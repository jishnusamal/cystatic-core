# Factor — Architecture

## What Factor Does

Factor is a **blast-radius and refactor-risk analysis engine** for code changes. Given a PR (or raw diff), it determines which downstream services, endpoints, databases, and queues are impacted, assigns a confidence-weighted verdict, and posts a structured PR comment.

**Core principle:** Evidence-based progressive compression drives the verdict; the LLM is an expert reviewer.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         External Inputs                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ GitHub PR    │  │ GitLab MR    │  │ Direct API (DIFF_ONLY)   │  │
│  │ Webhook      │  │ Webhook      │  │                          │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬──────────────┘  │
└─────────┼─────────────────┼─────────────────────┼─────────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI)                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  api/main.py                                                  │  │
│  │  - Webhook endpoints (GitHub/GitLab)                          │  │
│  │  - Analysis API endpoints                                     │  │
│  │  - Health checks                                              │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
└─────────────────────────────┼─────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Workers (Dramatiq + Redis)                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  workers/analyze_pr.py                                        │  │
│  │  - Receives job from queue                                    │  │
│  │  - Runs orchestrator                                          │  │
│  │  - Posts PR comment                                           │  │
│  │  - Persists results                                           │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
└─────────────────────────────┼─────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Core Engine (Analysis Brain)                     │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Compiler / Pipeline Infrastructure                          │  │
│  │  - PassRegistry: Manages compiler passes                     │  │
│  │  - PassManager: Executes passes with dependencies            │  │
│  │  - Compiler: Orchestrates pass execution                     │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
│                              │                                     │
│  ┌───────────────────────────▼────────────────────────────────┐  │
│  │  Analyzers (9 independent semantic analyzers)               │  │
│  │  ┌────────────┬────────────┬────────────┬──────────────┐   │  │
│  │  │ Surface    │ Signal     │ Coverage   │ Execution     │   │  │
│  │  │ Analyzer   │ Detector   │ Analyzer   │ Analyzer      │   │  │
│  │  ├────────────┼────────────┼────────────┼──────────────┤   │  │
│  │  │ Interaction│ Propagation│ Explain-   │ Context       │   │  │
│  │  │ Analyzer   │ Analyzer   │ ability    │ Builder       │   │  │
│  │  │            │            │ Auditor    │               │   │  │
│  │  └────────────┴────────────┴────────────┴──────────────┘   │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
│                              │                                     │
│  ┌───────────────────────────▼────────────────────────────────┐  │
│  │  Models (Pydantic data structures)                          │  │
│  │  - CompilerPass, Coverage, Evidence, Execution              │  │
│  │  - Interaction, Propagation, Signal, ReviewContext          │  │
│  │  - KnowledgeModel                                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Language Adapters (Static Analysis)              │
│  ┌────────────────────┐              ┌──────────────────────────┐   │
│  │ Python Adapter     │              │ TypeScript Adapter       │   │
│  │ - AST parsing      │              │ - TS/JS parsing          │   │
│  │ - Symbol extraction│              │ - Framework detection    │   │
│  │ - Framework detect │              │ - Type analysis          │   │
│  │  (FastAPI/Flask/   │              │                          │   │
│  │   Django/SQLAlchemy│              │                          │   │
│  └────────────────────┘              └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Source Adapters (VCS Integration)                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  GitHub Adapter                                              │  │
│  │  - github_client.py: Fetch diffs, file snapshots, SHAs       │  │
│  │  - auth.py: Installation auth, JWT, token exchange           │  │
│  │  - bot.py: Post comments to PRs                              │  │
│  │  - event_handler.py: Dispatch webhook events to jobs         │  │
│  │  - comment_formatter.py: Render PR comments                  │  │
│  │  - webhook.py: Parse webhooks + signature validation         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  GitLab Adapter (stub)                                       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Persistence (Tortoise ORM → Postgres)            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  api/models.py                                                │  │
│  │  - organizations, repositories, pull_requests                 │  │
│  │  - analysis_runs, analysis_artifacts                          │  │
│  │  - risk_findings, analysis_comments                           │  │
│  │  - analysis_jobs, feedback_signals                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Observability (Sentry)                           │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  instrumentation/sentry/                                      │  │
│  │  - Middleware for FastAPI                                      │  │
│  │  - Per-request context (repo, PR, run ID)                     │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Overview

### 1. API Layer
**Location:** `api/`

FastAPI service entrypoint that handles:
- GitHub/GitLab webhook events
- Direct analysis API requests
- Health checks and admin endpoints

**Key files:**
- `main.py` — App entrypoint (uvicorn)
- `models.py` — Tortoise ORM models
- `settings.py` — Pydantic configuration
- `admin/urls.py` — Admin routes
- `user/urls.py` — User-facing routes

### 2. Workers & Queue
**Location:** `workers/`

Async job processing using Dramatiq on Redis:
- Receives analysis jobs from queue
- Runs the core engine orchestrator
- Posts PR comments
- Persists results

**Key files:**
- `analyze_pr.py` — Worker entrypoint
- `queue.py` — Dramatiq Redis broker configuration

### 3. Core Engine
**Location:** `core_engine/`

The analysis brain with three main subsystems:

#### Compiler / Pipeline Infrastructure
- **PassRegistry** — Manages compiler passes and their dependencies
- **PassManager** — Executes passes in dependency order
- **Compiler** — Orchestrates pass execution with timing and diagnostics

#### Analyzers (9 independent semantic analyzers)
Each analyzer independently analyzes the codebase and produces structured output:

1. **SurfaceAnalyzer** — Surface-level code metrics and complexity
2. **SignalDetector** — Detects keyword signals and patterns
3. **CoverageAnalyzer** — Test coverage analysis
4. **ExecutionAnalyzer** — Execution path analysis
5. **InteractionAnalyzer** — Component interaction analysis
6. **PropagationAnalyzer** — Impact propagation analysis
7. **ExplainabilityAuditor** — Explainability and audit trail
8. **ContextBuilder** — Builds analysis context from multiple sources

#### Models (Pydantic data structures)
- **CompilerPass** — Compiler pass metadata and results
- **Coverage** — Test coverage data
- **Evidence** — Evidence data structures
- **Execution** — Execution path data
- **Interaction** — Interaction data
- **Propagation** — Propagation data
- **Signal** — Signal detection data
- **ReviewContext** — LLM review context
- **KnowledgeModel** — Knowledge representation

### 4. Language Adapters
**Location:** `language_adapters/`

Per-language static analysis to extract symbols, endpoints, and signals:

- **Python Adapter** — AST parsing, symbol extraction, framework detection (FastAPI, Flask, Django, SQLAlchemy)
- **TypeScript Adapter** — TS/JS parsing, type analysis, framework detection

**Key Design:** Language-specific but produces language-agnostic output format consumed by the core engine.

### 5. Source Adapters
**Location:** `source_adapters/`

Source control integration for fetching diffs and posting results:

- **GitHub Adapter** — Full integration with GitHub API (diffs, file snapshots, PR comments, webhooks, auth)
- **GitLab Adapter** — Stub for future implementation

### 6. Persistence
**Location:** `api/models.py`

Tortoise ORM models for Postgres (Neon):

- **organizations** — Tenant management
- **repositories** — Repo metadata
- **pull_requests** — PR headers
- **analysis_runs** — Analysis execution records
- **analysis_artifacts** — Compressed IR and artifacts
- **risk_findings** — Risk pattern detections
- **analysis_comments** — PR comment storage
- **analysis_jobs** — Queue state and deduplication
- **feedback_signals** — User feedback

### 7. Observability
**Location:** `instrumentation/sentry/`

Sentry integration for error tracking and performance monitoring:
- Middleware attached to FastAPI app
- Per-request context (repository, PR number, analysis run ID)

---

## Data Flow

```
PR Webhook / API Request
    │
    ▼
Source Adapter (GitHub/GitLab)
    │ - Fetch diff
    │ - Fetch file snapshots
    │ - Validate webhook
    │
    ▼
Language Adapter (Python/TypeScript)
    │ - Parse diff
    │ - Extract symbols
    │ - Detect frameworks
    │ - Extract endpoints
    │
    ▼
Core Engine Compiler
    │
    ├─► Pass 1: Surface Analysis
    │   - SurfaceAnalyzer
    │   - SignalDetector
    │
    ├─► Pass 2: Coverage Analysis
    │   - CoverageAnalyzer
    │
    ├─► Pass 3: Execution Analysis
    │   - ExecutionAnalyzer
    │   - InteractionAnalyzer
    │
    ├─► Pass 4: Propagation Analysis
    │   - PropagationAnalyzer
    │
    └─► Pass 5: Explainability
        - ExplainabilityAuditor
        - ContextBuilder
    │
    ▼
Analysis Result
    │
    ├─► Persist to Postgres (Tortoise ORM)
    │
    ├─► Post PR Comment (GitHub/GitLab)
    │
    └─► Return to caller (API response)
```

---

## Key Design Decisions

1. **Compiler/Pass Architecture** — Analysis is organized as compiler passes with explicit dependencies, enabling modular, reusable analysis stages.

2. **Independent Analyzers** — Each analyzer is independent and gracefully degrades on failure. The core engine coordinates but doesn't implement analysis logic.

3. **Language-Agnostic Output** — Language adapters produce a common output format, enabling multi-language support.

4. **Async-First** — Workers use Dramatiq for async job processing, keeping the API responsive.

5. **Full Persistence** — All analysis results are persisted to Postgres for audit trails, historical analysis, and feedback loops.

6. **Observability Built-In** — Sentry integration from the start for production debugging.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| API Framework | FastAPI + Uvicorn |
| ORM | Tortoise ORM |
| Database | PostgreSQL (Neon) |
| Queue | Dramatiq + Redis |
| LLM | OpenAI API (optional) |
| Observability | Sentry |
| Language Analysis | Python AST, TypeScript parser |
| VCS Integration | GitHub API, GitLab API (stub) |

---

## Directory Structure

```
cystatic-core/
├── api/                        FastAPI service
│   ├── main.py                 App entrypoint
│   ├── models.py               Tortoise ORM models
│   ├── settings.py             Configuration
│   ├── admin/urls.py           Admin routes
│   └── user/urls.py            User routes
│
├── core_engine/                Analysis engine
│   ├── pipelines/              Compiler infrastructure
│   │   ├── compiler.py         Compiler orchestration
│   │   ├── pass_manager.py     Pass execution
│   │   ├── registry.py         Pass registry
│   │   └── pipeline.py         Pipeline base
│   ├── analyzers/              Semantic analyzers (9)
│   │   ├── surface_analyzer.py
│   │   ├── signal_detector.py
│   │   ├── coverage_analyzer.py
│   │   ├── execution_analyzer.py
│   │   ├── interaction_analyzer.py
│   │   ├── propagation_analyzer.py
│   │   ├── explainability_auditor.py
│   │   └── context_builder.py
│   └── models/                 Pydantic models
│       ├── compiler_pass.py
│       ├── coverage.py
│       ├── evidence.py
│       ├── execution.py
│       ├── interaction.py
│       ├── propagation.py
│       ├── signal.py
│       ├── review_context.py
│       └── knowledge_model.py
│
├── language_adapters/          Per-language analysis
│   ├── python/                 Python adapter
│   └── typescript/             TypeScript adapter
│
├── source_adapters/            VCS integration
│   ├── github/                 GitHub integration
│   └── gitlab/                 GitLab stub
│
├── workers/                    Async job processing
│   ├── analyze_pr.py           Worker entrypoint
│   └── queue.py                Dramatiq broker
│
├── instrumentation/             Observability
│   └── sentry/                  Sentry integration
│
├── tests/                      Test suite
└── templates/                  PR comment templates
```

---

## Summary

Factor uses a **compiler/pass-based architecture** where analysis is organized as independent, composable passes. The system:

1. Receives PR/webhook events via FastAPI
2. Processes analysis jobs asynchronously via Dramatiq workers
3. Runs compiler passes through 9 independent semantic analyzers
4. Uses language adapters for multi-language static analysis
5. Integrates with GitHub/GitLab for source control
6. Persists all results to Postgres for audit and history
7. Posts structured PR comments with risk analysis

The architecture is designed for **modularity, extensibility, and graceful degradation** — each component can fail independently without breaking the entire system.