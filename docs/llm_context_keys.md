# LLM Context Keys

This document explains the meaning of the various keys that appear in the **LLM context** payloads used throughout the repository. These keys are used for accounting, budgeting, and diagnostics of language‑model‑driven workflows.

---

## fan_in

- **What it measures**: The count of separate inputs that feed the LLM for a single processing step. In our system these inputs are the events that arrive from the pipeline (e.g., a file change, a discovered symbol, an API‑call trigger).
- **Why it matters**: A higher fan_in means the LLM must consider more independent pieces of information, which raises token consumption and may require a larger token_budget. Keeping fan_in low helps the scheduler allocate resources efficiently and reduces the risk of token‑budget overruns.

---

## event_surface

- **What it measures**: The breadth of the event space that the LLM can react to. Every distinct event type (such as on_user_message, on_timeout, on_external_api, or the internal "symbol‑changed" event) contributes one unit to the event_surface.
- **Why it matters**: A larger surface indicates that the LLM must understand a wider variety of triggers, which can increase reasoning complexity. In practice, a modest event_surface (1‑3) is typical for simple pipelines, while larger orchestration flows (e.g., cross‑service change detection) may push this number higher.

---

## boundary_crossings

- **What it measures**: The number of times execution moves across a logical or architectural boundary during a pipeline run. Boundaries include transitions such as:
  - From the change‑discovery step to the execution‑graph builder.
  - From one micro‑service’s codebase to another’s (via shared dependencies).
  - From the LLM‑context construction to the LLM‑prompt generation.
- **Why it matters**: Each crossing typically entails serialization, network hops, or context reshaping, all of which are expensive in terms of latency and token usage. Monitoring boundary_crossings helps us spot over‑fragmented designs and guide refactoring toward more cohesive workflows.

---

- **Definition**: The number of distinct inbound messages, prompts, or data streams that flow into the LLM for a given processing step.
- **Purpose**: Helps the scheduler understand how many separate sources are contributing to the current request, which influences token budgeting and parallelism decisions.
- **Typical value range**: `0` (no external input) to dozens for highly compositional pipelines.

---

## event_surface

- **Definition**: The cardinality of the *event space* that the LLM may react to within the current context. In other words, the count of unique event types (e.g., `on_user_message`, `on_timeout`, `on_external_api`) that are visible to the model.
- **Purpose**: Provides a quick metric for the breadth of the LLM’s awareness; a larger surface usually means more complex reasoning is required.
- **Typical value range**: Small pipelines – 1‑3; large orchestrations – 10+.

---

## boundary_crossings

- **Definition**: The number of times the LLM’s execution crosses a predefined logical or architectural boundary (e.g., moving from one subsystem, micro‑service, or layer of abstraction to another).
- **Purpose**: Boundary crossings are expensive because they often involve serialization, network hops, or context reshaping. Tracking this metric enables the system to penalize overly fragmented workflows and to surface performance bottlenecks.
- **Typical value range**: 0 (purely local) to a handful (e.g., 3‑5) in distributed pipelines.

---

## token_budget (optional)

- **Definition**: The maximum number of tokens allocated for the LLM’s generation in the current step.
- **Purpose**: Guarantees that the model stays within the limits of the underlying service and that downstream consumers have enough capacity for their own processing.

---

## context_window (optional)

- **Definition**: The size (in tokens) of the rolling window of previous interactions that the LLM can attend to.
- **Purpose**: Determines how much historical information is retained; a larger window enables deeper reasoning but consumes more token budget.

---

## usage_notes

- These keys are emitted as part of the JSON payload that drives the LLM‑based orchestration engine. They are primarily for **observability** and **budget enforcement**; they do not affect the logical correctness of the LLM’s output.
- When building new pipelines, aim to keep `fan_in` and `boundary_crossings` low while allowing a sufficient `event_surface` to capture the necessary triggers.
- Monitoring dashboards often plot `fan_in` vs. `boundary_crossings` to spot over‑fragmented designs.

---

*Document generated on 2026‑08‑18.*

---

## st (String Table)

- **Definition**: Global string dictionary storing every distinct string used across the context. Entries are referenced by integer indices.
- **Purpose**: De‑duplicates repeated strings (file paths, symbol names, literals) to minimise token usage.

---

## f (Files)

- **Definition**: Tuple of `(path_idx, ct_id)` where `path_idx` indexes into `st` and `ct_id` references a change‑type enum.
- **Purpose**: Lists all files involved in the change set.

---

## sym (Symbols)

- **Definition**: Tuple of `(file_id, name_idx, kind_id)` representing each symbol that changed. `file_id` references an entry in `f`, `name_idx` references `st`, and `kind_id` references the `ENUM_KIND` table.
- **Purpose**: Captures the set of symbols (functions, classes, methods, etc.) affected by the change.

---

## ep (Endpoints)

- **Definition**: Tuple of `(method_id, path_idx)` where `method_id` indexes `ENUM_METHOD` and `path_idx` indexes `st`.
- **Purpose**: Describes HTTP or RPC endpoints introduced/modified.

---

## cs (Change Summary)

- **Definition**: A 5‑element tuple `(cls_id, scope_id, file_count, sym_count, bh_count)` summarising overall change classification, scope, and counts.
- **Purpose**: Provides a quick high‑level snapshot.

---

## cf (File Changes)

- **Definition**: Tuple of `(file_idx, (changed_sym_idx_1, changed_sym_idx_2, ...))`. `file_idx` references an entry in `f`; the inner tuple lists indices of symbols (from `sym`) that changed in that file.
- **Purpose**: Links files to the specific symbols they modify for precise localization.

---

## eg (Execution Graph)

- **Definition**: A DAG where each node is `(sym_idx, depth, reaches_svc_idx, reaches_mod_idx)` and edges are `(parent_node_idx, child_node_idx)`.
- **Purpose**: Represents execution flow across symbols, enabling reasoning about runtime impact.

---

## epts (Entry Points)

- **Definition**: Tuple of `(ep_idx, (node_idxs...), terminal_idx, max_depth)` describing each entry point into the execution graph.
- **Purpose**: Highlights starting points for execution (e.g., API handlers) and their reachable sub‑graph depths.

---

## disc (Discoveries)

- **Definition**: Tuple of `(kind_id, facts)` where `kind_id` references an enum and `facts` is a dictionary of arbitrary discovery data.
- **Purpose**: Encapsulates additional analysis findings (e.g., new dependencies, configuration changes).

---

*Document generated on 2026‑08‑18.*

*Document generated on 2026‑08‑18.*