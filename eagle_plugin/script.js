
// Check if Eagle API is available
if (typeof eagle === 'undefined') {
    console.error('Eagle API not available. This plugin must run inside Eagle.');
    document.body.innerHTML = '<div style="padding:20px;color:red">Error: Eagle API not available</div>';
}

const API_URL = "http://127.0.0.1:8005";
const child_process = require('child_process');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

// Generate or retrieve API auth token
let API_TOKEN = '';
const TOKEN_KEY = 'cosmictagger_api_token';

function getApiToken() {
    try {
        const stored = eagle.storage.getItemSync ? eagle.storage.getItemSync(TOKEN_KEY) : null;
        if (stored) return stored;
    } catch (e) {}
    // Generate new token
    const token = crypto.randomBytes(16).toString('hex');
    try {
        eagle.storage.setItemSync(TOKEN_KEY, token);
    } catch (e) {
        console.warn('Failed to store API token:', e);
    }
    return token;
}

function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (API_TOKEN) {
        options.headers['X-API-Key'] = API_TOKEN;
    }
    return fetch(url, options);
}

// Dynamic path detection
let PROJECT_ROOT = "";
let VENV_PYTHON = "";

function detectProjectRoot() {
    // Eagle plugin path points to eagle_plugin/ folder; project root is its parent
    try {
        const pluginPath = eagle.plugin.path;
        if (pluginPath) {
            return path.dirname(pluginPath);
        }
    } catch (e) {
        console.warn("Could not detect plugin path:", e);
    }
    // Fallback: use current working directory if it looks right
    const cwd = process.cwd();
    if (fs.existsSync(path.join(cwd, "backend", "localcura.py"))) {
        return cwd;
    }
    return "";
}

function detectPythonPath(projectRoot) {
    const platform = process.platform;
    // Try venv first
    if (platform === 'win32') {
        const venvPy = path.join(projectRoot, 'venv', 'Scripts', 'python.exe');
        if (fs.existsSync(venvPy)) return venvPy;
    } else {
        const venvPy = path.join(projectRoot, 'venv', 'bin', 'python');
        if (fs.existsSync(venvPy)) return venvPy;
    }
    // Try system Python from PATH
    const candidates = platform === 'win32'
        ? ['python.exe', 'python3.exe', 'py']
        : ['python3', 'python'];
    for (const py of candidates) {
        try {
            child_process.execSync(`${py} --version`, { stdio: 'ignore' });
            return py;
        } catch {
            continue;
        }
    }
    return 'python';
}

let availableModels = [];

async function fetchModels() {
    try {
        const res = await apiFetch(`${API_URL}/models`);
        if (!res.ok) return;
        const data = await res.json();
        availableModels = data.models || [];
        if (data.recommended && !settings.selectedModel) {
            settings.selectedModel = data.recommended;
        }
    } catch (e) {
        console.warn('Failed to fetch models:', e);
    }
}

function ensurePaths() {ensurePaths
    if (!PROJECT_ROOT) {
        PROJECT_ROOT = detectProjectRoot();
    }
    if (!VENV_PYTHON) {
        VENV_PYTHON = detectPythonPath(PROJECT_ROOT);
    }
    // Persist for next session
    if (PROJECT_ROOT) {
        settings.projectRoot = PROJECT_ROOT;
    }
    if (VENV_PYTHON) {
        settings.pythonPath = VENV_PYTHON;
    }
}

// State
let isProcessing = false;
let backendOnline = false;
let serverState = 'stopped'; // stopped, starting, running
let abortController = null;
let processedCount = 0;
let totalItems = 0;
let serverProcess = null;
let healthFailureCount = 0; // consecutive failed /health checks
const PID_KEY = 'cosmictagger_server_pid';

function storePid(pid) {
    try {
        if (eagle.storage.setItemSync) {
            eagle.storage.setItemSync(PID_KEY, String(pid));
        }
    } catch (e) {}
}

function getStoredPid() {
    try {
        if (eagle.storage.getItemSync) {
            return parseInt(eagle.storage.getItemSync(PID_KEY), 10);
        }
    } catch (e) {}
    return null;
}

function clearStoredPid() {
    try {
        if (eagle.storage.removeItemSync) {
            eagle.storage.removeItemSync(PID_KEY);
        }
    } catch (e) {}
}

function killOrphanPid() {
    const pid = getStoredPid();
    if (!pid || pid === serverProcess?.pid) return;
    try {
        if (process.platform === 'win32') {
            child_process.execSync(`taskkill /F /PID ${pid} /T`, { stdio: 'ignore' });
        } else {
            process.kill(pid, 'SIGKILL');
        }
        console.log(`Killed orphan server process ${pid}`);
    } catch (e) {
        // Process already dead
    }
    clearStoredPid();
}

// Memory management: track object URLs for cleanup
const objectURLs = new Set();

// Persistence key for Eagle storage
const PERSISTENCE_KEY = 'cosmictagger_state';
const SETTINGS_KEY = 'cosmictagger_settings';

// Default settings
const DEFAULT_SETTINGS = {
    chunkSize: 5,
    chunkDelayMs: 5000,
    itemDelayMs: 500,
    maxRetries: 2,
    retryDelayMs: 2000,
    enableAdaptiveChunking: true,
    enableCompression: true,
    enableSimilarityGrouping: true,
    similarityThreshold: 8,  // Hamming distance for grouping
    enableResume: true,
    enableProgressiveEnhancement: false,
    autoStartServer: true,
    projectRoot: '',
    pythonPath: '',
    extractMetadata: true,
    extractColors: true,
    maxTags: 30,
    verifyTags: true,
    selectedModel: '',
};

// Load settings from Eagle storage
let settings = { ...DEFAULT_SETTINGS };

async function loadSettings() {
    try {
        const stored = await eagle.storage.getItem(SETTINGS_KEY);
        if (stored) {
            settings = { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
            console.log('Settings loaded:', settings);
        }
    } catch (e) {
        console.warn('Failed to load settings:', e);
    }
}

async function saveSettings() {
    try {
        await eagle.storage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch (e) {
        console.warn('Failed to save settings:', e);
    }
}

// Adaptive chunking state
let responseTimeHistory = [];
let adaptiveChunkSize = settings.chunkSize;

function updateAdaptiveChunking(responseTimeMs) {
    if (!settings.enableAdaptiveChunking) return;
    
    responseTimeHistory.push(responseTimeMs);
    // Keep last 5 response times
    if (responseTimeHistory.length > 5) {
        responseTimeHistory.shift();
    }
    
    const avgResponseTime = responseTimeHistory.reduce((a, b) => a + b, 0) / responseTimeHistory.length;
    
    // Adjust chunk size based on average response time
    if (avgResponseTime < 3000) {
        adaptiveChunkSize = Math.min(10, settings.chunkSize + 2);
    } else if (avgResponseTime > 8000) {
        adaptiveChunkSize = Math.max(2, settings.chunkSize - 1);
    } else {
        adaptiveChunkSize = settings.chunkSize;
    }
    
    log(`Adaptive chunking: avg ${avgResponseTime.toFixed(0)}ms → chunk size ${adaptiveChunkSize}`, 'info', { toast: false });
}

// Get current chunk configuration (adaptive or fixed)
function getChunkConfig() {
    return {
        size: settings.enableAdaptiveChunking ? adaptiveChunkSize : settings.chunkSize,
        delay: settings.chunkDelayMs,
        itemDelay: settings.itemDelayMs,
        maxRetries: settings.maxRetries,
        retryDelay: settings.retryDelayMs,
    };
}

// Chunked Processing Configuration (now dynamic)
const CHUNK_SIZE = () => getChunkConfig().size;
const CHUNK_DELAY_MS = () => getChunkConfig().delay;
const ITEM_DELAY_MS = () => getChunkConfig().itemDelay;
const MAX_RETRIES = () => getChunkConfig().maxRetries;
const RETRY_DELAY_MS = () => getChunkConfig().retryDelay;

// Elements
const statusBadge = document.getElementById('statusBadge');
const statusText = document.getElementById('statusText');
const selCountEl = document.getElementById('selCount');
const processedCountEl = document.getElementById('processedCount');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const serverToggle = document.getElementById('serverToggle');
const queueSection = document.getElementById('queueSection');
const queueGrid = document.getElementById('queueGrid');
const queueProgress = document.getElementById('queueProgress');
const closeBtn = document.getElementById('closeBtn');
const toastContainer = document.getElementById('toast-container');
const activityDot = document.getElementById('activityDot');
const lastActivity = document.getElementById('lastActivity');

// Tag cleaning stopwords (mirror of backend SUBJECT_STOPWORDS)
const TAG_STOPWORDS = new Set([
    'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'from', 'with', 'by', 'at', 'as',
    'um', 'uh', 'etc', 'etc.',
    'subject', 'subjects', 'context',
    'image', 'photo', 'picture', 'screenshot', 'render', 'rendering', 'file', 'media', 'asset',
    'audio', 'sound', 'waveform', 'clip',
    'scene', 'view', 'shot', 'angle',
    'background', 'foreground', 'atmosphere',
]);

function cleanTags(tags) {
    if (!Array.isArray(tags)) return [];

    const out = [];
    for (const raw of tags) {
        if (!raw) continue;
        const text = String(raw).trim();
        if (!text) continue;

        // Split simple comma/semicolon/slash lists
        let parts = text.split(/[;,/]/).map(p => p.trim()).filter(Boolean);
        if (parts.length === 0) parts = [text];

        for (const part of parts) {
            // Strip prefix patterns like "Subject: ", "Genre: "
            let cleaned = part;
            const prefixMatch = cleaned.match(/^(Subject|Genre|Lighting|Color/Tone|Time/Season|Similar Artist|Cinematography|Production|Mood|Instrumentation|Structure|Topic|Tone|Intent|Entity|subjects|genre|lighting|color_and_tone|time_or_season)\s*[:\-]\s*/i);
            if (prefixMatch) {
                cleaned = cleaned.slice(prefixMatch[0].length).trim();
            }
            if (!cleaned) continue;
            const lower = cleaned.toLowerCase();
            if (TAG_STOPWORDS.has(lower)) continue;
            if (lower.length <= 2 && lower !== '3d' && lower !== 'ai') continue;
            if (!out.includes(cleaned)) out.push(cleaned);
        }
    }

    return out;
}

// Toast System
function toast(msg, type = 'info', duration = 4000) {
    const el = document.createElement('div');
    el.className = `toast ${type}`;

    // Icons based on type
    let icon = '';
    if (type === 'success') icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
    else if (type === 'error') icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>';
    else if (type === 'loading') icon = '<div class="spinner-sm" style="border-color: var(--text-muted); border-top-color: transparent;"></div>';
    else icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';

    el.innerHTML = `<div class="toast-icon">${icon}</div><div>${msg}</div>`;

    toastContainer.appendChild(el);

    // Update status bar
    lastActivity.textContent = msg;
    activityDot.classList.add('active');
    setTimeout(() => activityDot.classList.remove('active'), 2000);

    setTimeout(() => {
        el.classList.add('fade-out');
        el.addEventListener('transitionend', () => el.remove());
    }, duration);
}

// Logger Adapter
function log(msg, type = 'info', options = {}) {
    const { toast: forceToast } = options;

    // Update Status Bar Text
    lastActivity.textContent = msg;

    // Update Status Bar Color State
    const bar = document.getElementById('statusBar');
    if (!bar) return;
    bar.className = 'status-bar'; // reset

    if (type === 'success') {
        bar.classList.add('online');
    } else if (type === 'error') {
        bar.classList.add('error');
    } else if (type === 'loading' || type === 'processing') {
        bar.classList.add('processing');
    } else {
        bar.classList.add('init');
    }

    // Only toast for major events, not every little log
    const defaultShouldToast = (type === 'success' || type === 'error' || type === 'warn');
    const shouldToast = typeof forceToast === 'boolean' ? forceToast : defaultShouldToast;

    if (shouldToast) {
        toast(msg, type);
    }
}

// Server Management
function toggleServer() {
    if (serverProcess || backendOnline) {
        stopServer();
    } else {
        startServer();
    }
}

async function startServer() {
    if (serverProcess) return;

    // Ensure we know where the backend lives
    if (!PROJECT_ROOT || !VENV_PYTHON) {
        ensurePaths();
    }
    if (!PROJECT_ROOT) {
        toast("Cannot locate backend. Please set project root in settings.", "error");
        return;
    }

    serverState = 'starting';
    updateUIState();
    toast("Starting CosmicTagger Server...", "loading", 6000);

    serverToggle.textContent = "Starting...";
    serverToggle.disabled = true;

    try {
        // Get current library path
        let libPath = "";
        try {
            // Eagle API to get library info
            // Not all versions support eagle.library.path directly, try info()
            if (eagle.library.path) {
                libPath = eagle.library.path;
            } else {
                const info = await eagle.library.info();
                libPath = info.path;
            }
        } catch (e) {
            console.warn("Could not detect library path:", e);
        }

        const args = ["-m", "uvicorn", "backend.localcura:app", "--host", "0.0.0.0", "--port", "8005"];

        // Pass library path if found
        if (libPath) {
            const env = { ...process.env };
            env['EAGLE_LIBRARY_PATH'] = libPath;
        }

        const env = { ...process.env, EAGLE_LIBRARY_PATH: libPath };
        if (API_TOKEN) {
            env.COSMICTAGGER_API_KEY = API_TOKEN;
        }
        serverProcess = child_process.spawn(VENV_PYTHON, args, {
            cwd: PROJECT_ROOT,
            env: env,
            detached: false
        });

        serverProcess.stdout.on('data', (data) => { });

        if (serverProcess.pid) {
            storePid(serverProcess.pid);
        }

        serverProcess.stderr.on('data', (data) => {
            const msg = data.toString();
            if (msg.includes("Application startup complete")) {
                toast("Server Ready & Models Loaded", "success");
                checkBackend();
            }
        });

        serverProcess.on('close', (code) => {
            if (serverState !== 'stopped') {
                toast(`Server process exited (code ${code})`, 'warn');
            }
            serverProcess = null;
            serverState = 'stopped';
            serverToggle.textContent = "Start Server";
            serverToggle.disabled = false;
            serverToggle.classList.remove("running");
            checkBackend();
        });

    } catch (e) {
        toast(`Failed to spawn: ${e.message}`, "error");
        serverState = 'stopped';
        serverToggle.textContent = "Start Server";
        serverToggle.disabled = false;
    }
}

function stopServer() {
    if (serverProcess) {
        toast("Stopping server...", "info");
        try {
            if (process.platform === 'win32') {
                child_process.execSync(`taskkill /F /PID ${serverProcess.pid} /T`, { stdio: 'ignore' });
            } else {
                serverProcess.kill('SIGKILL');
            }
        } catch (e) {
            serverProcess.kill();
        }
        serverProcess = null;
    }
    clearStoredPid();
    serverState = 'stopped';
    serverToggle.textContent = "Start Server";
    serverToggle.classList.remove("running");
    backendOnline = false;
    setStatus(false);
}

// Status Updates
function setStatus(online) {
    backendOnline = online;

    if (online) {
        serverState = 'running';
        statusBadge.classList.add('online');
        statusText.textContent = "Online";

        if (!serverProcess) {
            serverToggle.textContent = "Server Running (External)";
            serverToggle.classList.add("running");
        } else {
            serverToggle.textContent = "Stop Server";
            serverToggle.classList.add("running");
            serverToggle.disabled = false;
        }
    } else {
        statusBadge.classList.remove('online');

        if (serverState === 'starting') {
            statusText.textContent = "Initializing...";
            // Keep spinning or waiting
        } else {
            statusText.textContent = "Offline";
            if (!serverProcess) {
                serverToggle.textContent = "Start Server";
                serverToggle.classList.remove("running");
            }
        }
    }
    updateUIState();
}

function updateUIState() {
    if (!backendOnline) {
        startBtn.disabled = true;
        // Don't return, update counts anyway
    } else {
        startBtn.disabled = isProcessing || selCountEl.textContent === '0';
    }

    eagle.item.getSelected().then(items => {
        selCountEl.textContent = items.length;
        if (backendOnline) {
            startBtn.disabled = isProcessing || items.length === 0;
        }

        if (isProcessing) {
            stopBtn.style.display = 'flex';
            startBtn.style.display = 'none';
        } else {
            stopBtn.style.display = 'none';
            startBtn.style.display = 'flex';
        }
    });
}

// Backend Health Check
async function checkBackend() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const res = await apiFetch(`${API_URL}/health`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (res.ok) {
            healthFailureCount = 0;
            if (!backendOnline) {
                setStatus(true);
                log("Backend connected", "success", { toast: false });
            }
        } else if (backendOnline) {
            healthFailureCount += 1;
            if (healthFailureCount >= 3) {
                setStatus(false);
                log("Backend error", "error", { toast: false });
            }
        }
    } catch (e) {
        if (backendOnline) {
            healthFailureCount += 1;
            if (healthFailureCount >= 3) {
                setStatus(false);
                log("Backend disconnected", "error", { toast: false });
            }
        }
    }
}

function createQueueItem(item) {
    const div = document.createElement('div');
    div.className = 'queue-item pending';
    div.id = `q-${item.id}`;
    div.dataset.itemId = item.id;

    let content = '<div class="file-icon">📄</div>';

    // Check if it's an image we can display
    const ext = item.ext.toLowerCase();
    if (['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'svg'].includes(ext)) {
        // Use object URL for memory management instead of direct file path
        try {
            const fs = require('fs');
            const fileBuffer = fs.readFileSync(item.filePath);
            const blob = new Blob([fileBuffer], { type: `image/${ext === 'jpg' ? 'jpeg' : ext}` });
            const objectURL = URL.createObjectURL(blob);
            objectURLs.add(objectURL);
            div.dataset.objectUrl = objectURL;
            content = `<img src="${objectURL}" class="queue-thumb" onerror="this.style.display='none'">`;
        } catch (e) {
            console.warn(`Failed to create object URL for ${item.name}:`, e);
            content = '<div class="file-icon">🖼️</div>';
        }
    } else if (['mp4', 'mov', 'webm', 'avi', 'mkv', 'flv', 'wmv', 'm4v'].includes(ext)) {
        content = '<div class="file-icon">🎬</div>';
    } else if (['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext)) {
        content = '<div class="file-icon">🎵</div>';
    }

    div.innerHTML = `
        ${content}
        <div class="status-dot-overlay"></div>
        <div class="error-overlay" id="err-${item.id}"></div>
    `;

    queueGrid.appendChild(div);
    return div;
}

// Cleanup object URLs to prevent memory leaks
function cleanupQueueMemory() {
    objectURLs.forEach(url => {
        URL.revokeObjectURL(url);
    });
    objectURLs.clear();
}

function updateQueueItem(id, status, errorMsg = null) {
    const el = document.getElementById(`q-${id}`);
    if (!el) return;

    el.className = `queue-item ${status}`; // pending, processing, success, error

    if (errorMsg) {
        const errEl = document.getElementById(`err-${id}`);
        if (errEl) errEl.textContent = errorMsg;
    }
}

// Utility: Delay promise
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Process a single item with retry logic and response time tracking
async function processSingleItem(item, abortController, attempt = 1) {
    console.log(`[Single] Processing item: ${item.name} (attempt ${attempt})`);
    const startTime = Date.now();
    let result = null;
    
    try {
        // Update UI to Processing
        updateQueueItem(item.id, 'processing');
        lastActivity.textContent = `Analyzing: ${item.name}`;
        activityDot.classList.add('active');

        // 1. Get File Path
        let filePath = item.filePath;
        if (!filePath) {
            throw new Error("No file path found");
        }

        // 2. Read File (Node API)
        const fs = require('fs');
        const fileBuffer = fs.readFileSync(filePath);
        const blob = new Blob([fileBuffer]);

        // 3. Upload
        const formData = new FormData();
        formData.append('file', blob, item.name + "." + item.ext);

        const res = await apiFetch(`${API_URL}/process`, {
            method: 'POST',
            body: formData,
            signal: abortController.signal
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        result = await res.json();

        if (!result || result.status === 'skipped') {
            updateQueueItem(item.id, 'pending');
            return { success: false, skipped: true };
        }

        // 4. Update Eagle
        let rawNewTags = result.tags || [];

        const cleanExisting = cleanTags(item.tags || []);
        const cleanNew = cleanTags(rawNewTags);
        const finalTags = [...new Set([...cleanExisting, ...cleanNew])];

        // Rating: map backend aesthetic (0-10) to Eagle stars (1-5)
        let rating = typeof item.star === 'number' ? item.star : 0;
        if (result.type !== 'audio' && typeof result.aesthetic === 'number') {
            const score = result.aesthetic;
            rating = Math.max(1, Math.min(5, Math.round(score / 2)));
        }
        rating = Math.max(1, Math.min(5, Math.floor(rating)));

        // Save changes
        item.tags = finalTags;
        item.star = rating;
        if (result.analysis && result.analysis.summary) {
            item.annotation = result.analysis.summary;
        }

        await item.save();

        // Show results panel
        showResultPanel(item, result);
        
        // Success State
        updateQueueItem(item.id, 'success');
        
        // Track response time for adaptive chunking
        const responseTime = Date.now() - startTime;
        updateAdaptiveChunking(responseTime);
        
        console.log(`[Single] Success for ${item.name}, tags:`, result.tags?.slice(0, 10));
        return { success: true, responseTime, result };

    } catch (e) {
        if (e.name === 'AbortError') throw e;

        // Check if this is a retryable error (from backend or network)
        const isRetryable = (
            result?.retryable === true ||
            (e.message && (
                e.message.includes('503') ||
                e.message.includes('504') ||
                e.message.includes('timeout') ||
                e.message.includes('fetch') ||
                e.message.includes('network')
            ))
        );

        const maxRetries = MAX_RETRIES();
        const retryDelay = RETRY_DELAY_MS();
        
        if (isRetryable && attempt <= maxRetries) {
            log(`Retrying ${item.name} (attempt ${attempt}/${maxRetries})...`, 'warn', { toast: false });
            await delay(retryDelay * attempt); // Exponential backoff
            return processSingleItem(item, abortController, attempt + 1);
        }

        console.error(`[Single] Error for ${item.name}:`, e.message);
        updateQueueItem(item.id, 'error', e.message);
        return { success: false, error: e.message };
    } finally {
        processedCount++;
        processedCountEl.textContent = processedCount;
        queueProgress.textContent = `${processedCount}/${totalItems}`;
        
        // Update Eagle native progress bar
        try {
            const progress = totalItems > 0 ? processedCount / totalItems : 0;
            eagle.window.setProgress(progress);
        } catch (e) {}
        
        activityDot.classList.remove('active');
    }
}

// Send a batch of items to the backend via file paths (server-side batch)
async function processBatchChunk(items, abortController) {
    const paths = items.map(item => item.filePath).filter(Boolean);
    if (paths.length === 0) {
        return { success: false, error: "No file paths available" };
    }

    try {
        const res = await apiFetch(`${API_URL}/process/batch/paths`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paths }),
            signal: abortController.signal
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        const backendResults = data.results || [];
        console.log(`[Batch] Backend returned ${backendResults.length} results for ${items.length} items`);

        // Apply results back to Eagle items
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const result = backendResults[i] || {};
            const startTime = Date.now();

            if (result.error) {
                console.warn(`[Batch] Item ${i} (${item.name}) error:`, result.error);
                updateQueueItem(item.id, 'error', result.error);
                processedCount++;
                processedCountEl.textContent = processedCount;
                queueProgress.textContent = `${processedCount}/${totalItems}`;
                continue;
            }

            try {
                let rawNewTags = result.tags || [];
                console.log(`[Batch] Item ${i} (${item.name}) tags:`, rawNewTags.slice(0, 10));

                const cleanExisting = cleanTags(item.tags || []);
                const cleanNew = cleanTags(rawNewTags);
                const finalTags = [...new Set([...cleanExisting, ...cleanNew])];

                // Rating: map backend aesthetic (0-10) to Eagle stars (1-5)
                let rating = typeof item.star === 'number' ? item.star : 0;
                if (result.media_kind !== 'audio' && typeof result.aesthetic === 'number') {
                    const score = result.aesthetic;
                    rating = Math.max(1, Math.min(5, Math.round(score / 2)));
                }
                rating = Math.max(1, Math.min(5, Math.floor(rating)));

                item.tags = finalTags;
                item.star = rating;
                if (result.analysis && result.analysis.summary) {
                    item.annotation = result.analysis.summary;
                }
                await item.save();
                updateQueueItem(item.id, 'success');
            } catch (saveErr) {
                console.error(`[Batch] Item ${i} save error:`, saveErr);
                updateQueueItem(item.id, 'error', saveErr.message);
            }

            processedCount++;
            processedCountEl.textContent = processedCount;
            queueProgress.textContent = `${processedCount}/${totalItems}`;
            
            // Update Eagle native progress bar
            try {
                const progress = totalItems > 0 ? processedCount / totalItems : 0;
                eagle.window.setProgress(progress);
            } catch (e) {}

            // Track response time for adaptive chunking (use per-item approximation)
            const responseTime = Date.now() - startTime + 500;
            updateAdaptiveChunking(responseTime);

            // Small delay between items to keep UI responsive
            if (i < items.length - 1) {
                await delay(ITEM_DELAY_MS());
            }
        }

        // Build return results for propagation
        const propagationResults = [];
        for (const item of items) {
            propagationResults.push({
                id: item.id,
                tags: item.tags,
                star: item.star,
                annotation: item.annotation,
            });
        }
        return { success: true, results: propagationResults };

    } catch (e) {
        if (e.name === 'AbortError') throw e;
        // Fallback to individual processing
        log(`Batch path processing failed: ${e.message}. Falling back to individual uploads.`, 'warn', { toast: false });
        for (const item of items) {
            if (abortController.signal.aborted) break;
            await processSingleItem(item, abortController);
        }
        return { success: false, error: e.message };
    }
}

// Similarity grouping: detect duplicates before processing
async function groupSimilarItems(items) {
    if (!settings.enableSimilarityGrouping) return { representatives: items, skipMap: {} };
    
    // Filter to image items only
    const imageItems = items.filter(item => {
        const ext = (item.ext || '').toLowerCase();
        return ['jpg','jpeg','png','webp','bmp','tiff','gif','avif','heic'].includes(ext);
    });
    
    if (imageItems.length < 2) return { representatives: items, skipMap: {} };
    
    try {
        // Send all image paths to similarity endpoint
        const paths = imageItems.map(item => item.filePath).filter(Boolean);
        if (paths.length < 2) return { representatives: items, skipMap: {} };
        
        const formData = new FormData();
        const fs = require('fs');
        for (let i = 0; i < Math.min(paths.length, 50); i++) { // cap at 50 for performance
            const buf = fs.readFileSync(paths[i]);
            formData.append('files', new Blob([buf]), imageItems[i].name + '.' + imageItems[i].ext);
        }
        
        const res = await apiFetch(`${API_URL}/similarity/group?threshold=${settings.similarityThreshold}`, {
            method: 'POST',
            body: formData
        });
        
        if (!res.ok) return { representatives: items, skipMap: {} };
        
        const data = await res.json();
        const groups = data.groups || [];
        if (groups.length === 0) return { representatives: items, skipMap: {} };
        
        // Build skip map: representative index -> list of duplicate indices (in imageItems)
        const skipMap = {};
        const representatives = [];
        const used = new Set();
        
        for (const group of groups) {
            const indices = group.indices || [];
            if (indices.length < 2) continue;
            const repIdx = indices[0];
            const repItem = imageItems[repIdx];
            representatives.push(repItem);
            used.add(repItem.id);
            skipMap[repItem.id] = indices.slice(1).map(idx => {
                const dup = imageItems[idx];
                return dup ? dup.id : null;
            }).filter(Boolean);
        }
        
        // Add non-grouped items as their own representatives
        for (const item of imageItems) {
            if (!used.has(item.id)) {
                representatives.push(item);
            }
        }
        
        // Add non-image items back
        const nonImageItems = items.filter(item => !imageItems.includes(item));
        representatives.push(...nonImageItems);
        
        toast(`Grouped ${groups.length} similarity sets, skipping ${Object.values(skipMap).flat().length} duplicates`, 'info');
        return { representatives, skipMap };
        
    } catch (e) {
        console.warn('Similarity grouping failed:', e);
        return { representatives: items, skipMap: {} };
    }
}

// Apply tags from representative to its duplicates
async function propagateTags(repItem, dupIds, resultsMap) {
    const result = resultsMap[repItem.id];
    if (!result) return;
    
    for (const dupId of dupIds) {
        try {
            const dupItem = await eagle.item.get({ id: dupId });
            if (!dupItem) continue;
            
            let rawNewTags = result.tags || [];
            
            const cleanExisting = cleanTags(dupItem.tags || []);
            const cleanNew = cleanTags(rawNewTags);
            dupItem.tags = [...new Set([...cleanExisting, ...cleanNew])];
            
            if (result.aesthetic !== undefined) {
                dupItem.star = Math.max(1, Math.min(5, Math.round(result.aesthetic / 2)));
            }
            if (result.analysis && result.analysis.summary) {
                dupItem.annotation = result.analysis.summary;
            }
            await dupItem.save();
            updateQueueItem(dupId, 'success');
        } catch (e) {
            console.warn(`Failed to propagate tags to ${dupId}:`, e);
        }
    }
}

// Process Logic with Chunking
async function processImages() {
    if (isProcessing) return;

    let items = await eagle.item.getSelected();
    console.log('[Process] Selected items:', items.length, items.map(i => i.name));
    if (items.length === 0) return;

    isProcessing = true;
    abortController = new AbortController();
    processedCount = 0;
    totalItems = items.length;
    
    // Reset adaptive chunking for new batch
    responseTimeHistory = [];
    adaptiveChunkSize = settings.chunkSize;

    updateUIState();

    // Setup Queue UI
    queueSection.style.display = 'flex';
    queueGrid.innerHTML = '';
    queueProgress.textContent = `0/${totalItems}`;
    processedCountEl.textContent = "0";

    // Populate Queue with Pending items
    items.forEach(item => createQueueItem(item));
    
    const processedIds = [];
    // Save batch state for resume capability
    if (settings.enableResume) {
        saveBatchState(items, processedIds);
    }

    const chunkSize = CHUNK_SIZE();
    const totalChunks = Math.ceil(items.length / chunkSize);
    const resultsMap = {}; // repId -> result, for propagation
    toast(`Starting batch analysis for ${items.length} items in ${totalChunks} chunks (size: ${chunkSize})...`, "info");

    // Process in chunks
    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
        if (abortController.signal.aborted) {
            toast("Batch processing stopped by user.", "warn");
            break;
        }

        const start = chunkIndex * chunkSize;
        const end = Math.min(start + chunkSize, items.length);
        const chunk = items.slice(start, end);
        
        // Get fresh config (adaptive chunking may have changed it)
        const currentChunkSize = CHUNK_SIZE();
        const itemDelay = ITEM_DELAY_MS();
        const chunkDelay = CHUNK_DELAY_MS();

        console.log(`[Chunk] Processing chunk ${chunkIndex + 1}/${totalChunks}, items:`, chunk.map(i => i.name));
        log(`Processing chunk ${chunkIndex + 1}/${totalChunks} (${chunk.length} items, chunk size: ${currentChunkSize})...`, 'info', { toast: false });

        // Use server-side batch processing for file paths (much faster)
        const allHavePaths = chunk.every(item => !!item.filePath);
        console.log(`[Chunk] allHavePaths:`, allHavePaths, 'backendOnline:', backendOnline);
        if (allHavePaths && backendOnline) {
            try {
                const batchResult = await processBatchChunk(chunk, abortController);
                // Save progress for resume
                if (settings.enableResume && batchResult.success) {
                    chunk.forEach(item => processedIds.push(item.id));
                    saveBatchState(items, processedIds);
                }
                // Store results for duplicate propagation (map by item id)
                if (batchResult.success && batchResult.results) {
                    for (let j = 0; j < chunk.length; j++) {
                        const item = chunk[j];
                        const result = batchResult.results[j];
                        if (result && !result.error) {
                            resultsMap[item.id] = result;
                            showResultPanel(item, result);
                        }
                    }
                }
            } catch (e) {
                if (e.name === 'AbortError') break;
                log(`Batch chunk failed: ${e.message}`, 'error', { toast: true });
            }
        } else {
            // Fallback: individual file upload (original behavior)
            for (let i = 0; i < chunk.length; i++) {
                if (abortController.signal.aborted) {
                    break;
                }

                const result = await processSingleItem(chunk[i], abortController);
                
                // Save progress for resume
                if (settings.enableResume && result.success) {
                    processedIds.push(chunk[i].id);
                    saveBatchState(items, processedIds);
                }

                // Small delay between items within a chunk (except the last one)
                if (i < chunk.length - 1) {
                    await delay(itemDelay);
                }
            }
        }

        // Delay between chunks (except after the last chunk)
        if (chunkIndex < totalChunks - 1 && !abortController.signal.aborted) {
            log(`Chunk ${chunkIndex + 1} complete. Pausing before next chunk...`, 'info', { toast: false });
            await delay(chunkDelay);
        }
    }

    finishProcessing(skipMap, resultsMap);
}

function finishProcessing(skipMap, resultsMap) {
    console.log('[Finish] Batch complete. skipMap:', skipMap ? Object.keys(skipMap).length : 0, 'resultsMap:', resultsMap ? Object.keys(resultsMap).length : 0);
    
    // Propagate tags from representatives to duplicates
    if (skipMap && Object.keys(skipMap).length > 0 && resultsMap) {
        for (const [repId, dupIds] of Object.entries(skipMap)) {
            try {
                const repItem = items.find(i => i.id === repId);
                if (repItem) propagateTags(repItem, dupIds, resultsMap);
            } catch (e) {
                console.warn('Propagation failed:', e);
            }
        }
    }
    
    isProcessing = false;
    abortController = null;
    lastActivity.textContent = "Batch Complete";
    updateUIState();

    // Clean up memory (object URLs)
    cleanupQueueMemory();

    // Tags saved via item.save() — no full reload needed
}

// Persistence functions for resume capability
async function saveBatchState(items, processedIds) {
    try {
        const state = {
            items: items.map(item => ({ id: item.id, name: item.name, filePath: item.filePath, ext: item.ext })),
            processedIds: processedIds || [],
            timestamp: Date.now(),
            totalItems: items.length
        };
        await eagle.storage.setItem(PERSISTENCE_KEY, JSON.stringify(state));
    } catch (e) {
        console.warn('Failed to save batch state:', e);
    }
}

async function loadBatchState() {
    try {
        const stored = await eagle.storage.getItem(PERSISTENCE_KEY);
        if (stored) {
            const state = JSON.parse(stored);
            // Migrate old count-based state to ID-based
            if (state.processedCount !== undefined && !state.processedIds) {
                state.processedIds = state.items.slice(0, state.processedCount).map(i => i.id);
                delete state.processedCount;
            }
            return state;
        }
    } catch (e) {
        console.warn('Failed to load batch state:', e);
    }
    return null;
}

async function clearBatchState() {
    try {
        await eagle.storage.removeItem(PERSISTENCE_KEY);
    } catch (e) {
        console.warn('Failed to clear batch state:', e);
    }
}

async function checkForResume() {
    if (!settings.enableResume) return;
    
    try {
        const state = await loadBatchState();
        if (state && state.processedCount < state.totalItems) {
            const timeSince = Date.now() - state.timestamp;
            const timeSinceStr = timeSince < 60000 ? 'just now' : 
                                timeSince < 3600000 ? `${Math.floor(timeSince / 60000)}m ago` :
                                `${Math.floor(timeSince / 3600000)}h ago`;
            
            // Use toast instead of confirm for Eagle plugin environment
            toast(`Found incomplete batch from ${timeSinceStr} (${state.processedCount}/${state.totalItems} items). Select items and click Start to resume.`, 'info');
        }
    } catch (e) {
        console.warn('Failed to check for resume state:', e);
    }
}

async function resumeBatch(state) {
    // This would need more implementation to fully restore Eagle items
    // For now, just show a toast
    toast(`Resuming batch: ${state.processedCount}/${state.totalItems} complete`, 'info');
}

// Configuration UI functions
function createSettingsUI() {
    try {
        // Check if settings button already exists
        if (document.getElementById('settingsBtn')) {
            return;
        }
        
        // Create settings button in header
        const settingsBtn = document.createElement('button');
        settingsBtn.className = 'icon-btn';
        settingsBtn.id = 'settingsBtn';
        settingsBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M12 1v6m0 6v6m4.22-10.22l4.24-4.24M6.34 6.34L2.1 2.1m17.8 17.8l-4.24-4.24M6.34 17.66l-4.24 4.24M23 12h-6m-6 0H1m20.24 4.24l-4.24-4.24M6.34 6.34l-4.24-4.24"></path>
            </svg>
        `;
        settingsBtn.title = 'Settings';
        settingsBtn.onclick = toggleSettingsPanel;
        
        // Insert before close button
        const header = document.querySelector('.header .no-drag');
        if (header && closeBtn) {
            header.insertBefore(settingsBtn, closeBtn);
        } else {
            console.warn('Could not find header or close button to insert settings UI');
        }
    } catch (e) {
        console.error('Failed to create settings UI:', e);
    }
}

function toggleSettingsPanel() {
    // Check if panel exists
    let panel = document.getElementById('settingsPanel');
    if (panel) {
        panel.remove();
        return;
    }
    
    // Create settings panel
    panel = document.createElement('div');
    panel.id = 'settingsPanel';
    panel.className = 'settings-panel';
    panel.innerHTML = `
        <div class="settings-header">
            <h3>Settings</h3>
            <button class="icon-btn" onclick="toggleSettingsPanel()">×</button>
        </div>
        <div class="settings-content">
            <div class="setting-group">
                <h4>Chunking</h4>
                <label>
                    Chunk Size: <span id="chunkSizeVal">${settings.chunkSize}</span>
                    <input type="range" min="1" max="20" value="${settings.chunkSize}" 
                           onchange="updateSetting('chunkSize', this.value); document.getElementById('chunkSizeVal').textContent = this.value;">
                </label>
                <label>
                    Chunk Delay (ms): <span id="chunkDelayVal">${settings.chunkDelayMs}</span>
                    <input type="range" min="1000" max="10000" step="500" value="${settings.chunkDelayMs}" 
                           onchange="updateSetting('chunkDelayMs', this.value); document.getElementById('chunkDelayVal').textContent = this.value;">
                </label>
                <label>
                    <input type="checkbox" ${settings.enableAdaptiveChunking ? 'checked' : ''} 
                           onchange="updateSetting('enableAdaptiveChunking', this.checked)">
                    Enable Adaptive Chunking
                </label>
            </div>
            <div class="setting-group">
                <h4>Features</h4>
                <label>
                    <input type="checkbox" ${settings.enableResume ? 'checked' : ''} 
                           onchange="updateSetting('enableResume', this.checked)">
                    Enable Resume
                </label>
                <label>
                    <input type="checkbox" ${settings.enableCompression ? 'checked' : ''} 
                           onchange="updateSetting('enableCompression', this.checked)">
                    Image Compression
                </label>
                <label>
                    <input type="checkbox" ${settings.extractMetadata ? 'checked' : ''} 
                           onchange="updateSetting('extractMetadata', this.checked)">
                    Extract ComfyUI/SD Metadata
                </label>
                <label>
                    <input type="checkbox" ${settings.extractColors ? 'checked' : ''} 
                           onchange="updateSetting('extractColors', this.checked)">
                    Extract Color Palette
                </label>
                <label>
                    <input type="checkbox" ${settings.verifyTags ? 'checked' : ''} 
                           onchange="updateSetting('verifyTags', this.checked)">
                    3-Layer Tag Verification
                </label>
            </div>
            <div class="setting-group">
                <h4>Tag Limits</h4>
                <label>
                    Max Tags: <span id="maxTagsVal">${settings.maxTags}</span>
                    <input type="range" min="5" max="50" value="${settings.maxTags}" 
                           onchange="updateSetting('maxTags', this.value); document.getElementById('maxTagsVal').textContent = this.value;">
                </label>
            </div>
            <div class="setting-group">
                <h4>AI Model</h4>
                <label>
                    <select id="modelSelect" onchange="updateSetting('selectedModel', this.value)" 
                            style="width:100%;background:var(--bg-app);color:var(--text-main);border:1px solid var(--border-subtle);border-radius:4px;padding:4px;">
                        <option value="">${settings.selectedModel || 'Auto (qwen3-vl:8b)'}</option>
                        ${availableModels.map(m => `<option value="${m.name}" ${settings.selectedModel === m.name ? 'selected' : ''}>${m.name} (${m.size_gb}GB) ${m.vision ? '👁' : ''}</option>`).join('')}
                    </select>
                </label>
                <button onclick="fetchModels().then(() => { document.getElementById('modelSelect').innerHTML = '<option value=\'\'>Auto</option>' + availableModels.map(m => '<option value=\'' + m.name + '\'>' + m.name + ' (' + m.size_gb + 'GB) ' + (m.vision ? '👁' : '') + '</option>').join(''); toast('Models refreshed', 'success'); })">Refresh Models</button>
            </div>
            <div class="setting-group">
                <h4>Backend</h4>
                <label>
                    Project Root:
                    <input type="text" id="projectRootInput" value="${settings.projectRoot || ''}" 
                           style="width:100%;background:var(--bg-app);color:var(--text-main);border:1px solid var(--border-subtle);border-radius:4px;padding:4px;"
                           onchange="updateSetting('projectRoot', this.value)">
                </label>
                <label>
                    Python Path:
                    <input type="text" id="pythonPathInput" value="${settings.pythonPath || ''}" 
                           style="width:100%;background:var(--bg-app);color:var(--text-main);border:1px solid var(--border-subtle);border-radius:4px;padding:4px;"
                           onchange="updateSetting('pythonPath', this.value)">
                </label>
                <small style="color:var(--text-dim);display:block;margin-top:4px;">Leave blank to auto-detect on next start.</small>
            </div>
            <div class="setting-actions">
                <button onclick="saveSettings(); toggleSettingsPanel(); toast('Settings saved', 'success');">Save</button>
                <button onclick="resetSettings();">Reset to Defaults</button>
            </div>
        </div>
    `;
    
    // Add styles
    const style = document.createElement('style');
    style.textContent = `
        .settings-panel {
            position: fixed;
            top: 60px;
            right: 20px;
            width: 300px;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-lg);
            padding: 16px;
            z-index: 1000;
            box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        }
        .settings-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-subtle);
        }
        .settings-header h3 {
            margin: 0;
            font-size: 16px;
        }
        .setting-group {
            margin-bottom: 16px;
        }
        .setting-group h4 {
            margin: 0 0 8px 0;
            font-size: 12px;
            text-transform: uppercase;
            color: var(--text-muted);
        }
        .setting-group label {
            display: block;
            margin: 8px 0;
            font-size: 13px;
        }
        .setting-group input[type="range"] {
            width: 100%;
            margin-top: 4px;
        }
        .setting-actions {
            display: flex;
            gap: 8px;
        }
        .setting-actions button {
            flex: 1;
            padding: 8px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: var(--radius-md);
            cursor: pointer;
        }
    `;
    document.head.appendChild(style);
    document.body.appendChild(panel);
}


// Results Panel
function showResultPanel(item, result) {
    let panel = document.getElementById('resultPanel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'resultPanel';
        panel.style.cssText = `
            position: fixed; bottom: 10px; left: 10px; right: 10px;
            max-height: 200px; overflow-y: auto;
            background: var(--bg-card); border: 1px solid var(--border-subtle);
            border-radius: var(--radius-lg); padding: 12px;
            z-index: 900; font-size: 12px;
            box-shadow: 0 -4px 20px rgba(0,0,0,0.3);
        `;
        document.body.appendChild(panel);
    }
    
    const tags = result.tags || [];
    const palette = result.color_palette || {};
    const metadata = result.metadata || {};
    const aesthetic = result.aesthetic || 0;
    const stars = '★'.repeat(Math.round(aesthetic / 2)) + '☆'.repeat(5 - Math.round(aesthetic / 2));
    
    let colorsHtml = '';
    if (palette.dominant) {
        colorsHtml = '<div style="display:flex;gap:4px;margin-top:4px;">' + 
            palette.dominant.map(c => 
                `<div style="width:20px;height:20px;border-radius:4px;background:${c.hex};border:1px solid var(--border-subtle);" title="${c.hex}"></div>`
            ).join('') + 
            `</div><div style="color:var(--text-muted);margin-top:2px;">${palette.palette_type || ''}</div>`;
    }
    
    let metaHtml = '';
    if (metadata.ai_generated) {
        metaHtml = `<div style="color:var(--accent);margin-top:4px;">AI Generated (${metadata.generator || 'unknown'})</div>`;
        if (metadata.seed) metaHtml += `<div style="color:var(--text-muted);">Seed: ${metadata.seed}</div>`;
    }
    
    panel.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong>${item.name}</strong>
            <span style="color:var(--accent);">${stars} ${aesthetic > 0 ? aesthetic.toFixed(1) : ''}</span>
        </div>
        <div style="margin-top:4px;color:var(--text-main);">${tags.slice(0, 15).join(', ')}${tags.length > 15 ? '...' : ''}</div>
        ${colorsHtml}
        ${metaHtml}
    `;
    panel.style.display = 'block';
}

function updateSetting(key, value) {
    if (typeof value === 'string' && !isNaN(value)) {
        value = parseInt(value);
    }
    settings[key] = value;
}

function resetSettings() {
    settings = { ...DEFAULT_SETTINGS };
    saveSettings();
    toggleSettingsPanel();
    toast('Settings reset to defaults', 'success');
}

// Keyboard shortcut: Ctrl+Shift+T to tag selected
window.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 't') {
        e.preventDefault();
        if (!isProcessing) {
            processImages();
        }
    }
});

// Events
startBtn.addEventListener('click', processImages);
stopBtn.addEventListener('click', stopProcessing);
serverToggle.addEventListener('click', toggleServer);
// clearLogBtn removed in UI update
closeBtn.addEventListener('click', () => {
    // Eagle API uses hide() to close the plugin window
    eagle.window.hide();
});

function stopProcessing() {
    if (abortController) {
        abortController.abort();
    }
    isProcessing = false;
    updateUIState();
}

// Init
eagle.onPluginCreate(async (plugin) => {
    try {
        log("CosmicTagger Plugin Ready.");

        // Initialize auth token
        API_TOKEN = getApiToken();

        // Kill any orphaned server process from previous session
        killOrphanPid();

        // Fetch available Ollama models
        await fetchModels();
        
        // Load settings from storage
        await loadSettings();
        
        // Create settings UI
        createSettingsUI();

        // First, see if a backend is already running
        await checkBackend();

        // If nothing is online yet and auto-start is enabled, start the backend
        if (!backendOnline && !serverProcess && settings.autoStartServer) {
            startServer();
        }
        
        // Check for incomplete batch to resume
        await checkForResume();

        // Periodic health + selection checks
        setInterval(checkBackend, 2000);
        setInterval(updateUIState, 1000);
        updateUIState();
    } catch (e) {
        console.error("Plugin initialization failed:", e);
        toast("Plugin initialization failed: " + e.message, "error");
    }
});
