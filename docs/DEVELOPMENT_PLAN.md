# Development Plan
# LocalCura AI for Eagle - v2.0 Roadmap

**Document Version:** 1.0  
**Date:** February 9, 2026  
**Status:** Draft  
**Sprints:** 6 x 2-week sprints (12 weeks total)

---

## Executive Summary

This development plan outlines a 12-week roadmap to deliver LocalCura v2.0, featuring a major architecture upgrade with modern efficient VLMs (LFM2-VL), enhanced asset support, and improved user experience.

---

## Phase Overview

| Phase | Duration | Focus | Key Deliverable |
|-------|----------|-------|-----------------|
| **Phase 1** | Weeks 1-2 | Foundation | Model integration, testing framework |
| **Phase 2** | Weeks 3-4 | Backend Core | New pipeline processors, API v2 |
| **Phase 3** | Weeks 5-6 | Frontend Revamp | New UI components, state management |
| **Phase 4** | Weeks 7-8 | Integration | End-to-end testing, Eagle API integration |
| **Phase 5** | Weeks 9-10 | Polish & Features | Duplicate detection, audio captioning |
| **Phase 6** | Weeks 11-12 | Release Prep | Documentation, packaging, beta testing |

---

## Phase 1: Foundation (Weeks 1-2)

### Sprint 1: Model Research & Integration

**Goals:**
- Integrate LFM2-VL-1.6B as primary VLM
- Set up model fallback system (Moondream2)
- Establish testing framework

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 1.1 | Research LFM2-VL HuggingFace integration | ML Engineer | 8 | P0 |
| 1.2 | Create model abstraction layer | Backend Dev | 16 | P0 |
| 1.3 | Implement LFM2-VL inference engine | ML Engineer | 12 | P0 |
| 1.4 | Implement Moondream2 fallback | Backend Dev | 8 | P1 |
| 1.5 | Model performance benchmarking | ML Engineer | 8 | P1 |
| 1.6 | Create model download/management system | Backend Dev | 12 | P1 |

**Deliverables:**
- `models/` module with abstract base class
- LFM2-VL and Moondream2 implementations
- Benchmark report (speed/accuracy comparison)
- Model auto-download functionality

**Acceptance Criteria:**
- [ ] LFM2-VL loads and processes images <1s on RTX 3060
- [ ] Moondream2 fallback works when LFM2 fails
- [ ] Both models produce valid JSON output
- [ ] VRAM usage stays under 3GB peak

### Sprint 2: Testing Framework

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 2.1 | Set up pytest framework | Backend Dev | 4 | P0 |
| 2.2 | Create test fixtures (sample images/audio/video) | QA | 8 | P0 |
| 2.3 | Unit tests for model abstraction | Backend Dev | 12 | P0 |
| 2.4 | Integration tests for pipeline | Backend Dev | 16 | P0 |
| 2.5 | GitHub Actions CI/CD setup | DevOps | 8 | P1 |
| 2.6 | Code coverage reporting | DevOps | 4 | P1 |

**Deliverables:**
- `tests/` directory with organized test structure
- CI/CD pipeline on GitHub Actions
- 80%+ code coverage for core modules

---

## Phase 2: Backend Core (Weeks 3-4)

### Sprint 3: Pipeline Architecture

**Goals:**
- Refactor monolithic `localcura.py` into modular processors
- Implement proper file type detection
- Add async processing support

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 3.1 | Design processor interface (ABC) | Architect | 4 | P0 |
| 3.2 | Implement FileTypeDetector | Backend Dev | 8 | P0 |
| 3.3 | Refactor ImageProcessor | Backend Dev | 16 | P0 |
| 3.4 | Refactor VideoProcessor with scene detection | Backend Dev | 16 | P0 |
| 3.5 | Create async pipeline orchestrator | Backend Dev | 12 | P0 |
| 3.6 | Implement progress tracking system | Backend Dev | 8 | P1 |

**Deliverables:**
- `processors/` module with specialized classes
- Async pipeline with semaphore-based concurrency control
- Progress callback system for UI updates

**Acceptance Criteria:**
- [ ] All existing file formats still process correctly
- [ ] Pipeline can process 3 files concurrently
- [ ] Progress callbacks fire at 10% intervals
- [ ] Memory usage stable under concurrent load

### Sprint 4: API v2 & Database

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 4.1 | Design new API endpoints | Architect | 4 | P0 |
| 4.2 | Implement SQLite schema | Backend Dev | 8 | P0 |
| 4.3 | Create database models (SQLAlchemy) | Backend Dev | 12 | P0 |
| 4.4 | Implement job persistence | Backend Dev | 16 | P0 |
| 4.5 | Create `/batch` endpoint | Backend Dev | 12 | P0 |
| 4.6 | Implement resume functionality | Backend Dev | 12 | P1 |
| 4.7 | Add configuration API | Backend Dev | 8 | P1 |

**Deliverables:**
- SQLite database with job/item tables
- `/batch` endpoint with job queuing
- Resume capability for interrupted jobs
- Configuration persistence

---

## Phase 3: Frontend Revamp (Weeks 5-6)

### Sprint 5: UI Architecture

**Goals:**
- Modernize plugin UI with component-based architecture
- Implement proper state management
- Add preview mode

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 5.1 | Design new UI mockups | UX Designer | 16 | P0 |
| 5.2 | Set up component structure | Frontend Dev | 8 | P0 |
| 5.3 | Implement PluginStateManager | Frontend Dev | 12 | P0 |
| 5.4 | Create ServerControl component | Frontend Dev | 8 | P0 |
| 5.5 | Create BatchQueue visualizer | Frontend Dev | 16 | P0 |
| 5.6 | Create TagPreview component | Frontend Dev | 16 | P0 |

**Deliverables:**
- New HTML/CSS/JS component structure
- Real-time queue visualization
- Tag preview with confidence scores
- Dark/light theme support

**Acceptance Criteria:**
- [ ] UI renders without console errors
- [ ] Queue shows thumbnails and progress
- [ ] Tag preview updates in real-time
- [ ] Server start/stop has clear visual feedback

### Sprint 6: Settings & Polish

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 6.1 | Create Settings panel UI | Frontend Dev | 12 | P0 |
| 6.2 | Implement settings persistence | Frontend Dev | 8 | P0 |
| 6.3 | Add keyboard shortcuts | Frontend Dev | 8 | P1 |
| 6.4 | Implement theme switching | Frontend Dev | 8 | P1 |
| 6.5 | Add notification/toast system | Frontend Dev | 8 | P1 |
| 6.6 | Error boundary implementation | Frontend Dev | 8 | P1 |

---

## Phase 4: Integration (Weeks 7-8)

### Sprint 7: End-to-End Integration

**Goals:**
- Full plugin + backend integration
- Eagle API testing
- Performance optimization

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 7.1 | Integrate new backend with plugin | Full Stack | 16 | P0 |
| 7.2 | Implement Eagle API error handling | Full Stack | 12 | P0 |
| 7.3 | Add retry logic for failed operations | Full Stack | 8 | P0 |
| 7.4 | Performance profiling and optimization | Backend Dev | 12 | P1 |
| 7.5 | VRAM usage optimization | ML Engineer | 12 | P1 |
| 7.6 | Add circuit breaker pattern | Backend Dev | 8 | P2 |

**Deliverables:**
- Fully integrated system
- Retry/circuit breaker resilience
- Optimized VRAM usage

### Sprint 8: Testing & QA

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 8.1 | End-to-end test scenarios | QA | 16 | P0 |
| 8.2 | Cross-platform testing (Windows) | QA | 12 | P0 |
| 8.3 | Performance benchmarking | QA | 8 | P1 |
| 8.4 | User acceptance testing plan | PM | 8 | P1 |
| 8.5 | Bug fixing sprint | All Dev | 24 | P0 |

**Acceptance Criteria:**
- [ ] All P0 bugs resolved
- [ ] Processing time <1s per image (RTX 3060)
- [ ] No memory leaks over 1000 file batch
- [ ] 95%+ test pass rate

---

## Phase 5: Advanced Features (Weeks 9-10)

### Sprint 9: Duplicate Detection

**Goals:**
- Perceptual hashing for image similarity
- Near-duplicate detection
- Similarity search capabilities

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 9.1 | Research perceptual hashing algorithms | ML Engineer | 8 | P2 |
| 9.2 | Implement pHash/ahash for images | Backend Dev | 12 | P2 |
| 9.3 | Create similarity index (SQLite) | Backend Dev | 12 | P2 |
| 9.4 | Add duplicate detection UI | Frontend Dev | 12 | P2 |
| 9.5 | Batch duplicate scanning | Backend Dev | 12 | P2 |

**Deliverables:**
- Duplicate detection module
- Similarity scoring (0-100%)
- UI for reviewing duplicates

### Sprint 10: Audio Enhancement

**Goals:**
- ML-based audio captioning
- Enhanced audio metadata extraction

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 10.1 | Research audio captioning models | ML Engineer | 8 | P2 |
| 10.2 | Integrate LP-MusicCaps-style model | ML Engineer | 16 | P2 |
| 10.3 | Create audio embedding cache | Backend Dev | 8 | P2 |
| 10.4 | Update AudioProcessor | Backend Dev | 12 | P2 |
| 10.5 | Audio results UI enhancement | Frontend Dev | 8 | P2 |

---

## Phase 6: Release Preparation (Weeks 11-12)

### Sprint 11: Documentation & Packaging

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 11.1 | Write user documentation | Tech Writer | 16 | P0 |
| 11.2 | Create setup/install guide | Tech Writer | 12 | P0 |
| 11.3 | API documentation | Backend Dev | 12 | P1 |
| 11.4 | Create Windows installer | DevOps | 16 | P0 |
| 11.5 | Build release pipeline | DevOps | 12 | P0 |
| 11.6 | Create demo video | Marketing | 16 | P2 |

**Deliverables:**
- `docs/` with user guide, API docs
- Windows .exe installer
- GitHub release automation
- Demo/tutorial video

### Sprint 12: Beta Testing & Launch

**Tasks:**

| ID | Task | Owner | Est. Hours | Priority |
|----|------|-------|------------|----------|
| 12.1 | Beta tester recruitment | PM | 8 | P0 |
| 12.2 | Beta testing program | QA | 16 | P0 |
| 12.3 | Feedback collection & triage | PM | 12 | P0 |
| 12.4 | Final bug fixes | All Dev | 24 | P0 |
| 12.5 | Release candidate | DevOps | 8 | P0 |
| 12.6 | v2.0.0 release | All | 8 | P0 |

**Acceptance Criteria:**
- [ ] 10+ beta testers with positive feedback
- [ ] Zero critical bugs
- [ ] Documentation complete and reviewed
- [ ] All deliverables signed off

---

## Resource Allocation

### Team Structure

| Role | Allocation | Responsibilities |
|------|------------|----------------|
| **Tech Lead/Architect** | 100% | Architecture, code review, technical decisions |
| **Backend Developer** | 100% | API, processors, database, integrations |
| **Frontend Developer** | 75% | Plugin UI, components, state management |
| **ML Engineer** | 50% | Model integration, optimization, audio features |
| **QA Engineer** | 50% | Testing, bug reports, UAT |
| **DevOps** | 25% | CI/CD, packaging, releases |
| **Technical Writer** | 25% | Documentation (Sprint 11) |
| **Project Manager** | 25% | Coordination, beta program, release |

### Hardware Requirements

| Resource | Specification | Quantity | Purpose |
|----------|--------------|----------|---------|
| **Development Workstation** | RTX 3060 12GB, 32GB RAM | 2 | Primary development |
| **Testing Workstation** | RTX 2060 6GB, 16GB RAM | 1 | Low-end testing |
| **CPU-Only Testing** | Modern CPU, 16GB RAM | 1 | Fallback mode testing |
| **Mac Testing** | M1/M2 Mac, 16GB RAM | 1 | macOS compatibility (future) |

---

## Risk Management

### Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LFM2-VL performance below target | Medium | High | Keep Moondream2 as primary, delay LFM2 |
| Eagle API breaking changes | Low | High | Abstract Eagle client, version detection |
| VRAM requirements too high | Medium | Medium | Implement aggressive offloading, CPU fallback |
| Plugin UI performance issues | Medium | Medium | Virtual scrolling, lazy loading |
| Team member unavailable | Low | Medium | Cross-training, pair programming |

### Contingency Plans

**If LFM2-VL doesn't meet performance targets:**
1. Switch to Moondream2 as primary model
2. Keep Qwen2.5-VL-3B as premium option
3. Adjust marketing to emphasize quality over speed

**If VRAM usage exceeds 3GB:**
1. Implement stricter model offloading
2. Add "low VRAM mode" toggle
3. Recommend smaller model variants

---

## Success Metrics

### Development Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Code coverage | >80% | pytest-cov |
| Build success rate | >95% | GitHub Actions |
| Bug escape rate | <5% | Production bugs vs total |
| Documentation coverage | 100% | All features documented |

### Performance Metrics

| Metric | Current | Target v2.0 |
|--------|---------|-------------|
| Image processing time | 2-4s | <1s |
| VRAM peak usage | 6-8GB | <3GB |
| Model load time | 15-30s | <10s |
| Batch processing (100 files) | ~5min | <2min |

### User Experience Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Plugin startup time | <3s | Stopwatch |
| Tag accuracy (user-rated) | >80% | In-app survey |
| NPS score | >40 | Post-install survey |
| Support ticket volume | <5/week | GitHub issues |

---

## Milestone Checkpoints

### Checkpoint 1: End of Phase 1 (Week 2)
**Criteria:**
- [ ] LFM2-VL and Moondream2 models load successfully
- [ ] Basic tests pass
- [ ] CI/CD pipeline operational

### Checkpoint 2: End of Phase 2 (Week 4)
**Criteria:**
- [ ] All processors refactored and tested
- [ ] Database persistence working
- [ ] API v2 fully functional

### Checkpoint 3: End of Phase 3 (Week 6)
**Criteria:**
- [ ] New UI components all functional
- [ ] State management working
- [ ] Settings persistence operational

### Checkpoint 4: End of Phase 4 (Week 8)
**Criteria:**
- [ ] Full integration tested
- [ ] Eagle API integration stable
- [ ] Performance targets met

### Checkpoint 5: End of Phase 5 (Week 10)
**Criteria:**
- [ ] Duplicate detection functional
- [ ] Audio captioning working
- [ ] Beta build ready

### Checkpoint 6: End of Phase 6 (Week 12)
**Criteria:**
- [ ] Documentation complete
- [ ] Beta feedback incorporated
- [ ] v2.0.0 released

---

## Appendix A: Dependencies & External Resources

### Model Downloads

| Model | Source | Size | License |
|-------|--------|------|---------|
| LFM2-VL-1.6B | HuggingFace | ~3GB | Commercial OK |
| Moondream2 | HuggingFace | ~4GB | Apache 2.0 |
| CLIP ViT-L/14 | HuggingFace | ~1.6GB | MIT |
| Aesthetic Predictor | HuggingFace | ~1GB | Unknown |

### External APIs

| API | Purpose | Rate Limits |
|-----|---------|-------------|
| Eagle REST API (local) | Item management | None |
| HuggingFace Hub | Model downloads | 10K/day anonymous |
| GitHub API | Release management | 5K/hour |

---

## Appendix B: Development Environment Setup

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/yourusername/localcura.git
cd localcura

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Download models
python scripts/download_models.py

# 5. Run tests
pytest tests/ -v --cov=backend

# 6. Start development server
python -m uvicorn backend.localcura:app --reload
```

### VS Code Extensions

- Python (Microsoft)
- Pylance
- Python Test Explorer
- autoDocstring
- markdownlint (for docs)
- Prettier

---

**End of Development Plan**
