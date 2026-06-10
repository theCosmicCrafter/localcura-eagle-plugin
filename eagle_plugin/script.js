
// Check if Eagle API is available
if (typeof eagle === 'undefined') {
    console.error('Eagle API not available. This plugin must run inside Eagle.');
    document.body.innerHTML = '<div style="padding:20px;color:red">Error: Eagle API not available</div>';
}

const API_URL = "http://127.0.0.1:8005";
const child_process = require('child_process');
const path = require('path');

// Config - Adjust path as needed
const PROJECT_ROOT = "c:\\Users\\richk\\CascadeProjects\\localcura-eagle-plugin";
const VENV_PYTHON = path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe");

// State
let isProcessing = false;
let backendOnline = false;
let serverState = 'stopped'; // stopped, starting, running
let abortController = null;
let processedCount = 0;
let totalItems = 0;
let serverProcess = null;
let healthFailureCount = 0; // consecutive failed /health checks

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
    enableProgressiveEnhancement: false,  // Off by default (3-stage tagging)
    autoStartServer: true,
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
            const lower = part.toLowerCase();
            if (TAG_STOPWORDS.has(lower)) continue;
            if (lower.length <= 2 && lower !== '3d' && lower !== 'ai') continue;
            if (!out.includes(part)) out.push(part);
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

        serverProcess = child_process.spawn(VENV_PYTHON, args, {
            cwd: PROJECT_ROOT,
            env: { ...process.env, EAGLE_LIBRARY_PATH: libPath },
            detached: false
        });

        serverProcess.stdout.on('data', (data) => { });

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
        serverProcess.kill();
        serverProcess = null;
    }
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
        const res = await fetch(`${API_URL}/health`, { signal: controller.signal });
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

        const res = await fetch(`${API_URL}/process`, {
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

        if (result.type === 'audio') {
            // Audio specific handling if needed
        } else if (result.analysis) {
            if (Array.isArray(result.analysis.subjects)) {
                rawNewTags.push(...result.analysis.subjects);
            }
            if (result.analysis.visual_style) {
                rawNewTags.push(result.analysis.visual_style);
            }
        }

        const cleanExisting = cleanTags(item.tags || []);
        const cleanNew = cleanTags(rawNewTags);
        const finalTags = [...new Set([...cleanExisting, ...cleanNew])];

        // Rating
        let rating = typeof item.star === 'number' ? item.star : 0;
        if (result.type !== 'audio' && typeof result.aesthetic === 'number') {
            const score = result.aesthetic;
            rating = Math.round(score / 2);
        }
        rating = Math.max(0, Math.min(5, Math.floor(rating)));

        // Save changes
        item.tags = finalTags;
        item.star = rating;
        if (result.analysis && result.analysis.summary) {
            item.annotation = result.analysis.summary;
        }

        await item.save();

        // Success State
        updateQueueItem(item.id, 'success');
        
        // Track response time for adaptive chunking
        const responseTime = Date.now() - startTime;
        updateAdaptiveChunking(responseTime);
        
        return { success: true, responseTime };

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

        updateQueueItem(item.id, 'error', e.message);
        return { success: false, error: e.message };
    } finally {
        processedCount++;
        processedCountEl.textContent = processedCount;
        queueProgress.textContent = `${processedCount}/${totalItems}`;
        activityDot.classList.remove('active');
    }
}

// Process Logic with Chunking
async function processImages() {
    if (isProcessing) return;

    const items = await eagle.item.getSelected();
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
    
    // Save batch state for resume capability
    if (settings.enableResume) {
        saveBatchState(items, 0);
    }

    const chunkSize = CHUNK_SIZE();
    const totalChunks = Math.ceil(items.length / chunkSize);
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

        log(`Processing chunk ${chunkIndex + 1}/${totalChunks} (${chunk.length} items, chunk size: ${currentChunkSize})...`, 'info', { toast: false });

        // Process items in current chunk with small delays between them
        for (let i = 0; i < chunk.length; i++) {
            if (abortController.signal.aborted) {
                break;
            }

            const result = await processSingleItem(chunk[i], abortController);
            
            // Save progress for resume
            if (settings.enableResume && result.success) {
                saveBatchState(items, processedCount);
            }

            // Small delay between items within a chunk (except the last one)
            if (i < chunk.length - 1) {
                await delay(itemDelay);
            }
        }

        // Delay between chunks (except after the last chunk)
        if (chunkIndex < totalChunks - 1 && !abortController.signal.aborted) {
            log(`Chunk ${chunkIndex + 1} complete. Pausing before next chunk...`, 'info', { toast: false });
            await delay(chunkDelay);
        }
    }

    finishProcessing();
}

function finishProcessing() {
    isProcessing = false;
    abortController = null;
    lastActivity.textContent = "Batch Complete";
    updateUIState();

    // Clean up memory (object URLs)
    cleanupQueueMemory();

    // Refresh Eagle view to show new tags
    eagle.window.reload();
}

// Persistence functions for resume capability
async function saveBatchState(items, processedCount) {
    try {
        const state = {
            items: items.map(item => ({ id: item.id, name: item.name, filePath: item.filePath, ext: item.ext })),
            processedCount,
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
            return JSON.parse(stored);
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
