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
        A5["POST /analysis"] --> A6["Manual Analysis Router"]
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
        RC["Repository Compiler"]
        CC["Change Compiler"]
        BC["Behavior Compiler"]
        OC["Operational Compiler"]
        DC["Discovery Compiler"]
        RVC["ReviewContext Compiler"]
        LLMC["LLMContext Compiler"]
        
        PL --> LA --> RC
        PL --> CC
        PL --> BC
        PL --> OC
        PL --> DC
        PL --> RVC
        PL --> LLMC
    end
    class Engine,PL,LA,RC,CC,BC,OC,DC,RVC,LLMC engineStyle;

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

The runtime pipeline is orchestrated by the `Pipeline` class located in [`engine/pipeline/pipeline.py`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/engine/pipeline/pipeline.py). It runs sequentially through the following compiler phases:

```mermaid
flowchart TD
    %% Styling Classes
    classDef stepStyle fill:#e8f5e9,stroke:#2e7d32,stroke-width:1px;
    classDef ioStyle fill:#fff3e0,stroke:#f57c00,stroke-width:1px;

    Start(["Git Repository / Diff Payload"]) --> Step1["Step 1: Repository Model Compilation<br/>(Cache via RepositoryStore)"]
    Step1 --> Step2["Step 2: Fetch Diff Data<br/>(Parse hunks & changed files)"]
    Step2 --> Step3["Step 3: Change Compilation<br/>(ChangedSymbolsPass + Classification)"]
    Step3 --> Step4["Step 4: Behavior Compilation<br/>(Trace call graphs to entry points)"]
    Step4 --> Step5["Step 5: Operational Compilation<br/>(DB schema, Event pub/sub, API contract checks)"]
    Step5 --> Step6["Step 6: Engineering Discovery Model<br/>(Project findings to intermediate representation)"]
    Step6 --> Step7["Step 7: Discovery IR Compilation<br/>(Deep rule-based analysis passes)"]
    Step7 --> Step8["Step 8: ReviewContext Compilation<br/>(Assemble evidence & raw diffs)"]
    Step8 --> Step9["Step 9: LLMContext Compilation<br/>(Compress tokens & dictionary-encode StringTable)"]
    Step9 --> End(["LLM-Ready Context Package"])

    class Start,End ioStyle;
    class Step1,Step2,Step3,Step4,Step5,Step6,Step7,Step8,Step9 stepStyle;
```

### Compiler Phase Details

| Phase | Component | Key Operations & Outputs |
| :--- | :--- | :--- |
| **Step 1** | `RepositoryCompiler` | Fetches code tree snapshots for base and head references. Detects language adapter (**Python**, **Java**, or **TypeScript**) and parses syntax trees (ASTs/Tree-sitter) into a unified `RepositoryModel`. Caches compiled repositories in `RepositoryStore`. |
| **Step 2** | `DiffFetcher` | Extracts diff hunks, matching line changes back to files and symbol scopes. |
| **Step 3** | `ChangeCompiler` | Computes semantic deltas using `ChangedSymbolsPass` (detects added, modified, or removed symbols) and `ChangeClassificationPass` (categorizes mutations such as method signature, body, visibility, or decorators). |
| **Step 4** | `BehaviorCompiler` | Traces downstream caller-callee execution chains starting from changed symbols to identify impacted paths and entry points. |
| **Step 5** | `OperationalCompiler` | Enriches findings with domain-specific analysis passes:<br/>- **API Pass:** Detects alterations or breakages in HTTP contracts.<br/>- **Data Pass:** Tracks changes to database schemas, models, or active query structures.<br/>- **Event Pass:** Traces publish/subscribe updates. |
| **Step 6 & 7** | `DiscoveryCompiler` | Normalizes findings into a canonical `EngineeringDiscoveryModel` and runs rule-based analysis passes to extract boundary-crossing transfers, state mutations, shared dependencies, and validation gaps. |
| **Step 8 & 9** | `LLMContextCompiler` | Bundles findings into a compact `LLMContext` via discovery-centered build orders. Applies token compression, including enum ID encoding, location normalization, duplicate label elimination, and **dead-string elimination** (removing unreferenced string table entries). |

---

## 3. Directory Layout & Module Roles

```
cystatic-core/
├── api/                         # FastAPI Application Layer
│   ├── routes/                  # Routers (/health, /github webhook, manual /analysis)
│   ├── schemas/                 # Pydantic verification and validation schemas
│   ├── deps.py                  # Dependency injection utilities
│   └── main.py                  # API application initialization
│
├── core/                        # Core System & Runtime Utilities
│   ├── config.py                # Environment configurations (pydantic-settings)
│   ├── db.py                    # Database connection pool setup
│   ├── errors.py                # System-wide custom exception definitions
│   ├── logging.py               # Time logging & execution tracing
│   ├── profile.py               # MemoryProfiler (RSS & tracemalloc)
│   └── runtime.py               # Runtime context manager
│
├── engine/                      # Core Analysis & Compilation Engine
│   ├── pipeline/                # Runtime pipeline orchestrator and context
│   │   ├── pipeline.py          # Pipeline manager (executes the 9 compiler phases)
│   │   └── context.py           # Tracks pipeline state, timing, and errors
│   ├── language/                # Source code parsing & Language adapters
│   │   ├── base/                # Abstract compiler framework, normalization, and visitors
│   │   ├── python/              # Python adapter parsing (standard AST extractors)
│   │   ├── java/                # Java adapter parsing (Tree-sitter parser)
│   │   ├── typescript/          # TypeScript adapter parsing
│   │   └── detection.py         # Automatic language detection factory
│   ├── repository/              # Repository model declarations and caching
│   │   ├── model/               # Dataclass entities (symbols, graphs, persistence, events)
│   │   └── indexing/            # Caching and indexing layer (RepositoryStore)
│   ├── change/                  # ChangeCompiler (changed symbols & classification passes)
│   ├── behavior/                # BehaviorCompiler (impacted control flows & call graphs)
│   ├── operational/             # OperationalCompiler (API/DB/Event passes)
│   ├── discovery/               # DiscoveryCompiler (projects to Discovery IR model)
│   ├── review_context/          # ReviewContextCompiler (compiles target review details)
│   └── llm_context/             # LLMContextCompiler (compresses context for the LLM)
│
├── integrations/                # Pluggable Platform Integrations
│   ├── base/                    # Platform-agnostic interfaces (Repository, Event, Output)
│   └── github/                  # GitHub VCS implementations & comment/JSON renderers
│
├── models/                      # SQLAlchemy & system-wide Pydantic data models
├── repositories/                # Database service layer for indexed documents
├── workers/                     # Background workers for processing queued analyses
└── tests/                       # Complete pytest suite
```

---

## 4. Key Architectural Patterns

### Pluggable Provider Pattern
External platforms are abstracted behind interfaces defined in [`integrations/base/`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/integrations/base/). The compiler engine operates entirely on these interfaces (e.g. `RepositoryProvider`), meaning integration with new platforms (like GitLab, Bitbucket, or self-hosted VCS) requires no modifications to the core analysis engine.

### Deterministic & Immutable Models
To prevent side effects across compiler passes, all data structures produced throughout the compilation pipeline are designed as frozen, immutable dataclasses. The pipeline guarantees that given the same input `ReviewContext`, the output `LLMContext` is 100% deterministic and reproducible.

### Isolated Language Parsers
Language-specific features are normalized by language adapters in [`engine/language/`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/engine/language/) into a language-agnostic representation. Downstream compilers (Change, Behavior, Operational) consume this normalized abstract syntax map, isolating them from syntactic quirks of individual programming languages.

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
