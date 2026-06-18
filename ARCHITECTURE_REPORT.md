# Factor — Technical Deep-Dive Architecture

## Executive Summary

Factor is a **blast-radius and refactor-risk analysis engine** that combines deterministic static analysis (causal graphs, propagation engines) with probabilistic LLM reasoning to provide actionable impact analysis for code changes.

**Core Technical Principle:** Causal-graph propagation is the non-negotiable primary signal. The LLM serves as a contextual override only. Failure templates are optional hypotheses that never drive verdict upgrades.

---

## System Architecture: Technical Deep-Dive

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ENTRY POINTS                                 │
│  GitHub Webhook → workers/analyze_pr.py (Dramatiq)                  │
│  API Request → api/main.py (FastAPI)                                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              SOURCE ADAPTER LAYER                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ GitHubBot (source_adapters/github/bot.py)                    │  │
│  │ • fetch_diff() → DiffIR (unidiff parsing)                    │  │
│  │ • fetch_file_at_sha() → GitHubFileSnapshot                   │  │
│  │ • get_head_sha() → PR head SHA                               │  │
│  │ • Retry: 3 attempts, exponential backoff, 429/500-504        │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              LANGUAGE ADAPTER LAYER                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PythonAdapter (language_adapters/python/python_adapter.py)   │  │
│  │                                                              │  │
│  │ TWO MODES:                                                   │  │
│  │ • DIFF_ONLY: Regex over hunks (no repo access)              │  │
│  │   - _get_top_level_functions_from_hunk_regex()              │  │
│  │   - Pattern: ^(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(  │  │
│  │   - extract_endpoints_from_diff_only()                      │  │
│  │                                                              │  │
│  │ • FULL_FILE: AST over complete file content                  │  │
│  │   - ast.parse() → _get_functions_ast()                      │  │
│  │   - _map_changed_lines_to_functions()                       │  │
│  │   - extract_endpoints() → FastAPIEndpointParser             │  │
│  │   - FlaskEndpointParser                                      │  │
│  │                                                              │  │
│  │ KEYWORD SIGNALS:                                             │  │
│  │ • AUTH_PATTERN: \b(auth|authenticate|authorization|...)\b   │  │
│  │ • PAYMENT_PATTERN: \b(payment|pay|billing|invoice|...)\b    │  │
│  │ • VALIDATION_REMOVAL_PATTERN: on removed lines only          │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              INTERMEDIATE REPRESENTATION (IR)                        │
│  schemas/ir.py:                                                     │
│  • DiffIR → list[FileDiff]                                         │
│  • FileDiff → file_path, added_lines, removed_lines, hunks        │
│  • DiffHunk → source_start/length, target_start/length, lines     │
│  • DiffLine → line_type, content, source_line_no, target_line_no  │
│  • FunctionChanged → name, file_path, change_type, start/end_line │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              ORCHESTRATOR PIPELINE                                   │
│  core_engine/orchestrator.py                                        │
│                                                                     │
│  TWO STRATEGIES:                                                    │
│  • Orchestrator (FULL_FILE) - Production                           │
│  • DiffOrchestrator (DIFF_ONLY) - Demo/Sandbox                     │
│                                                                     │
│  SHARED PIPELINE (_run_causal_pipeline):                           │
│  1. FileExclusionService → filter lockfiles, assets, generated    │
│  2. RiskPatternDetector → detect risky code shapes                 │
│  3. EntryPointResolver → affected HTTP/event/CLI entry points      │
│  4. extract_behavior_deltas() → per-symbol behavior                │
│  5. build_behavior_diffs() → BehaviorDiff(symbol, before, after)  │
│  6. ReachabilityClassifier → classify reachability                 │
│  7. SideEffectDetector → mutation/IO/state side effects            │
│  8. RIRCompressor.compress_v3() → token-budgeted IR               │
│  9. build_causal_graph() → CausalGraph                             │
│  10. build_impact_tree() → ImpactTree                              │
│  11. match_failure_templates() → optional hypotheses               │
│  12. build_system_behavior_deltas() → SystemBehaviorDelta          │
│  13. build_execution_paths() → PathGenerationResult                │
│  14. extract_constraints() → ConstraintSet                         │
│  15. LLM failure simulation (optional)                             │
│  16. score_scenarios() → ValidationScore                           │
│  17. _aggregate_verdict() → final verdict                          │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              CAUSAL GRAPH ENGINE (CORE PRIMITIVE)                    │
│  core_engine/causal_graph.py                                        │
│                                                                     │
│  DATA STRUCTURES:                                                   │
│  • CausalNode: name, node_type (symbol|endpoint|service|database  │
│    |queue|shared_state), metadata                                   │
│  • CausalEdge: from_symbol, to_symbol, edge_type, confidence,      │
│    evidence_type, evidence_location, evidence_snippet              │
│  • CausalGraph: edges[], nodes{}, outgoing{}, incoming{}           │
│                                                                     │
│  EDGE TYPES (6):                                                    │
│  • data_flow: Result flows from one symbol to another              │
│  • control_flow: One symbol gates execution of another             │
│  • shared_state: Shared state coupling (cache/redis/session)       │
│  • async_event: Event emitted between symbols                      │
│  • db_dependency: Database read/write dependency                   │
│  • transaction_boundary: Shared transaction boundary               │
│                                                                     │
│  GRAPH CONSTRUCTION (CausalGraphBuilder.build()):                  │
│  1. Build known_symbols set:                                       │
│     - DIFF_ONLY: only changed functions                            │
│     - FULL_FILE: changed + repo_index.known_symbols                │
│                                                                     │
│  2. For each enriched file:                                        │
│     a. _register_typed_nodes() - Register endpoints, services,     │
│        databases as typed nodes                                     │
│        • Repo-wide: ALL endpoints from repo_index                  │
│        • Local: endpoints from current file                        │
│        • Service inference from file path (billing/ → "Billing")   │
│        • Database inference from DB access patterns                │
│                                                                     │
│     b. _detect_call_edges() - Data flow from function calls        │
│        • Pattern: (?:self\.|\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(    │
│        • Filter: COMMON_BUILTINS, KNOWN_LIBRARY_CALLS              │
│        • CRITICAL: Only to known_symbols (repo-defined)            │
│        • Confidence calibration:                                   │
│          - assignment: 0.45                                        │
│          - return: 0.50                                            │
│          - chained (.method()): 0.35                               │
│          - direct call: 0.30                                       │
│        • Bidirectional: forward (calls) + reverse (called_by)      │
│                                                                     │
│     c. _detect_shared_state_edges() - Direction-aware resource     │
│        nodes (Task I innovation)                                    │
│        • OLD MODEL (deprecated): O(n²) fully-connected            │
│        • NEW MODEL: O(n) directional through typed resource nodes  │
│          writer_symbol → resource → reader_symbol                  │
│        • Resource extraction: cache:user, redis:cart, etc.        │
│        • Direction detection:                                      │
│          WRITE: .set(, .put(, .add(, .save(, .update(, .delete(  │
│          READ: .get(, .fetch(, .read(, .load(, .peek(, .retrieve(│
│        • Confidence: 0.60                                          │
│                                                                     │
│     d. _detect_async_edges() - Event/queue propagation             │
│        • Patterns: queue., publish(, emit(, dispatch(, send_task( │
│        • Consumer patterns: subscribe(, consumer(, handler(       │
│        • Confidence: 0.55                                          │
│                                                                     │
│     e. _detect_db_edges() - Database dependencies                  │
│        • Write patterns: .save(, .update(, .insert(, .delete(    │
│        • Read patterns: .query(, .filter(, db., database.         │
│        • Direction: write → collection, collection → read          │
│        • Confidence: 0.65                                          │
│                                                                     │
│     f. _detect_transaction_edges() - Transaction boundaries         │
│        • Patterns: transaction.atomic, db.session, BEGIN;         │
│        • Confidence: 0.70                                          │
│                                                                     │
│  REPOSITORY SYMBOL INDEX (RepositorySymbolIndex):                 │
│  • from_files() - Builds from (file_path, content) pairs          │
│  • AST parsing: _function_names_from_ast() - Collect all defs     │
│  • _extract_endpoints_from_ast() - FastAPI/Flask routes           │
│  • known_symbols: set of all function names in repo               │
│  • all_endpoints: list of all route definitions                   │
│  • Unlocks propagation past diff boundary                          │
│  • Zero extra HTTP calls - reuses already-fetched snapshots        │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PROPAGATION ENGINE                                      │
│  core_engine/propagation_engine.py                                  │
│                                                                     │
│  ALGORITHM:                                                         │
│  1. Initialize roots from directly_changed symbols                 │
│     • confidence = 1.0, hop_distance = 0                           │
│     • impacted_systems inferred from symbol naming                 │
│                                                                     │
│  2. DFS traversal from each root:                                  │
│     • For each outgoing edge:                                      │
│       propagated_confidence = current_confidence × edge.confidence │
│       if propagated < confidence_threshold (0.05): skip            │
│                                                                     │
│     • Update or create ImpactNode:                                 │
│       - If new: create with propagated confidence                  │
│       - If exists: take MAX confidence, MIN hop_distance           │
│       - Append edge to incoming_edges                              │
│                                                                     │
│     • Recurse with new confidence, hops+1                          │
│     • Cap at max_hops=5                                            │
│                                                                     │
│  3. System inference (SYSTEM_MAP):                                 │
│     checkout → [Checkout]                                          │
│     payment, pay, charge → [Payment]                               │
│     invoice → [Invoice]                                            │
│     tax → [Tax]                                                    │
│     auth, authenticate, login → [Authentication]                   │
│     billing → [Billing]                                            │
│     cache, redis → [Caching]                                       │
│                                                                     │
│  OUTPUT (ImpactTree):                                              │
│  • roots: directly changed ImpactNodes                             │
│  • all_nodes: dict[symbol, ImpactNode]                             │
│  • get_blast_radius():                                            │
│    - impacted_services, endpoints, databases, queues              │
│    - downstream_symbols (capped at 30)                             │
│    - critical_paths (paths ending at typed boundaries)             │
│    - max_confidence, avg_confidence                                │
│                                                                     │
│  rank_impact_paths(): DFS from roots, rank by confidence           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              EXECUTION PATHS (PHASE 3: TRUST CORE)                  │
│  core_engine/execution_paths.py                                     │
│                                                                     │
│  PURPOSE: Engineers don't trust abstract graphs - they trust       │
│  concrete paths. This generates specific chains:                   │
│  "this specific sequence explains the risk"                        │
│                                                                     │
│  ALGORITHM (PathGenerator):                                        │
│  1. Entry symbols: directly_changed + API handlers + transaction   │
│     boundaries from causal graph                                    │
│                                                                     │
│  2. DFS from each entry symbol:                                    │
│     • Stack: (current, path_nodes, path_edges, confidence, depth,  │
│       edge_types, risk_points)                                      │
│     • Sort outgoing edges by confidence (highest first)            │
│     • Accumulate confidence: product of edge confidences           │
│     • Prune if confidence < min_confidence (0.05)                  │
│     • Detect risk points at each node                              │
│                                                                     │
│  3. Risk point classification:                                     │
│     • Typed boundary nodes (service, database, endpoint, queue)   │
│     • Transaction boundary edges                                   │
│     • Shared state writes (schema mutation)                        │
│     • DB write→read transitions (stale data risk)                  │
│     • Async event emissions (cross-service boundary)               │
│                                                                     │
│  4. Path type inference:                                           │
│     • Domain-specific: checkout_to_invoice, payment_to_order      │
│     • Infrastructure: shared_state_propagation, async_event_chain  │
│     • Generic: {start}_to_{end}                                   │
│                                                                     │
│  5. Deduplication: Remove identical node sequences, keep highest   │
│     confidence                                                      │
│                                                                     │
│  6. Cap: max_paths_per_entry=10, max_total_paths=30               │
│                                                                     │
│  OUTPUT (PathGenerationResult):                                    │
│  • paths: list[ExecutionPath]                                      │
│  • entry_points_used: list[str]                                    │
│  • total_symbols_reached: int                                      │
│  • max_confidence, avg_confidence: float                           │
│                                                                     │
│  ExecutionPath structure:                                          │
│  • path_type: "checkout_to_invoice"                                │
│  • nodes: ["_update_checkout_tax", "handle_payment", ...]         │
│  • edges: [{from, to, type, confidence, affected_by_change}]      │
│  • path_confidence: float (product of edge confidences)            │
│  • key_risk_points: list[RiskPoint]                                │
│  • hop_distance: int                                               │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              LLM FAILURE SIMULATION (PHASE 5)                       │
│  core_engine/failure_simulation_llm.py                             │
│                                                                     │
│  V5 INPUT CONTRACT (4 sections ONLY):                              │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ {                                                           │   │
│  │   "execution_paths": [...],      // Hard truth chains      │   │
│  │   "change_overlay": [...],       // Risk injection         │   │
 │  │   "uncertainty_shadows": [...],  // Confidence modifiers   │   │
│  │   "constraints": {...}           // Risk amplifiers        │   │
│  │ }                                                           │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  REMOVED (noise generators):                                       │
│  ❌ change_influence, soft_propagation, domain_risk_priors         │
│  ❌ system_constraints, causal_hypotheses, raw change_graph        │
│  ❌ raw risk_patterns, full behavior_diff, full causal_graph       │
│  ❌ "None → downstream" placeholders                               │
│                                                                     │
│  LLM ROLE (strict constraints):                                    │
│  • ONLY allowed to reason using execution_paths                    │
│  • Every failure scenario MUST originate from exactly one path     │
│  • May NOT create new chains or new flows                          │
│  • Priority: execution_paths > change_overlay > uncertainty >      │
│    constraints                                                     │
│  • "no edges → SAFE" is REMOVED                                   │
│  • NEVER default to SAFE                                          │
│  • Prefer 1-3 high-confidence failures over none                  │
│                                                                     │
│  PROMPT STRUCTURE:                                                 │
│  • SYSTEM_PROMPT: Rules and constraints                            │
│  • USER_PROMPT_TEMPLATE: Input structure + output format spec     │
│                                                                     │
│  OUTPUT FORMAT (strict JSON):                                      │
│  {                                                                 │
│    "verdict": "SAFE|LOW_RISK|UNCERTAIN_IMPACT|...|BLOCK_REVIEW", │
│    "failure_scenarios": [{                                         │
│      "title": "specific, concrete failure",                        │
│      "trigger": "exact condition",                                 │
│      "execution_path": "function → function → system outcome",    │
│      "evidence_type": "direct|inferred|structural_pattern|...",   │
│      "production_impact": "real-world consequence",                │
│      "confidence": 0.0,                                            │
│      "hop_confidence": 0.0,                                        │
│      "causal_chain": "symbol → symbol (with confidence)",         │
│      "failure_class": "idempotency_break|double_charge|...",      │
│      "first_observable_signal": "where detected in production",   │
│      "silent_failure": true,                                       │
│      "ci_would_catch": false,                                      │
│      "false_confidence_reason": "...",                             │
│      "why_it_slips_through": "...",                                │
│      "merge_confidence_trap": "...",                               │
│      "merge_risk_level": "LOW|MEDIUM|HIGH|CRITICAL",              │
│      "supported_by": ["symbol1", "symbol2"],                       │
│      "reasoning": "Step-by-step reasoning"                         │
│    }],                                                             │
│    "hidden_impact_chain": ["step 1 → step 2 → step 3"],          │
│    "checked_risk_areas": ["checkout", "billing", ...],            │
│    "missing_critical_tests": ["test scenario"],                    │
│    "broken_assumptions": ["assumption no longer true"],            │
│    "silent_failure_summary": "1-2 lines",                          │
│    "merge_risk_statement": "...",                                  │
│    "verdict_rationale": "...",                                     │
│    "final_question": "sharp question forcing reconsideration"     │
│  }                                                                 │
│                                                                     │
│  DEFENSIVE SANITIZATION:                                           │
│  • sanitize_llm_json_string():                                     │
│    - Strip markdown code blocks (```json ... ```)                  │
│    - Fix malformed keys (unicode-escape, stray quotes)            │
│    - Regex-based key cleaning:                                     │
│      key_pattern = r'"' r'(?:\\.|[^"\\])*?' r'"' r'\s*' r':'    │
│    - clean_malformed_key(): decode unicode, strip, match expected  │
│    - fix_structural(): remove whitespace, normalize braces        │
│                                                                     │
│  • sanitize_llm_json():                                            │
│    - Iterate keys, decode unicode-escape                           │
│    - Match against expected_keys (fuzzy match)                     │
│    - Backfill missing fields from _default_failure_simulation()    │
│                                                                     │
│  API CALL:                                                         │
│  • OpenAI client (compatible with Groq, OpenRouter)               │
│  • response_format={"type": "json_object"}                         │
│  • temperature=0.0 (deterministic)                                 │
│  • extra_headers: HTTP-Referer, X-OpenRouter-Title                │
│  • extra_body: reasoning={"enabled": true} for OpenRouter         │
│                                                                     │
│  VALIDATION:                                                       │
│  • FailureSimulationOutput.model_validate(data) - Pydantic        │
│  • On failure: raise ValueError with raw output for debugging     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              SCENARIO VALIDATION                                    │
│  core_engine/scenario_validator.py                                 │
│                                                                     │
│  PURPOSE: Soft scoring, not hard rejection                         │
│                                                                     │
│  score_scenarios(failure_simulation, compressed_for_llm):         │
│  • For each failure_scenario in LLM output:                        │
│    - Validate against compressed IR                                │
│    - confidence_adjustment: float multiplier (0.0-1.0)            │
│    - issues: list[str] of validation problems                     │
│                                                                     │
│  • Top-level:                                                      │
│    - warnings: list[str]                                          │
│    - notes: list[str]                                             │
│                                                                     │
│  APPLICATION:                                                      │
│  • scenario["confidence"] *= score.confidence_adjustment          │
│  • Append validation issues to scenario["reasoning"]               │
│  • Never discard scenarios - only adjust confidence                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              VERDICT AGGREGATION                                    │
│  BaseOrchestrator._aggregate_verdict()                             │
│                                                                     │
│  PRIORITY ORDER:                                                   │
│  1. BLAST RADIUS (primary signal)                                  │
│  2. LLM OVERRIDE (only SAFE or BLOCK_REVIEW)                       │
│  3. FALLBACK (NO_SIGNIFICANT_PROPAGATION_FOUND)                    │
│                                                                     │
│  ALGORITHM:                                                        │
│  if impacted_services or impacted_endpoints or impacted_databases: │
│    blast_verdict = "LOW_RISK"                                     │
│    if max_confidence >= 0.6:                                      │
│      blast_verdict = "REVIEW_REQUIRED"                             │
│    elif max_confidence >= 0.25:                                   │
│      blast_verdict = "UNCERTAIN_IMPACT"                            │
│                                                                     │
│    # LLM override check                                            │
│    if llm_verdict in {"SAFE", "BLOCK_REVIEW"}:                    │
│      return llm_verdict  # Override blast radius                   │
│    else:                                                           │
│      return blast_verdict                                          │
│                                                                     │
│  elif llm_verdict:                                                 │
│    return llm_verdict  # No blast radius, trust LLM               │
│                                                                     │
│  else:                                                             │
│    return "NO_SIGNIFICANT_PROPAGATION_FOUND"                       │
│                                                                     │
│  ALLOWED VERDICTS:                                                 │
│  SAFE | LOW_RISK | UNCERTAIN_IMPACT |                             │
│  NO_SIGNIFICANT_PROPAGATION_FOUND | REVIEW_REQUIRED | BLOCK_REVIEW │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PERSISTENCE LAYER                                      │
│  api/models.py - persist_analysis_result()                         │
│                                                                     │
│  11 TABLES WRITTEN IN SINGLE CALL:                                 │
│                                                                     │
│  1. Organization (update_or_create)                                │
│     • github_installation_id or github_organization_login         │
│                                                                     │
│  2. Repository (update_or_create)                                  │
│     • full_name unique                                             │
│     • language_breakdown, framework_hints                          │
│                                                                     │
│  3. PullRequest (update_or_create)                                 │
│     • (repository, number) unique_together                         │
│     • changed_files, changed_files_count                           │
│                                                                     │
│  4. AnalysisRun (get_or_create)                                    │
│     • (pull_request, head_sha, triggered_by) unique_together       │
│     • analysis_snapshot: ENTIRE result dict as JSON                │
│     • internal_reasoning_artifacts: compressed IR, entry points   │
│                                                                     │
│  5. PullRequestSnapshot (create)                                   │
│     • raw_payload: full result JSON                                │
│                                                                     │
│  6. AnalysisArtifact (create)                                      │
│     • artifact_type="compressed_for_llm"                           │
│     • payload_json: compressed IR                                  │
│                                                                     │
│  7. DeterministicAnalyzerOutput (create)                           │
│     • Structured deterministic pass results                        │
│     • Indexed metadata: node_count, edge_count, impacted_services │
│     • Denormalized lists: execution_paths, auth_boundary_changes   │
│                                                                     │
│  8. RiskFinding (create per risk pattern)                          │
│     • category, severity, confidence, evidence                     │
│     • affected_components, inferred_blast_radius                   │
│                                                                     │
│  9. AnalysisComment (create)                                       │
│     • body: rendered markdown                                      │
│     • Links to AnalysisRun via canonical_comment                   │
│                                                                     │
│  DEFENSIVE PARSING:                                                │
│  • _jsonable(): Recursively convert Pydantic models, dataclasses, │
│    enums, sets, tuples to JSON-safe structures                    │
│  • _to_int(), _to_float(): Safe type conversion with defaults     │
│  • _confidence_bucket(): high(≥0.8), medium(≥0.5), low           │
│  • _severity_for_category(): Maps RiskEventType to CRITICAL/HIGH/ │
│    MEDIUM based on domain                                          │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PR COMMENT RENDERING                                   │
│  templates/github/pr_comment.md.j2 (Jinja2)                        │
│                                                                     │
│  INPUT:                                                             │
│  • verdict: final aggregated verdict                               │
│  • failure_simulation: normalized dict                             │
│                                                                     │
│  RENDER: _render_pr_comment()                                      │
│  • Load Jinja2 template from templates/ directory                  │
│  • Pass verdict and normalized failure_simulation                  │
│  • Return rendered markdown                                        │
│                                                                     │
│  NORMALIZATION:                                                    │
│  • _normalize_failure_simulation():                                │
│    - Ensure all expected keys present                               │
│    - Clean unicode-escape artifacts                                │
│    - Strip stray quotes from keys                                  │
│    - Normalize failure_scenarios list                              │
│    - Convert lists to string lists                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Algorithms: Technical Specifications

### 1. Causal Graph Construction Algorithm

**Input:** `enriched_files`, `behavior_diffs`, `repo_index` (optional)

**Output:** `CausalGraph` with nodes and edges

**Step-by-step:**

```python
# Step 1: Build known_symbols set
known_symbols = set()
for file in enriched_files:
    for fn in file.changed_functions:
        known_symbols.add(fn.name.split(".")[-1])

if repo_index:
    known_symbols |= repo_index.known_symbols  # Repo-wide expansion

# Step 2: For each file, detect edges
for file in enriched_files:
    symbols = extract_symbols(file.changed_functions)
    lines = collect_lines(file.hunks)
    
    # Register typed nodes
    register_endpoints(file.endpoints)
    if repo_index:
        register_all_repo_endpoints(repo_index.all_endpoints)
    register_services_from_path(file.path)
    register_databases_from_patterns(lines)
    
    # Detect edges (only to known symbols)
    detect_call_edges(symbols, lines, known_symbols)
    detect_shared_state_edges(symbols, lines)
    detect_async_edges(symbols, lines)
    detect_db_edges(symbols, lines)
    detect_transaction_edges(symbols, lines)
```

**Edge Detection Details:**

**Call Edges:**
- Pattern: `(?:self\.|\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(`
- Filters: COMMON_BUILTINS (len, str, int, etc.), KNOWN_LIBRARY_CALLS (json, datetime, os, etc.)
- CRITICAL: Only create edge if `called in known_symbols`
- Confidence calibration:
  - Assignment (`x = func()`): 0.45
  - Return (`return func()`): 0.50
  - Chained (`self.func()` or `obj.func()`): 0.35
  - Direct call: 0.30
- Bidirectional: forward (calls) + reverse (called_by, confidence × 0.9)

**Shared State Edges (Direction-Aware):**
- Extract resource name: `cache:user`, `redis:cart`, `session:token`
- Register as typed node: `node_type="shared_state"`
- Direction detection:
  - WRITE patterns: `.set(`, `.put(`, `.add(`, `.save(`, `.update(`, `.delete(`, `.pop(`, `.store(`, `.write(`, `session[`, `session.`
  - READ patterns: `.get(`, `.fetch(`, `.read(`, `.load(`, `.peek(`, `.retrieve(`
- Edge creation:
  - Writer → resource (edge_type="shared_state", confidence=0.60)
  - Resource → reader (edge_type="shared_state", confidence=0.60)
- O(n) complexity vs old O(n²) fully-connected model

**Async Event Edges:**
- Producer patterns: `queue.`, `publish(`, `emit(`, `dispatch(`, `send_task(`, `webhook.`, `.push(`, `broker.`, `event.`
- Consumer patterns: `subscribe(`, `consumer(`, `handler(`, `listener(`, `process_event(`, `on_message(`, `receive(`, `handle_event(`, `on_event(`
- Confidence: 0.55

**Database Edges:**
- Write patterns: `.save(`, `.update(`, `.insert(`, `.delete(`, `.commit(`, `.get_or_create(`
- Read patterns: `.query(`, `.filter(`, `db.`, `database.`
- Direction: write → collection, collection → read
- Confidence: 0.65

**Transaction Edges:**
- Patterns: `transaction.atomic`, `db.session`, `begin_transaction`, `BEGIN;`, `START TRANSACTION`, `transactional`, `@transactional`
- Confidence: 0.70

### 2. Propagation Algorithm

**Input:** `CausalGraph`, `directly_changed: list[str]`, `max_hops=5`

**Output:** `ImpactTree`

**Algorithm:**

```python
# Initialize roots
for symbol in directly_changed:
    root = ImpactNode(
        symbol=symbol,
        confidence=1.0,
        hop_distance=0,
        is_direct_change=True,
        impacted_systems=infer_systems(symbol)
    )
    tree.roots.append(root)
    tree.all_nodes[symbol] = root

# DFS traversal
for symbol in directly_changed:
    traverse(symbol, 1.0, 0, set())

def traverse(current, confidence, hops, visited):
    if hops >= max_hops:
        return
    
    for edge in graph.get_outgoing(current):
        if (current, edge.to_symbol) in visited:
            continue
        visited.add((current, edge.to_symbol))
        
        propagated = confidence * edge.confidence
        if propagated < 0.05:  # confidence_threshold
            continue
        
        # Update or create node
        if edge.to_symbol not in tree.all_nodes:
            node = ImpactNode(
                symbol=edge.to_symbol,
                confidence=propagated,
                hop_distance=hops + 1,
                incoming_edges=[edge],
                impacted_systems=infer_systems(edge.to_symbol)
            )
            tree.all_nodes[edge.to_symbol] = node
        else:
            existing = tree.all_nodes[edge.to_symbol]
            if propagated > existing.confidence:
                existing.confidence = propagated
                existing.hop_distance = min(existing.hop_distance, hops + 1)
            if edge not in existing.incoming_edges:
                existing.incoming_edges.append(edge)
            propagated = existing.confidence
        
        traverse(edge.to_symbol, propagated, hops + 1, visited)
```

**Key Properties:**
- Confidence propagation: multiplicative decay (`parent_confidence × edge.confidence`)
- Aggregation: MAX confidence for repeated paths
- Pruning: confidence < 0.05 threshold
- Cycle prevention: visited edge set
- Hop cap: max_hops=5

### 3. Execution Path Generation Algorithm

**Input:** `CausalGraph`, `entry_symbols`, `max_depth=5`, `min_confidence=0.05`

**Output:** `PathGenerationResult`

**Algorithm:**

```python
# DFS with stack
stack = [(start, [start], [], 1.0, 0, [], [])]

while stack and len(paths) < max_paths_per_entry:
    current, path_nodes, path_edges, acc_confidence, depth, edge_types, risk_points = stack.pop()
    
    outgoing = graph.get_outgoing(current)
    if not outgoing or depth >= max_depth:
        # Record terminal path
        if len(path_nodes) >= 2:
            paths.append(build_path(...))
        continue
    
    # Sort by confidence (highest first)
    sorted_edges = sorted(outgoing, key=lambda e: -e.confidence)
    
    has_children = False
    for edge in sorted_edges:
        next_symbol = edge.to_symbol
        if next_symbol in path_nodes:
            continue  # Avoid cycles
        
        has_children = True
        new_confidence = acc_confidence * edge.confidence
        if new_confidence < min_confidence:
            continue
        
        # Detect risk points
        risk_point = classify_risk_point(next_symbol, next_node, edge, first_next_outgoing)
        
        stack.append((
            next_symbol,
            path_nodes + [next_symbol],
            path_edges + [edge_dict],
            new_confidence,
            depth + 1,
            edge_types + [edge.edge_type],
            risk_points + [risk_point] if risk_point else risk_points
        ))
    
    if not has_children and len(path_nodes) >= 2:
        paths.append(build_path(...))

# Post-processing
paths = deduplicate_paths(paths)  # Remove identical node sequences
paths.sort(key=lambda p: (-p.path_confidence, p.hop_distance))
paths = paths[:max_total_paths]  # Cap at 30
```

**Risk Point Classification:**

```python
def classify_risk_point(symbol, node, incoming_edge, outgoing_edge):
    # 1. Typed boundary nodes
    if node.node_type in {service, database, endpoint, queue, shared_state}:
        return RiskPoint(symbol, f"{node.node_type}_boundary", ...)
    
    # 2. Transaction boundary
    if incoming_edge.edge_type == "transaction_boundary":
        return RiskPoint(symbol, "transaction_boundary", 
                        "atomic rollback risk", ...)
    
    # 3. Shared state write
    if outgoing_edge.edge_type == "shared_state":
        return RiskPoint(symbol, "schema_mutation",
                        "shared state write", ...)
    
    # 4. DB write→read transition
    if (incoming_edge.edge_type == "db_dependency" and
        outgoing_edge.edge_type == "db_dependency"):
        return RiskPoint(symbol, "db_write_read_transition",
                        "stale data risk", ...)
    
    # 5. Async event emission
    if outgoing_edge.edge_type == "async_event":
        return RiskPoint(symbol, "cross_service_boundary",
                        "async event emission", ...)
    
    return None
```

### 4. LLM Input Contract (V5)

**Strict 4-Field Input:**

```python
{
    "execution_paths": [
        {
            "path_type": "checkout_to_invoice",
            "nodes": ["_update_checkout_tax", "handle_payment", "generate_invoice"],
            "edges": [
                {
                    "from": "_update_checkout_tax",
                    "to": "handle_payment",
                    "type": "data_flow",
                    "confidence": 0.85,
                    "evidence": "return value passed to payment handler",
                    "affected_by_change": True
                }
            ],
            "path_confidence": 0.86,
            "key_risk_points": [
                {
                    "symbol": "handle_payment",
                    "risk_type": "transaction_boundary",
                    "description": "handle_payment -> transaction boundary (atomic rollback risk)",
                    "confidence": 0.85,
                    "evidence": "calls db.session.commit()"
                }
            ],
            "hop_distance": 2,
            "start_symbol": "_update_checkout_tax",
            "end_symbol": "generate_invoice",
            "path_types_involved": ["data_flow", "transaction_boundary"]
        }
    ],
    "change_overlay": [
        {
            "symbol": "_update_checkout_tax",
            "risk_type": "FINANCIAL_LOGIC_CHANGE",
            "confidence": 0.9,
            "file_path": "services/checkout/tax.py",
            "change_type": "modified"
        }
    ],
    "uncertainty_shadows": [
        {
            "symbol": "handle_payment",
            "shadow_type": "low_test_coverage",
            "confidence_modifier": 0.8,
            "reason": "No integration tests for payment failure scenarios"
        }
    ],
    "constraints": {
        "idempotency": {
            "required": True,
            "enforcement": "database_unique_constraint",
            "confidence": 0.9
        },
        "transaction_boundary": {
            "symbol": "handle_payment",
            "is_atomic": True,
            "rollback_on_error": True
        },
        "retry_policy": {
            "max_retries": 3,
            "backoff": "exponential",
            "idempotent": True
        }
    }
}
```

**LLM Constraints:**
1. Every failure scenario MUST originate from exactly one execution path
2. May NOT create new chains or new flows
3. Priority: execution_paths > change_overlay > uncertainty_shadows > constraints
4. change_overlay only marks nodes as risky (doesn't create risk)
5. uncertainty_shadows only adjust confidence (never create failure modes)
6. If no execution_path contains changed symbol → NO_SIGNIFICANT_PROPAGATION_FOUND
7. SAFE only if no execution path affected by change_overlay
8. NEVER default to SAFE
9. Prefer 1-3 high-confidence failures over none

### 5. Repository-Wide Symbol Index

**Purpose:** Expand propagation past diff boundary

**Construction:**

```python
@classmethod
def from_files(cls, files: list[tuple[str, str]]) -> "RepositorySymbolIndex":
    idx = cls()
    for file_path, content in files:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue  # Defensive: skip malformed files
        
        # Extract all function names
        symbols = _function_names_from_ast(tree)
        idx.file_symbols[file_path] = symbols
        idx.known_symbols.update(symbols)
        
        # Extract all endpoints
        endpoints = _extract_endpoints_from_ast(tree, file_path)
        if endpoints:
            idx.all_endpoints.extend(endpoints)
            idx.file_endpoints[file_path] = endpoints
    
    return idx

def _function_names_from_ast(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (node.name.startswith("__") and node.name.endswith("__")):
                names.add(node.name)
    return names
```

**Impact on Graph:**
- Without repo index: `known_symbols = changed_functions_only`
- With repo index: `known_symbols = changed_functions ∪ all_repo_functions`
- Result: Calls to unchanged helpers produce real edges
- Example: `process_order()` calls `validate_address()` (unchanged)
  - Without index: no edge (validate_address not in known_symbols)
  - With index: edge created (validate_address in known_symbols)
- Blast radius quality jump: 8.5 → 9.5 (reported metric)

### 6. Confidence Propagation Mathematics

**Propagation Formula:**

```
confidence_at_node_n = Π(edge_i.confidence) for i in 1..n
```

**Example:**
```
Root: calculate_tax (confidence=1.0)
  ↓ edge: data_flow, confidence=0.85
Node: handle_payment (confidence=0.85)
  ↓ edge: transaction_boundary, confidence=0.70
Node: generate_invoice (confidence=0.595)
  ↓ edge: db_dependency, confidence=0.65
Node: save_to_db (confidence=0.386)
```

**Aggregation (multiple paths to same node):**
```
confidence = max(path1_confidence, path2_confidence, ...)
hop_distance = min(path1_hops, path2_hops, ...)
incoming_edges = union of all incoming edges
```

**Verdict Thresholds:**
```
max_confidence >= 0.6  → REVIEW_REQUIRED
max_confidence >= 0.25 → UNCERTAIN_IMPACT
max_confidence < 0.25  → LOW_RISK
```

---

## Data Structures: Technical Specifications

### Core Data Structures

**CausalGraph:**
```python
@dataclass
class CausalGraph:
    edges: list[CausalEdge]
    nodes: dict[str, CausalNode]  # name → node
    outgoing: dict[str, list[CausalEdge]]  # from_symbol → edges
    incoming: dict[str, list[CausalEdge]]  # to_symbol → edges
    
    def add_edge(self, edge: CausalEdge):
        self.edges.append(edge)
        self.outgoing.setdefault(edge.from_symbol, []).append(edge)
        self.incoming.setdefault(edge.to_symbol, []).append(edge)
        # Auto-create nodes if not exists
        if edge.from_symbol not in self.nodes:
            self.nodes[edge.from_symbol] = CausalNode(name=edge.from_symbol)
        if edge.to_symbol not in self.nodes:
            self.nodes[edge.to_symbol] = CausalNode(name=edge.to_symbol)
```

**ImpactTree:**
```python
@dataclass
class ImpactTree:
    roots: list[ImpactNode]
    all_nodes: dict[str, ImpactNode]  # symbol → node
    
    def get_impacted_symbols(self, min_confidence=0.1):
        return [n.symbol for n in self.all_nodes.values()
                if n.confidence >= min_confidence and not n.is_direct_change]
    
    def get_blast_radius(self):
        return {
            "total_nodes": len(self.all_nodes),
            "direct_changes": len([n for n in self.all_nodes.values() if n.is_direct_change]),
            "impacted_downstream": len(self.get_impacted_symbols()),
            "impacted_symbols": self.get_impacted_symbols()[:20],
            "impacted_systems": self.get_impacted_systems(),
            "impacted_services": self.get_impacted_by_type("service"),
            "impacted_endpoints": self.get_impacted_by_type("endpoint"),
            "impacted_databases": self.get_impacted_by_type("database"),
            "impacted_queues": self.get_impacted_by_type("queue"),
            "max_confidence": self.get_max_confidence(),
            "avg_confidence": round(sum(n.confidence for n in self.all_nodes.values()) / max(len(self.all_nodes), 1), 3)
        }
```

**ExecutionPath:**
```python
@dataclass
class ExecutionPath:
    path_type: str  # "checkout_to_invoice"
    nodes: list[str]
    edges: list[dict]  # {from, to, type, confidence, affected_by_change}
    path_confidence: float  # Product of edge confidences
    key_risk_points: list[RiskPoint]
    hop_distance: int
    start_symbol: str
    end_symbol: str
    path_types_involved: list[str]  # Unique edge types
```

**FailureSimulationOutput (Pydantic):**
```python
class FailureSimulationOutput(BaseModel):
    verdict: str
    failure_scenarios: list[FailureScenario]
    hidden_impact_chain: list[str]
    checked_risk_areas: list[str]
    missing_critical_tests: list[str]
    broken_assumptions: list[str]
    silent_failure_summary: str
    merge_risk_statement: str
    verdict_rationale: str
    final_question: str
    system_behavior_deltas: list[dict]
    matched_failure_templates: list[dict]
    blast_radius: dict

class FailureScenario(BaseModel):
    title: str
    trigger: str
    execution_path: str
    evidence_type: str
    production_impact: str
    confidence: float
    hop_confidence: float
    causal_chain: str
    failure_class: str
    first_observable_signal: str
    silent_failure: bool
    ci_would_catch: bool
    false_confidence_reason: str
    why_it_slips_through: str
    merge_confidence_trap: str
    merge_risk_level: str
    supported_by: list[str]
    reasoning: str
```

---

## Key Algorithms: Complexity Analysis

### Causal Graph Construction
- **Time:** O(F × (L + E)) where F=files, L=lines, E=edge detection strategies
- **Space:** O(N + E) where N=nodes, E=edges
- **Edge Count:**
  - Call edges: O(F × L) worst case, filtered to O(changed_functions × calls_per_function)
  - Shared state: O(F × L) with O(n) per file (directional)
  - Async/DB/Transaction: O(F × L)

### Propagation Engine
- **Time:** O(N × D × E_avg) where N=nodes, D=max_depth, E_avg=avg outgoing edges
- **Space:** O(N) for ImpactTree
- **Pruning:** Confidence threshold (0.05) dramatically reduces traversal

### Execution Path Generation
- **Time:** O(E × P × D) where E=entry points, P=paths per entry, D=depth
- **Space:** O(P × D) for path storage
- **Caps:** max_paths_per_entry=10, max_total_paths=30, max_depth=5

### LLM Sanitization
- **Time:** O(K × L) where K=keys, L=key length (regex operations)
- **Space:** O(K) for sanitized output

---

## Critical Implementation Details

### 1. Bidirectional Edge Creation

**Problem:** Changing a callee should propagate back to callers

**Solution:** For every call edge `A → B`, also create reverse edge `B → A`:
```python
# Forward edge
graph.add_edge(CausalEdge(
    from_symbol=symbol,
    to_symbol=called,
    edge_type="calls",
    confidence=0.30,
    ...
))

# Reverse edge (called_by)
graph.add_edge(CausalEdge(
    from_symbol=called,
    to_symbol=symbol,
    edge_type="called_by",
    confidence=0.30 * 0.9,  # Slightly discounted
    ...
))
```

### 2. Confidence Calibration Strategy

**Rationale:** Different evidence types have different reliability

| Evidence Type | Confidence | Reason |
|---------------|------------|--------|
| Assignment | 0.45 | Direct data flow, high confidence |
| Return | 0.50 | Explicit return value, very high confidence |
| Chained call | 0.35 | Indirect, may have side effects |
| Direct call | 0.30 | Simple invocation, but context unknown |
| Shared state | 0.60 | Strong coupling, but direction matters |
| Async event | 0.55 | Eventual consistency, medium confidence |
| DB dependency | 0.65 | Strong coupling, clear direction |
| Transaction | 0.70 | Very strong coupling, atomic boundary |

### 3. Repo Index Zero-Cost Construction

**Problem:** Building repo index requires fetching all files (expensive)

**Solution:** Reuse already-fetched snapshots:
```python
# In Orchestrator.run_pr_analysis():
repo_index_files = []
for file in files:
    snapshot = source.fetch_file_at_sha(repo, file.path, sha)
    # ... process file ...
    repo_index_files.append((file.path, snapshot.content))

# Build index from already-fetched data
repo_index = RepositorySymbolIndex.from_files(repo_index_files)
# Zero extra HTTP calls!
```

### 4. LLM Output Sanitization: Unicode-Escape Handling

**Problem:** LLMs often output malformed JSON with unicode escapes, stray quotes

**Solution:** Multi-stage sanitization:
```python
# Stage 1: String-level cleanup
def sanitize_llm_json_string(json_string):
    # Strip markdown code blocks
    json_string = re.sub(r'^```(?:json)?\s*', '', json_string)
    json_string = re.sub(r'\s*```$', '', json_string)
    
    # Fix malformed keys with regex
    key_pattern = r'"' r'(?:\\.|[^"\\])*?' r'"' r'\s*' r':'
    fixed = re.sub(key_pattern, clean_malformed_key, json_string)
    
    # Fix structural whitespace
    fixed = re.sub(r'\s*\n\s*', '', fixed)
    fixed = re.sub(r'\{\s*', '{', fixed)
    fixed = re.sub(r'\s*\}', '}', fixed)
    
    return fixed

# Stage 2: Dict-level cleanup
def sanitize_llm_json(raw_output):
    sanitized = {}
    for key, value in raw_output.items():
        # Decode unicode escapes
        try:
            clean_key = key.encode().decode('unicode_escape')
        except (UnicodeDecodeError, AttributeError):
            clean_key = key
        
        # Strip quotes and whitespace
        clean_key = clean_key.strip().strip('"\'').strip()
        
        # Fuzzy match against expected keys
        matched_key = None
        for expected in expected_keys:
            if clean_key == expected or clean_key.replace(" ", "_").lower() == expected.lower():
                matched_key = expected
                break
        
        sanitized[matched_key or clean_key] = value
    
    return sanitized
```

### 5. Domain Risk Priors (Layer 4)

**Purpose:** Probabilistic safety net for LLM when causal graph is sparse

**Structure:**
```python
_DOMAIN_BASE_RISK = {
    "billing": 0.7,
    "payment": 0.8,
    "money_movement": 0.8,
    "checkout": 0.75,
    "auth": 0.6,
    "tax": 0.7,
    # ... 20+ domains
}

_DOMAIN_FAILURE_MODES = {
    "billing": ["double_charge", "tax_mismatch", "ledger_drift"],
    "payment": ["double_charge", "payment_flow_error", "webhook_mismatch"],
    "auth": ["auth_bypass_chain", "permission_escalation"],
    # ... domain-specific failure modes
}

_MUTATION_RISK = {
    "state_mutation": 0.6,
    "payment_flow_change": 0.8,
    "retry_handling_change": 0.75,
    "financial_calculation_change": 0.7,
    "schema_change": 0.5,
    # ...
}
```

**Construction:**
```python
def _build_domain_risk_priors(change_influence, risk_patterns, enriched_files):
    # 1. Collect touched domains from change_influence
    touched_domains = {}
    for ci in change_influence:
        domain = ci.get("domain", "general")
        score = ci.get("influence_score", 0.0)
        touched_domains[domain] = max(touched_domains.get(domain, 0), score)
    
    # 2. Scan enriched files for keyword signals
    for file_data in enriched_files:
        for signal in file_data.keyword_signals:
            for domain_key in _DOMAIN_BASE_RISK:
                if domain_key in signal.keyword.lower() or domain_key in file_path:
                    touched_domains[domain_key] = 0.5
    
    # 3. Build output with adjusted risk
    for domain, base_risk in _DOMAIN_BASE_RISK.items():
        if domain in touched_domains:
            influence = touched_domains[domain]
            adjusted_risk = min(base_risk + influence * 0.2, 1.0)
            # ... populate domain entry
    
    # 4. Compute overall risk level
    max_risk = max(domains[domain]["adjusted_risk"] for domain in domains)
    if max_risk >= 0.7:
        overall = "HIGH"
    elif max_risk >= 0.5:
        overall = "MEDIUM"
    else:
        overall = "LOW"
    
    return {"domains": domains, "mutation_risk": mutation_risks, "overall_risk_level": overall}
```

---

## Performance Optimizations

### 1. Confidence Thresholding
- Prune edges where `propagated_confidence < 0.05`
- Reduces traversal space exponentially
- Example: 100 edges × 0.7 confidence = 7 edges at hop 2 (vs 100 without threshold)

### 2. Hop Capping
- `max_hops=5` prevents infinite traversal
- Typical blast radius: 2-3 hops
- Rarely reaches 5 hops in practice

### 3. Result Capping
- `downstream_symbols` capped at 30
- `paths` capped at 30 total (10 per entry)
- Prevents LLM context overflow

### 4. Lazy Imports
- `failure_templates` imported lazily
- Graceful degradation if module unavailable
- Core signals don't depend on it

### 5. Snapshot Reuse
- Repo index built from already-fetched snapshots
- Zero extra HTTP calls
- Critical for rate limit management

---

## Security & Defensive Programming

### 1. Input Sanitization
- All external inputs parsed defensively
- `_jsonable()` recursively converts unknown types
- `_to_int()`, `_to_float()` with try/except defaults
- Never trust webhook payloads without signature validation

### 2. LLM Output Sanitization
- Never trust raw LLM output
- Multi-stage sanitization (string → dict → validation)
- Backfill missing fields with defaults
- Strip unicode escapes, stray quotes, markdown

### 3. SQL Injection Prevention
- Tortoise ORM parameterized queries
- No raw SQL construction
- Foreign key constraints enforced

### 4. Secrets Management
- All credentials via environment variables
- pydantic-settings with `.env.local` support
- No hardcoded secrets

### 5. Webhook Security
- HMAC-SHA256 signature validation
- `delivery_id` for deduplication
- `idempotency_key` prevents double-runs

---

## Extension Points

### 1. Language Adapters
**Interface:**
```python
class LanguageAdapter(Protocol):
    def extract_changed_files(self, diff_ir: DiffIR) -> list[dict]: ...
    def extract_changed_functions(self, file: dict, mode: AnalysisMode, content: str = None) -> list[FunctionChanged]: ...
    def extract_endpoints(self, file_path: str, content: str) -> list[dict]: ...
    def extract_keyword_signals_from_diff(self, file: dict) -> list[KeywordDetected]: ...
```

**To add TypeScript:**
- Implement `extract_changed_functions()` using TypeScript AST (ts-morph or regex)
- Implement `extract_endpoints()` for Express/Fastify patterns
- Add keyword signals for TypeScript-specific risks

### 2. Source Adapters
**Interface:**
```python
class SourceAdapter(Protocol):
    def fetch_diff(self, repo: str, pr_number: int) -> DiffIR: ...
    def fetch_file_at_sha(self, repo: str, file_path: str, sha: str) -> FileSnapshot: ...
    def get_head_sha(self, repo: str, pr_number: int) -> str: ...
    def post_comment(self, repo: str, pr_number: int, comment: str) -> None: ...
```

**To add GitLab:**
- Implement GitLab API client
- Convert GitLab diff format to DiffIR
- Handle GitLab webhook payloads

### 3. Risk Patterns
**Extension:**
```python
# In core_engine/risk_flags.py
class RiskEventType(Enum):
    # Existing patterns...
    NEW_RISK_CATEGORY = "new_risk_category"

# In core_engine/risk_pattern_detector.py
def detect(self, enriched_files):
    # Add detection logic for NEW_RISK_CATEGORY
    patterns = []
    for file in enriched_files:
        if self._detect_new_risk(file):
            patterns.append(RiskPattern(
                risk_type=RiskEventType.NEW_RISK_CATEGORY,
                confidence=0.8,
                ...
            ))
    return patterns
```

### 4. LLM Providers
**Current:** OpenAI-compatible API (Groq default)

**To add Anthropic:**
```python
class AnthropicFailureSimulationLLM:
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20240620"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
    
    def generate(self, execution_paths, change_overlay, uncertainty_shadows, constraints):
        # Convert V5 input to Anthropic format
        # Handle response parsing
        # Return FailureSimulationOutput
```

---

## Testing Strategy

### Unit Tests
- **causal_graph tests:** Graph construction, edge detection, blast radius
- **propagation_engine tests:** Impact tree building, confidence propagation
- **execution_paths tests:** Path generation, risk point classification
- **language_adapter tests:** Function extraction, endpoint detection
- **scenario_validator tests:** Validation scoring

### Integration Tests
- **github_webhook_tests:** Webhook parsing, signature validation
- **github_worker_tests:** End-to-end worker flow
- **source_adapter_tests:** GitHub API interactions

### Test Patterns
```python
# Example: Causal graph construction
def test_build_causal_graph_with_repo_index():
    enriched_files = [...]
    repo_index = RepositorySymbolIndex.from_files([...])
    
    graph = build_causal_graph(
        enriched_files=enriched_files,
        behavior_diffs=[],
        repo_index=repo_index
    )
    
    assert len(graph.nodes) > 0
    assert len(graph.edges) > 0
    # Verify repo-wide propagation
    assert "unchanged_helper" in graph.nodes
```

---

## Conclusion: Technical Insights

### What Makes Factor Unique

1. **Deterministic Core:** Causal graph propagation is mathematically sound, reproducible, and explainable. The LLM enhances but never replaces this.

2. **Direction-Aware Shared State:** The shift from O(n²) fully-connected edges to O(n) directional resource nodes is a fundamental algorithmic improvement that reduces false positives.

3. **Execution Paths Over Abstract Graphs:** Engineers trust concrete paths ("A → B → C → database") over abstract node counts. Phase 3 (Trust Core) bridges this gap.

4. **Strict LLM Constraints:** V5 input contract removes noise, enforces grounding in execution paths, and prevents hallucination. The LLM is a reasoning engine, not a creativity engine.

5. **Graceful Degradation:** Every optional component (LLM, failure templates, repo index) has a fallback. The system never fails completely.

6. **Defensive Everything:** From LLM output sanitization to type conversion to webhook validation, defensive programming is pervasive.

### Technical Debt & Future Work

1. **TypeScript Adapter:** Currently regex-based, needs AST parsing (ts-morph)
2. **GitLab Adapter:** Stub implementation, needs full API integration
3. **Performance:** Path generation could benefit from memoization
4. **Testing:** Integration test coverage needs expansion
5. **Observability:** Add distributed tracing (OpenTelemetry)
6. **Caching:** Cache causal graphs for unchanged files

### Architecture Metrics

- **Files:** 50+ across 9 directories
- **Core Engine Modules:** 20
- **Database Tables:** 11 + 1 eval
- **Edge Types:** 6
- **Node Types:** 6
- **LLM Input Fields:** 4 (V5)
- **LLM Output Fields:** 13
- **Verdict Options:** 6
- **Max Propagation Hops:** 5
- **Confidence Threshold:** 0.05
- **Max Paths:** 30 total (10 per entry)
- **Max Downstream Symbols:** 30

---

*This technical deep-dive was generated through systematic code analysis of the Factor codebase, examining implementation details, algorithms, data structures, and design patterns.*