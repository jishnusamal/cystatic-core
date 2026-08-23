# Factor System & Compiler Architecture

Factor is a high-performance **blast-radius and refactor-risk analysis engine** for code changes. Given a pull request (or a raw git diff), it evaluates downstream impacts on API endpoints, databases, message queues, and event subscriptions. It compiles behavioral and operational change indicators, then packages a token-efficient context for an LLM to produce a final, confidence-weighted review verdict.

---

## 1. System Architecture

```mermaid
flowchart TB
    %% Styling Classes
    classDef apiStyle fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef integrationStyle fill:#efebe9,stroke:#5d4037,stroke-width:2px;
    classDef engineStyle fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef outputStyle fill:#fff3e0,stroke:#f57c00,stroke-width:2px;

    subgraph API [API Layer - FastAPI]
        direction TB
        A1["GET /health"] --> A2["Health Check"]
        A3["POST /github"] --> A4["GitHub Webhook Router"]
        A5["GET /"] --> A6["Root & Version Info"]
    end
    class API,A1,A2,A3,A4,A5,A6 apiStyle;

    subgraph Integration [Integration Layer]
        direction TB
        IR["IntegrationRegistry"] --> RP["RepositoryProvider"]
        IR --> EP["EventProvider"]
        IR --> IP["InstallationProvider"]
        IR --> OP["OutputProvider"]
        GI["GitHub Integration"] --> GRP["GitHubRepositoryProvider"]
        GI --> GWP["GitHubWebhookProvider"]
        GI --> GCP["GitHubCommentProvider"]
    end
    class Integration,IR,RP,EP,IP,OP,GI,GRP,GWP,GCP integrationStyle;

    subgraph Engine [Analysis & Compilation Engine]
        direction TB
        PL["Pipeline Orchestrator"]
        LA["Language Detection & Adapters"]
        RI["Repository Indexer"]
        RS["Repository Store (SQLite)"]
        MAT["Repository Materializer"]
        RO["Repository Overlay"]
        RV["Repository View"]
        CC["Change Compiler"]
        BC["Behavior Compiler"]
        OC["Operational Compiler"]
        EDC["EngineeringDiscovery Compiler"]
        DC["Discovery Compiler"]
        RVC["ReviewContext Compiler"]
        LLMC["LLMContext Compiler"]

        PL --> LA --> RI
        RI --> RS
        MAT --> RS
        RI --> RO
        RS --> RV
        RO --> RV
        RV --> CC
        PL --> CC
        PL --> BC
        PL --> OC
        PL --> EDC
        PL --> DC
        PL --> RVC
        PL --> LLMC
    end
    class Engine,PL,LA,RI,RS,MAT,RO,RV,CC,BC,OC,EDC,DC,RVC,LLMC engineStyle;

    subgraph Output [Rendering & Publishing]
        direction TB
        JR["JSONRenderer"]
        GR["GitHubRenderer"]
        LR["LLMContextRenderer"]
    end
    class Output,JR,GR,LR outputStyle;

    API --> Integration
    Integration --> Engine
    Engine --> Output
```

---

## 2. The 9-Step Compilation Pipeline

The runtime pipeline is orchestrated by the `Pipeline` class located in [`engine/pipeline/pipeline.py`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/engine/pipeline/pipeline.py). The canonical stage ordering is defined in [`engine/pipeline/stages.py`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/engine/pipeline/stages.py). It runs sequentially through the following compiler phases:

```mermaid
flowchart TD
    %% Styling Classes
    classDef stepStyle fill:#e8f5e9,stroke:#2e7d32,stroke-width:1px;
    classDef ioStyle fill:#fff3e0,stroke:#f57c00,stroke-width:1px;

    Start(["Git Repository / Diff Payload"]) --> Step1["Step 1: Repository Fact & Overlay Compilation<br/>(Cache via RepositoryStore / RepositoryView)"]
    Step1 --> Step2["Step 2: Fetch Diff Data<br/>(Parse hunks & changed files)"]
    Step2 --> Step3["Step 3: Change Compilation<br/>(ChangedSymbolsPass + Classification)"]
    Step3 --> Step4["Step 4: Behavior Compilation<br/>(Trace call graphs to entry points)"]
    Step4 --> Step5["Step 5: Operational Compilation<br/>(DB schema, Event pub/sub, API contract checks)"]
    Step5 --> Step6["Step 6: Engineering Discovery Compilation<br/>(Project OCM into EngineeringDiscoveryModel)"]
    Step6 --> Step7["Step 7: Discovery IR Compilation<br/>(Deep rule-based passes to DiscoveryIR)"]
    Step7 --> Step8["Step 8: ReviewContext Compilation<br/>(Assemble evidence & raw diffs)"]
    Step8 --> Step9["Step 9: LLMContext Compilation<br/>(Compress tokens & dictionary-encode StringTable)"]
    Step9 --> End(["LLM-Ready Context Package"])

    class Start,End ioStyle;
    class Step1,Step2,Step3,Step4,Step5,Step6,Step7,Step8,Step9 stepStyle;
```

### Compiler Phase Details

| Phase | Component | Key Operations & Outputs |
| :--- | :--- | :--- |
| **Step 1** | `RepositoryIndexer`, `RepositoryStore`, `RepositoryMaterializer`, `RepositoryOverlay`, `RepositoryView` | Resolves base version facts from `SQLiteRepositoryStore` (or indexes base repository snapshot on-demand using `RepositoryIndexer` and persists to store). Uses `RepositoryMaterializer` to lazily fetch and index only the paths required by downstream compilers within a `MaterializationBudget`. Extracts head version files changed in the PR diff, indexes them, and constructs a `RepositoryOverlay`. Wraps the base query and overlay in a `RepositoryView` to present a unified `RepositoryQuery` interface for subsequent phases without materializing a full repository in memory. |
| **Step 2** | `DiffFetcher` | Extracts diff hunks, matching line changes back to files and symbol scopes. |
| **Step 3** | `ChangeCompiler` | Computes semantic deltas using `ChangedSymbolsPass` (detects added, modified, or removed symbols) and `ChangeClassificationPass` (categorizes mutations such as method signature, body, visibility, or decorators). |
| **Step 4** | `BehaviorCompiler` | Traces downstream caller-callee execution chains starting from changed symbols to identify impacted paths and entry points. Runs sub-passes for behavior graph construction, entry point detection, execution chain tracing, reachable unit resolution, and shared execution detection. |
| **Step 5** | `OperationalCompiler` | Enriches findings with domain-specific analysis passes:<br/>- **API Pass:** Detects alterations or breakages in HTTP contracts.<br/>- **Data Pass:** Tracks changes to database schemas, models, or active query structures.<br/>- **Event Pass:** Traces publish/subscribe updates.<br/>- **Dependency, Validation, Metrics, Model Composition passes** for additional operational signals. Produces `OperationalChangeModel` (OCM). |
| **Step 6** | `EngineeringDiscoveryCompiler` | Projection-only pass that transforms the `OperationalChangeModel` into a structured `EngineeringDiscoveryModel` (EDM). Extracts execution-oriented abstractions such as API surfaces, data interactions, event flows, dependency graphs, and validation coverage. |
| **Step 7** | `DiscoveryCompiler` (from `engine/operational/discovery/`) | Executes deep rule-based analysis passes on the `EngineeringDiscoveryModel` to produce `DiscoveryIR`. Passes include: `HiddenRelationshipPass`, `DominantExecutionPass`, `BoundaryInvariantPass`, `ValidationGapPass`, `SharedExecutionPass`, and `CompressionPass`. Each pass emits `Discovery` objects with complete natural-language statements backed by structured evidence. |
| **Step 8** | `ReviewContextCompiler` | Selects and normalizes compiler outputs into a stable `ReviewContext`. Runs four deterministic stages: Selection → Normalization → Discovery Assembly (from DiscoveryIR) → Reference Assembly. Performs no graph traversal, no re-discovery, and no prose generation. |
| **Step 9** | `LLMContextCompiler` | Transforms `ReviewContext` into a compact `LLMContext` via a discovery-centred build order. Applies token compression: enum ID encoding, location normalization, duplicate label elimination, execution chain DAG deduplication, intermediate chain compression, and **dead-string elimination** (removing unreferenced string table entries). |

---

## 3. Directory Layout & Module Roles

```
cystatic-core/
├── api/                         # FastAPI Application Layer
│   ├── routes/                  # Routers (/health, /github webhook)
│   ├── deps.py                  # Dependency injection utilities
│   └── main.py                  # API application initialization & memory middleware
│
├── core/                        # Core System & Runtime Utilities
│   ├── config.py                # Environment configurations (pydantic-settings)
│   ├── db.py                    # Database connection pool setup
│   ├── errors.py                # System-wide custom exception definitions
│   ├── logging.py               # Time logging & execution tracing
│   ├── profile.py               # MemoryProfiler (RSS & tracemalloc)
│   └── runtime.py               # Runtime context manager & PREVENT_LEGACY_ARCHITECTURE guard
│
├── engine/                      # Core Analysis & Compilation Engine
│   ├── pipeline/                # Runtime pipeline orchestrator and context
│   │   ├── pipeline.py          # Pipeline manager (executes the 9 compiler phases)
│   │   ├── context.py           # Tracks pipeline state, timing, and errors (PipelineContext)
│   │   └── stages.py            # Stage enum defining canonical pipeline ordering
│   ├── language/                # Source code parsing & Language adapters
│   │   ├── base/                # Abstract compiler framework, normalization, and visitors
│   │   ├── python/              # Python adapter parsing (standard AST extractors)
│   │   ├── java/                # Java adapter parsing (Tree-sitter parser)
│   │   ├── typescript/          # TypeScript adapter parsing
│   │   ├── detection.py         # Automatic language detection factory
│   │   ├── registry.py          # LanguageRegistry for adapter lookup and registration
│   │   └── builtins.py          # Default language registry factory
│   ├── repository/              # Fact-based Repository Architecture
│   │   ├── facts/               # Lightweight semantic entities (Symbol, Call, Endpoint, DB/Event facts, IDs)
│   │   ├── query/               # Abstract RepositoryQuery interface and InMemoryRepository fallback
│   │   ├── store/               # SQLiteRepositoryStore backend for persistent version facts and schema definition
│   │   ├── indexing/            # RepositoryIndexer parsing and indexing facts into sinks (InMemory/PersistentFactSink)
│   │   ├── overlay/             # RepositoryOverlay (PR diff mutations) and RepositoryView (layered query scope)
│   │   ├── materialization/     # RepositoryMaterializer, MaterializationBudget, FullIndexMaterializer
│   │   ├── resolver/            # Resolver planner, frontier, outcome, and context for demand-driven fact resolution
│   │   ├── metrics.py           # RepositoryMaterializationMetrics tracking files/bytes materialized
│   │   ├── compiler.py          # Repository compilation entry point
│   │   └── model/               # Legacy RepositoryGraph & RepositoryModel structures (guarded from construction)
│   ├── change/                  # ChangeCompiler (changed symbols & classification passes)
│   ├── behavior/                # BehaviorCompiler (impacted control flows & call graphs)
│   │   └── compiler/passes/     # Sub-passes: behavior_graph, entry_point, execution_chain,
│   │                            #             reachable_units, shared_execution, terminal_point
│   ├── operational/             # OperationalCompiler (API/DB/Event/Dependency/Validation passes)
│   │   ├── compiler/            # OperationalCompiler + EngineeringDiscoveryCompiler
│   │   └── discovery/           # DiscoveryCompiler → DiscoveryIR (deep rule-based passes)
│   ├── discovery/               # Standalone DiscoveryCompiler → DiscoveryModel (deterministic passes)
│   ├── review_context/          # ReviewContextCompiler + ReviewScopeBuilder
│   └── llm_context/             # LLMContextCompiler (compresses ReviewContext to LLMContext)
│
├── integrations/                # Pluggable Platform Integrations
│   ├── base/                    # Platform-agnostic interfaces (RepositoryProvider, EventProvider,
│   │                            #   InstallationProvider, OutputProvider) + IntegrationRegistry
│   └── github/                  # GitHub VCS implementations, auth, webhooks, comment/JSON renderers
│
├── models/                      # SQLAlchemy & system-wide Pydantic data models
├── repositories/                # Database service layer for indexed documents
├── workers/                     # Background workers: analyze_pr.py (PR analysis task), queue.py
└── tests/                       # Complete pytest suite
```

---

## 4. Key Architectural Patterns

### Pluggable Provider Pattern
External platforms are abstracted behind interfaces defined in [`integrations/base/`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/integrations/base/). The `IntegrationRegistry` manages named provider registrations so that the compiler engine operates entirely on abstract interfaces (e.g. `RepositoryProvider`). Integrating new platforms (like GitLab, Bitbucket, or self-hosted VCS) requires no modifications to the core analysis engine.

### Deterministic & Immutable Models
To prevent side effects across compiler passes, all data structures produced throughout the compilation pipeline are designed as frozen, immutable dataclasses. The pipeline guarantees that given the same input `ReviewContext`, the output `LLMContext` is 100% deterministic and reproducible.

### Isolated Language Parsers
Language-specific features are parsed by language adapters in [`engine/language/`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/engine/language/) and emitted as normalized, language-agnostic repository facts (symbols, calls, references, database entries, events, etc.). Downstream compilers query the repository and overlays via the `RepositoryQuery` and `RepositoryView` interfaces, completely isolating them from syntactic quirks of individual programming languages.

### Fact-Based Repository View Pattern
To scale the engine to repositories with thousands of files and millions of lines of code without incurring massive memory overhead (which previously caused 3.4+ GB memory peaks), the repository is represented as a set of lightweight, queryable facts stored in a persistent `SQLiteRepositoryStore`.
- **Base Version Facts**: Fully indexed facts (symbols, calls, imports, type dependencies, endpoints, database entities, events) are cached in SQLite.
- **Demand-Driven Materialization**: A `RepositoryMaterializer` fetches and indexes only the file paths demanded by downstream compilers, governed by a `MaterializationBudget` (file count and byte caps). A `FullIndexMaterializer` handles full-repository indexing when a cold cache must be primed.
- **PR Overlay**: During analysis, only the files added or modified in the pull request diff are indexed on the fly. Their facts are collected in a `RepositoryOverlay`.
- **Dynamic View**: A `RepositoryView` merges the base database facts with the `RepositoryOverlay` in memory, presenting a unified `RepositoryQuery` interface. This allows downstream compilers to resolve call graphs and operational surfaces dynamically, without ever loading the entire code tree or constructing full in-memory graph objects.
- **Architectural Guard**: In production PR-analysis runs, the runtime sets `PREVENT_LEGACY_ARCHITECTURE` to `True` via a ContextVar. Any attempt to construct legacy in-memory objects (like `RepositoryGraph`, `RepositoryModel`, or `GraphPatcher`) immediately raises a runtime error to prevent memory regressions.

### Two-Phase Discovery
The pipeline uses two distinct discovery compilers operating on different abstractions:
1. **`EngineeringDiscoveryCompiler`** (Step 6): A projection-only pass that transforms the `OperationalChangeModel` into an `EngineeringDiscoveryModel` — a structured, execution-oriented representation of API surfaces, data interactions, event flows, and validation coverage.
2. **`DiscoveryCompiler`** (Step 7, from `engine/operational/discovery/`): Executes rule-based analysis passes on the `EngineeringDiscoveryModel` to produce `DiscoveryIR` — structured `Discovery` objects with complete natural-language statements and evidence references consumed by the `ReviewContextCompiler`.

A separate, standalone `DiscoveryCompiler` in `engine/discovery/` operates on the `OperationalChangeModel` directly and produces a `DiscoveryModel` — used in contexts where the full engineering projection is not required.

### Graceful Degradation
Analysis and operational passes run independently. If a highly complex database parse or event subscription extraction fails, the pipeline isolates the error and degrades gracefully, allowing standard symbol change and control flow tracing to proceed uninterrupted.

---

## 5. Performance and Resource Monitoring

Factor runs a built-in diagnostics system for tracking system footprint, defined in [`core/profile.py`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/core/profile.py):

> [!NOTE]
> **MemoryProfiler** (`core/profile.py`)
> - Tracks real-time Process RSS usage (using `psutil`) sampled on a background thread every 5ms.
> - Tracks precise heap allocation diagnostics via Python's `tracemalloc` to trace memory usage back to specific files and line numbers.
> - Dumps structured diagnostics (`memory_checkpoints.json`) into the log directory for profiling execution runs and identifying memory growth patterns.

The `api/main.py` middleware additionally logs per-request RSS deltas and duration for every non-health endpoint, providing continuous operational visibility into memory growth from individual requests.

The `engine/repository/metrics.py` module tracks `RepositoryMaterializationMetrics` — recording materialized vs. total repository file/byte counts for each run, enabling precise measurement of how much of the codebase was touched during analysis.
