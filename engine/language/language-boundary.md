# Language Boundary Architecture

## The Core Rule

> **Language-specific syntax must terminate at `RepositoryIndex`.**
>
> Parser ASTs, Tree-sitter nodes, parser-specific types, extractors, and language adapters belong exclusively to the language frontend. All components after `RepositoryIndex` must operate exclusively on language-independent representations.

---

## 1. Architectural Diagram

```text
Source Files
     │
     ▼
Language Detection
     │
     ▼
Language Plugin
     │
     ▼
Language Adapter
     │
     ├── Parser
     ├── Extractors
     ├── Passes
     └── Normalization
     │
     ▼
RepositoryIndex
════════════════════════════════════
       LANGUAGE BOUNDARY
════════════════════════════════════
     │
     ▼
SemanticCompiler
     │
     ▼
RepositoryModel
     │
     ├── GraphPatcher
     ├── ChangeCompiler
     ├── BehaviorCompiler
     ├── OperationalCompiler
     ├── DiscoveryCompiler
     ├── ReviewContextCompiler
     └── LLMContextCompiler
```

---

## 2. Responsibilities

### Language Frontend Responsibilities
* Parsing source files using tree-sitter or language-specific parsers
* Extracting raw AST / Tree-sitter representations
* Syntax tree traversal and pattern matching
* Language-specific semantic extraction (e.g. decorators, annotations, imports)
* Normalizing facts and shapes into canonical indices
* Producing the `RepositoryIndex`

### Language-Independent Responsibilities
* Semantic reference resolution and identifier binding
* Call and reference graph construction (`SemanticCompiler`)
* Graph patching (`GraphPatcher`)
* Downstream analysis (Change, Behavior, Operational compilers)
* Review and LLM context compilation
* Feature discovery and search indexing

---

## 3. Boundary Rules & Invariants

1. **`RepositoryIndex` is the handoff point**: No language-specific parser types (like `ast.AST` or `tree_sitter.Node`) may leak into `RepositoryIndex` or `RepositoryModel`.
2. **One-way dependencies**: `engine/language/*` packages may depend on language-independent definitions, but downstream components (`engine/change`, `engine/behavior`, etc.) must never import or consume anything inside concrete language packages (like `engine.language.python`, `engine.language.java`, etc.).
3. **No language branching downstream**: Do not check `if language == "python"` inside downstream compilers. If there's a language-specific feature, normalize it into a standard semantic representation at the adapter layer.
