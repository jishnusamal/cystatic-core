# Factor — Architecture

## What Factor Does

Factor is a **blast-radius and refactor-risk analysis engine** for code changes. Given a PR (or raw diff), it determines which downstream services, endpoints, databases, and queues are impacted, assigns a confidence-weighted verdict, and posts a structured PR comment.

**Core principle:** Evidence-based progressive compression drives the verdict; the LLM is an expert reviewer.

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Source Adapters (VCS)                              │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────┐  │
│  │ GitHub Adapter       │  │ GitLab Adapter (stub) │  │ Direct API     │  │
│  │ - github_client.py   │  │                       │  │ (future)       │  │
│  │ - auth.py            │  │                       │  │                │  │
│  │ - bot.py             │  │                       │  │                │  │
│  │ - event_handler.py   │  │                       │  │                │  │
│  │ - webhook.py         │  │                       │  │                │  │
│  └──────────┬───────────┘  └───────────────────────┘  └────────────────┘  │
└─────────────┼────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Language Adapters (Static Analysis)                    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  BaseLanguageAdapter (abstract)                                  │    │
│  │  ┌──────────────────────┐  ┌──────────────────────────────────┐  │    │
│  │  │ PythonAdapter        │  │ JavaAdapter                      │  │    │
│  │  │ - AST parsing        │  │ - Java parser                    │  │    │
│  │  │ - Framework detect   │  │ - Framework detect               │  │    │
│  │  │   (FastAPI/Flask/    │  │   (Spring Boot/JPA)              │  │    │
│  │  │    Django/SQLAlchemy)│  │                                  │  │    │
│  │  └──────────┬───────────┘  └──────────────────────────────────┘  │    │
│  │             │                                                     │    │
│  │             ▼                                                     │    │
│  │  ┌──────────────────────────────────────────────────────────┐    │    │
│  │  │  ModelCompiler (11 passes)                               │    │    │
│  │  │  Pass 1:  Symbol Collection                              │    │    │
│  │  │  Pass 2:  Reference Resolution (imports)                 │    │    │
│  │  │  Pass 3:  Call Graph                                     │    │    │
│  │  │  Pass 4:  Endpoint Discovery                             │    │    │
│  │  │  Pass 5:  Type Relationships                             │    │    │
│  │  │  Pass 6:  Async Entry Points                             │    │    │
│  │  │  Pass 7:  Persistence Models                             │    │    │
│  │  │  Pass 8:  Repository Methods                             │    │    │
│  │  │  Pass 9:  Event Constructs                               │    │    │
│  │  │  Pass 10: Test Definitions                               │    │    │
│  │  │  Pass 11: Configuration References                       │    │    │
│  │  └──────────────────────┬───────────────────────────────────┘    │    │
│  └─────────────────────────┼────────────────────────────────────────┘    │
└────────────────────────────┼─────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Compilation Pipeline (4 Phases)                        │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Phase 1: Repository Compilation                                 │    │
│  │  ┌──────────────────────────────────────────────────────────┐    │    │
│  │  │  Input:  Semantic graph (file_path → extracted data)     │    │    │
│  │  │  Output: RepositoryModel                                 │    │    │
│  │  │  ─ symbols (functions, classes, methods, imports)        │    │    │
│  │  │  ─ call_graph (caller → callee edges)                    │    │    │
│  │  │  ─ reference_graph (import resolution edges)             │    │    │
│  │  │  ─ type_relationship_graph (inheritance, composition)    │    │    │
│  │  │  ─ entry_points (REST endpoints)                         │    │    │
│  │  │  ─ async_entry_points (workers, queues)                  │    │    │
│  │  │  ─ persistence_models (ORM models, tables)               │    │    │
│  │  │  ─ repository_methods (data access methods)              │    │    │
│  │  │  ─ event_constructs (publish/subscribe)                  │    │    │
│  │  │  ─ test_definitions (test functions, classes)            │    │    │
│  │  │  ─ configuration_references (env vars, config)           │    │    │
│  │  └──────────────────────────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Phase 2: Change Compilation                                    │    │
│  │  ┌──────────────────────────────────────────────────────────┐    │    │
│  │  │  Input:  diff_data + old RepositoryModel + new            │    │    │
│  │  │          RepositoryModel                                  │    │    │
│  │  │  Output: ChangeModel                                      │    │    │
│  │  │  ─ added_symbols, removed_symbols                         │    │    │
│  │  │  ─ modified_symbols (with classified changes)             │    │    │
│  │  │  ─ changed_imports                                        │    │    │
│  │  │  ─ changed_endpoints                                      │    │    │
│  │  │  Passes:                                                  │    │    │
│  │  │    1. ChangedSymbolsPass                                  │    │    │
│  │  │    2. ChangeClassificationPass                            │    │    │
│  │  └──────────────────────────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Phase 3: Behavior Compilation                                  │    │
│  │  ┌──────────────────────────────────────────────────────────┐    │    │
│  │  │  Input:  ChangeModel + RepositoryModel                    │    │    │
│  │  │  Output: BehaviorModel                                    │    │    │
│  │  │  ─ behaviors (affected behaviors with confidence)         │    │    │
│  │  │  ─ execution_graphs (control flow paths)                  │    │    │
│  │  │  Passes:                                                  │    │    │
│  │  │    1. BehaviorDiscoveryPass                               │    │    │
│  │  │    2. BehaviorGraphPass                                   │    │    │
│  │  └──────────────────────────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Phase 4/5: Operational Compilation                             │    │
│  │  ┌──────────────────────────────────────────────────────────┐    │    │
│  │  │  Input:  RepositoryModel + ChangeModel + BehaviorModel    │    │    │
│  │  │  Output: OperationalChangeModel                           │    │    │
│  │  │  ─ repository (Phase 1)                                   │    │    │
│  │  │  ─ change (Phase 2)                                       │    │    │
│  │  │  ─ behavior (Phase 3)                                     │    │    │
│  │  │  ─ dependency (Phase 5)                                   │    │    │
│  │  │  ─ data (Phase 5)                                         │    │    │
│  │  │  ─ event (Phase 5)                                        │    │    │
│  │  │  ─ api (Phase 5)                                          │    │    │
│  │  │  ─ validation (Phase 5)                                   │    │    │
│  │  │  ─ metrics (Phase 5)                                      │    │    │
│  │  │  Passes:                                                  │    │    │
│  │  │  Phase 4:                                                 │    │    │
│  │  │    1. ModelCompositionPass                                │    │    │
│  │  │    2. ConsistencyValidationPass                           │    │    │
│  │  │  Phase 5:                                                 │    │    │
│  │  │    3. DependencyAnalysisPass                              │    │    │
│  │  │    4. DataAnalysisPass                                    │    │    │
│  │  │    5. EventAnalysisPass                                   │    │    │
│  │  │    6. APIAnalysisPass                                     │    │    │
│  │  │    7. ValidationAnalysisPass                              │    │    │
│  │  │    8. MetricsPass                                         │    │    │
│  │  └──────────────────────────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Observability (Sentry)                                 │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  instrumentation/sentry/                                         │    │
│  │  - Sentry integration for error tracking                         │    │
│  │  - Per-request context (repo, PR, run ID)                        │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Compilation Pipeline Overview

The system uses a **4-phase compilation pipeline** where each phase produces a deterministic model consumed by the next:

| Phase | Name | Input | Output | Compiler |
|-------|------|-------|--------|----------|
| 1 | Repository | Semantic graph | `RepositoryModel` | `ModelCompiler` |
| 2 | Change | Diff + old/new RepositoryModels | `ChangeModel` | `ChangeCompiler` |
| 3 | Behavior | ChangeModel + RepositoryModel | `BehaviorModel` | `BehaviorCompiler` |
| 4/5 | Operational | RepositoryModel + ChangeModel + BehaviorModel | `OperationalChangeModel` | `OperationalCompiler` |

Each phase is implemented as a **compiler** that orchestrates a sequence of **passes**. Passes are executed in order, with each pass transforming a shared **context** object that accumulates state.

---

## Phase 1: Repository Compilation

**Location:** `language_adapters/base/compiler.py`
**Compiler:** `ModelCompiler`

Transforms a language-agnostic **semantic graph** (produced by language-specific extractors) into a complete `RepositoryModel`.

### Input
A `dict[file_path, file_data]` where each `file_data` contains extracted semantic elements:
- `functions`, `classes`, `imports`
- `function_calls`, `rest_endpoints`
- `type_relationships`, `async_entry_points`
- `persistence_models`, `repository_methods`
- `event_constructs`, `test_definitions`
- `configuration_references`

### Output: `RepositoryModel`
A frozen dataclass containing:
- `symbols: frozenset[Symbol]` — All symbols (functions, classes, methods, imports)
- `call_graph: CallGraph` — Caller → callee edges
- `reference_graph: ReferenceGraph` — Import resolution edges
- `type_relationship_graph: TypeRelationshipGraph` — Inheritance, composition edges
- `entry_points: tuple[EntryPoint]` — REST endpoints
- `async_entry_points: tuple[AsyncEntryPoint]` — Workers, queue consumers
- `persistence_models: tuple[PersistenceModel]` — ORM models, tables
- `repository_methods: tuple[RepositoryMethod]` — Data access methods
- `event_constructs: tuple[EventConstruct]` — Publish/subscribe constructs
- `test_definitions: tuple[TestDefinition]` — Test functions and classes
- `configuration_references: tuple[ConfigurationReference]` — Config key references

### 11 Compiler Passes
1. **Symbol Collection** — Collects all symbols (functions, classes, methods, imports) from file data
2. **Reference Resolution** — Resolves import statements to their target symbols
3. **Call Graph** — Builds caller → callee edges from function call data
4. **Endpoint Discovery** — Creates EntryPoint objects from REST endpoint data
5. **Type Relationships** — Builds inheritance and composition edges
6. **Async Entry Points** — Processes worker/queue entry points
7. **Persistence Models** — Processes ORM model definitions
8. **Repository Methods** — Processes data access methods
9. **Event Constructs** — Processes publish/subscribe constructs
10. **Test Definitions** — Processes test functions and classes
11. **Configuration References** — Processes config key references

---

## Phase 2: Change Compilation

**Location:** `change/compiler/compiler.py`
**Compiler:** `ChangeCompiler`

Compares old and new `RepositoryModel` snapshots against a git diff to produce a `ChangeModel` describing exactly what changed.

### Input
- `diff_data: dict[str, Any]` — Git diff data (file changes, hunks)
- `old_repository_model: RepositoryModel` — Before the change
- `new_repository_model: RepositoryModel` — After the change

### Output: `ChangeModel`
A frozen dataclass containing:
- `added_symbols: tuple[Symbol]` — Newly added symbols
- `removed_symbols: tuple[Symbol]` — Deleted symbols
- `modified_symbols: tuple[ModifiedSymbol]` — Changed symbols with classified changes
- `changed_imports: tuple[ImportChange]` — Import statement changes
- `changed_endpoints: tuple[EndpointChange]` — Endpoint route/method changes

### Change Types (classified per symbol)
- `FunctionBodyChange` — Function implementation changed
- `SignatureChange` — Function signature changed
- `VisibilityChange` — Public/private changed
- `DecoratorChange` — Decorators added/removed
- `SuperclassChange` — Class inheritance changed
- `InterfaceChange` — Interface implementation changed
- `EndpointAnnotationChange` — Route/method annotation changed

### Passes
1. **ChangedSymbolsPass** — Identifies added, removed, and modified symbols by comparing old/new models
2. **ChangeClassificationPass** — Classifies the type of change for each modified symbol

---

## Phase 3: Behavior Compilation

**Location:** `behavior/compiler/compiler.py`
**Compiler:** `BehaviorCompiler`

Transforms the `ChangeModel` and `RepositoryModel` into a `BehaviorModel` that describes what behaviors are affected by the change.

### Input
- `change_model: ChangeModel` — From Phase 2
- `repository_model: RepositoryModel` — From Phase 1

### Output: `BehaviorModel`
A frozen dataclass containing:
- `behaviors: tuple[Behavior]` — Affected behaviors with confidence scores
- `execution_graphs: tuple[ExecutionGraph]` — Control flow paths through affected code

### Passes
1. **BehaviorDiscoveryPass** — Discovers affected behaviors from changed symbols
2. **BehaviorGraphPass** — Builds execution graphs showing how changes propagate

---

## Phase 4/5: Operational Compilation

**Location:** `operational/compiler/compiler.py`
**Compiler:** `OperationalCompiler`

Composes all deterministic models into a single `OperationalChangeModel` and enriches it with operational analysis.

### Input
- `repository_model: RepositoryModel` — From Phase 1
- `change_model: ChangeModel` — From Phase 2
- `behavior_model: BehaviorModel` — From Phase 3

### Output: `OperationalChangeModel`
A frozen dataclass containing:
- `repository: RepositoryModel` — Phase 1 output
- `change: ChangeModel` — Phase 2 output
- `behavior: BehaviorModel` — Phase 3 output
- `dependency: object | None` — Structural dependency analysis (Phase 5)
- `data: object | None` — Persistent state impact (Phase 5)
- `event: object | None` — Async interaction impact (Phase 5)
- `api: object | None` — Externally visible interface changes (Phase 5)
- `validation: object | None` — Test coverage evidence (Phase 5)
- `metrics: object | None` — Discovery metrics (Phase 5)

### Passes

**Phase 4 — Composition:**
1. **ModelCompositionPass** — Assembles the `OperationalChangeModel` from Phase 1-3 outputs
2. **ConsistencyValidationPass** — Validates cross-model consistency (e.g., all referenced symbols exist)

**Phase 5 — Operational Analysis:**
3. **DependencyAnalysisPass** — Analyzes structural dependencies
4. **DataAnalysisPass** — Analyzes persistent state impact
5. **EventAnalysisPass** — Analyzes async interaction impact
6. **APIAnalysisPass** — Analyzes externally visible interface changes
7. **ValidationAnalysisPass** — Analyzes test coverage and evidence
8. **MetricsPass** — Collects discovery metrics

---

## Language Adapters

**Location:** `language_adapters/`

Per-language static analysis that produces a language-agnostic semantic graph consumed by the `ModelCompiler`.

### Architecture

```
BaseLanguageAdapter (abstract)
├── PythonAdapter
│   ├── Extractors:
│   │   ├── calls/        — Function call extraction
│   │   ├── configuration/ — Config reference extraction
│   │   ├── entrypoints/  — REST endpoint extraction
│   │   ├── events/       — Event construct extraction
│   │   ├── imports/      — Import statement extraction
│   │   ├── persistence/  — ORM model extraction
│   │   ├── symbols/      — Symbol extraction
│   │   ├── tests/        — Test definition extraction
│   │   └── types/        — Type relationship extraction
│   └── parser/           — Python AST parser
│
└── JavaAdapter
    ├── Extractors:
    │   ├── calls/        — Method call extraction
    │   ├── configuration/ — Config reference extraction
    │   ├── entrypoints/  — REST endpoint extraction
    │   ├── events/       — Event construct extraction
    │   ├── imports/      — Import statement extraction
    │   ├── persistence/  — ORM model extraction
    │   ├── symbols/      — Symbol extraction
    │   ├── tests/        — Test definition extraction
    │   └── types/        — Type relationship extraction
    └── parser/           — Java parser
```

### Key Design
- **Language-specific** extractors parse source code into structured data
- **Language-agnostic** `ModelCompiler` transforms that data into a `RepositoryModel`
- Each extractor is independent and produces a specific slice of the semantic graph
- Framework detection (FastAPI, Flask, Django, SQLAlchemy for Python; Spring Boot, JPA for Java) is handled within extractors

### Model Types
- `Symbol` — Functions, classes, methods, imports with id, name, kind, language, file, range, visibility, properties
- `CallEdge` — Caller → callee relationship
- `ReferenceEdge` — Import resolution relationship
- `TypeRelationshipEdge` — Inheritance, composition, implementation
- `EntryPoint` — REST endpoints (method + route + handler)
- `AsyncEntryPoint` — Workers, queue consumers
- `PersistenceModel` — ORM models with fields and relationships
- `RepositoryMethod` — Data access methods
- `EventConstruct` — Publish/subscribe operations
- `TestDefinition` — Test functions/classes with fixtures and assertions
- `ConfigurationReference` — Environment variable and config key references

---

## Source Adapters

**Location:** `source_adapters/`

Source control integration for fetching diffs and posting results.

### GitHub Adapter
**Location:** `source_adapters/github/`

| File | Purpose |
|------|---------|
| `github_client.py` | GitHub API client (fetch diffs, file snapshots, SHAs) |
| `auth.py` | Installation auth, JWT generation, token exchange |
| `bot.py` | Post comments to PRs |
| `event_handler.py` | Dispatch webhook events to analysis jobs |
| `comment_formatter.py` | Render structured PR comments |
| `webhook.py` | Parse webhooks + signature validation |

### GitLab Adapter
**Location:** `source_adapters/gitlab/` (stub for future implementation)

---

## Instrumentation

**Location:** `instrumentation/sentry/`

Sentry integration for error tracking and performance monitoring:
- `sentry.py` — Sentry SDK initialization and configuration
- `contexts.py` — Per-request context (repository, PR number, analysis run ID)

---

## Data Flow

```
Source Code Repository
    │
    ▼
Language Adapter (Python/Java)
    │ - Parse source files
    │ - Extract symbols, calls, endpoints, etc.
    │ - Detect frameworks
    │
    ▼
ModelCompiler (Phase 1)
    │ - 11 passes over semantic graph
    │
    ▼
RepositoryModel
    │
    ├──► ChangeCompiler (Phase 2)
    │    │ - Compare old vs new RepositoryModel
    │    │ - Classify changes per symbol
    │    │
    │    ▼
    │   ChangeModel
    │
    ├──► BehaviorCompiler (Phase 3)
    │    │ - Discover affected behaviors
    │    │ - Build execution graphs
    │    │
    │    ▼
    │   BehaviorModel
    │
    └──► OperationalCompiler (Phase 4/5)
         │ - Compose all models
         │ - Validate consistency
         │ - Enrich with operational analysis
         │
         ▼
        OperationalChangeModel
            │
            ├──► Persist to database
            │
            ├──► Post PR comment (GitHub/GitLab)
            │
            └──► Return to caller
```

---

## Key Design Decisions

1. **4-Phase Compilation Pipeline** — Analysis is organized as sequential compilation phases, each producing a deterministic, immutable model. This enables independent testing, caching, and debugging of each phase.

2. **Pass-Based Architecture** — Each compiler executes a sequence of passes, where each pass has a single responsibility and transforms a shared context. Passes are composable and independently testable.

3. **Language-Agnostic Core** — Language adapters produce a common semantic graph format. The `ModelCompiler` and all subsequent phases operate on language-agnostic models, enabling multi-language support.

4. **Deterministic Models** — All models (`RepositoryModel`, `ChangeModel`, `BehaviorModel`, `OperationalChangeModel`) are frozen dataclasses, ensuring immutability and deterministic behavior.

5. **Graceful Degradation** — Phase 5 extension models (`dependency`, `data`, `event`, `api`, `validation`, `metrics`) are optional. The system degrades gracefully if any analysis pass fails.

6. **Independent Extractors** — Each language adapter has independent extractors for different semantic concerns (symbols, calls, endpoints, persistence, etc.). Extractors can be added or modified without affecting others.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Data Models | Pydantic / Frozen dataclasses |
| Testing | pytest |
| Static Analysis | Python AST, Java parser |
| VCS Integration | GitHub API |
| Observability | Sentry |
| Package Management | uv + pyproject.toml |

---

## Directory Structure

```
cystatic-core/
│
├── language_adapters/          Per-language static analysis
│   ├── base/                   Base classes and shared compiler
│   │   ├── adapter.py          BaseLanguageAdapter (abstract)
│   │   ├── compiler.py         ModelCompiler (11 passes)
│   │   ├── extractor.py        Base extractor interface
│   │   ├── normalization.py    Data normalization utilities
│   │   └── parser.py           Base parser interface
│   ├── model/                  Language-agnostic data models
│   │   ├── repository_model.py RepositoryModel
│   │   ├── symbol.py           Symbol, SymbolKind, SymbolVisibility
│   │   ├── graphs.py           CallGraph, ReferenceGraph, TypeRelationshipGraph
│   │   ├── configuration.py    ConfigurationReference
│   │   ├── events.py           EventConstruct
│   │   ├── persistence.py      PersistenceModel, RepositoryMethod
│   │   └── tests.py            TestDefinition, TestFramework, TestFixture
│   ├── python/                 Python adapter
│   │   ├── adapter.py          PythonAdapter
│   │   ├── parser/             Python AST parser
│   │   └── extractors/         Python-specific extractors (9)
│   │       ├── calls/
│   │       ├── configuration/
│   │       ├── entrypoints/
│   │       ├── events/
│   │       ├── imports/
│   │       ├── persistence/
│   │       ├── symbols/
│   │       ├── tests/
│   │       └── types/
│   └── java/                   Java adapter
│       ├── adapter.py          JavaAdapter
│       ├── parser/             Java parser
│       └── extractors/         Java-specific extractors (9)
│           ├── calls/
│           ├── configuration/
│           ├── entrypoints/
│           ├── events/
│           ├── imports/
│           ├── persistence/
│           ├── symbols/
│           ├── tests/
│           └── types/
│
├── change/                     Phase 2: Change Compilation
│   ├── compiler/
│   │   ├── compiler.py         ChangeCompiler
│   │   └── passes/
│   │       ├── base.py         ChangePassContext, ChangeCompilerPass
│   │       ├── changed_symbols/    ChangedSymbolsPass
│   │       └── change_classification/ ChangeClassificationPass
│   └── model/
│       ├── change_model.py     ChangeModel
│       └── changes.py          Change types (FunctionBodyChange, etc.)
│
├── behavior/                   Phase 3: Behavior Compilation
│   ├── compiler/
│   │   ├── compiler.py         BehaviorCompiler
│   │   └── passes/
│   │       ├── base.py         BehaviorPassContext, BehaviorCompilerPass
│   │       ├── behavior_discovery/ BehaviorDiscoveryPass
│   │       └── behavior_graph/     BehaviorGraphPass
│   └── model/
│       ├── behavior_model.py   BehaviorModel
│       ├── behavior.py         Behavior
│       └── execution_graph.py  ExecutionGraph
│
├── operational/                Phase 4/5: Operational Compilation
│   ├── compiler/
│   │   ├── compiler.py         OperationalCompiler
│   │   └── passes/
│   │       ├── base.py         OperationalPassContext, OperationalCompilerPass
│   │       ├── model_composition/     ModelCompositionPass
│   │       ├── consistency_validation/ ConsistencyValidationPass
│   │       ├── dependency/            DependencyAnalysisPass
│   │       ├── data/                  DataAnalysisPass
│   │       ├── events/                EventAnalysisPass
│   │       ├── api/                   APIAnalysisPass
│   │       ├── validation/            ValidationAnalysisPass
│   │       └── metrics/               MetricsPass
│   └── model/
│       └── model.py            OperationalChangeModel
│
├── source_adapters/            VCS integration
│   ├── github/
│   │   ├── github_client.py    GitHub API client
│   │   ├── auth.py             Installation auth
│   │   ├── bot.py              PR comment posting
│   │   ├── event_handler.py    Webhook event dispatch
│   │   ├── comment_formatter.py PR comment rendering
│   │   └── webhook.py          Webhook parsing + validation
│   └── gitlab/                 GitLab stub
│
├── instrumentation/            Observability
│   └── sentry/
│       ├── sentry.py           Sentry initialization
│       └── contexts.py         Per-request context
│
├── tests/                      Test suite
│   ├── test_repository_compiler.py   Phase 1 tests
│   ├── test_change_compiler.py       Phase 2 tests
│   ├── test_behavior_compiler.py     Phase 3 tests
│   └── test_operational_compiler.py  Phase 4/5 tests
│
├── templates/                  PR comment templates
├── pyproject.toml              Project configuration
├── pylock.toml                 Dependency lock
├── requirements.txt            Requirements
├── uv.lock                     uv lock file
├── pytest.ini                  pytest configuration
├── .clinerules                 Agent rules
└── README.md                   Project overview
```

---

## Summary

Factor uses a **4-phase compilation pipeline** where each phase produces a deterministic, immutable model:

1. **Phase 1 (Repository)** — Language adapters parse source code and the `ModelCompiler` builds a `RepositoryModel` with symbols, call graphs, endpoints, persistence models, and more.
2. **Phase 2 (Change)** — The `ChangeCompiler` compares old and new repository snapshots to produce a `ChangeModel` describing exactly what changed.
3. **Phase 3 (Behavior)** — The `BehaviorCompiler` discovers affected behaviors and builds execution graphs.
4. **Phase 4/5 (Operational)** — The `OperationalCompiler` composes all models and enriches them with dependency, data, event, API, validation, and metrics analysis.

The architecture is designed for **modularity, determinism, and extensibility** — each phase and pass can be developed, tested, and debugged independently.