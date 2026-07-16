# Engineering Discovery Artifact — Design Document

## Purpose

The Engineering Discovery Artifact is the **final immutable output** of the factor-api compilation pipeline. It replaces hours of manual code investigation with a structured, deterministic model that answers: **"What does this change actually touch?"**

## Design Philosophy

**Don't think in terms of JSON. Think in terms of what a reviewer should understand in 30 seconds.**

Every section of this artifact replaces a specific manual investigation that a senior engineer would normally perform when reviewing a PR.

---

## Artifact Sections

| Artifact Section | Replaces | Time Saved |
| --- | --- | --- |
| **Change Surface** | Reading the diff to estimate scope | 15-30 min |
| **Execution Surface** | Searching for entry points and tracing execution paths | 1-2 hours |
| **Dependency Surface** | Find References / Call Hierarchy in IDE | 30-60 min |
| **Data Surface** | Grepping models and repositories for database changes | 30-45 min |
| **Event Surface** | Searching producers/consumers for async interactions | 45-90 min |
| **Validation Surface** | Looking through tests to understand test coverage | 20-40 min |
| **Architecture Surface** | Asking senior engineers "what does this touch?" | 1-4 hours |

---

## Section Details

### 1. Change Surface

**What it provides:**
- Exact list of added, removed, and modified symbols
- Classification of each change (body, signature, visibility, decorators)
- Changed imports and endpoints

**Replaces manual investigation:**
```
❌ OLD WAY:
1. Open PR diff
2. Read through all changed files
3. Manually categorize: "Is this a new function? Modified signature? Just whitespace?"
4. Check if imports changed
5. Check if API endpoints changed
6. Write summary in PR comment

✅ NEW WAY:
Reviewer sees: "3 functions modified, 1 endpoint changed from GET to POST"
Time: 30 seconds
```

**Manual investigation time:** 15-30 minutes  
**Artifact confidence:** 100% (deterministic diff analysis)

---

### 2. Execution Surface

**What it provides:**
- All execution units (functions/methods that execute)
- Execution chains (ordered call sequences)
- Entry points (where execution begins: REST endpoints, workers, scheduled tasks)
- Terminal points (where execution ends: returns, raises, exits)
- Shared executions (infrastructure used by multiple behaviors)
- Reachable units (what can be touched from changed code)
- Execution depth (maximum call chain length)

**Replaces manual investigation:**
```
❌ OLD WAY:
1. Find the changed function
2. Search for all callers (IDE: Find Usages / Call Hierarchy)
3. For each caller, repeat: find their callers
4. Build mental model of execution flow
5. Identify entry points (where does this get called from?)
6. Identify shared infrastructure (database connections, API clients)
7. Draw execution graph on whiteboard

✅ NEW WAY:
Reviewer sees: "Changed function is called from 3 endpoints, 
reaches 12 execution units at depth 4, shares DB connection pool 
with 2 other behaviors"
Time: 30 seconds
```

**Manual investigation time:** 1-2 hours  
**Artifact confidence:** High (static call graph analysis)

---

### 3. Dependency Surface

**What it provides:**
- Structural dependencies of changed symbols
- Downstream dependencies affected by the change
- Import dependencies and module relationships

**Replaces manual investigation:**
```
❌ OLD WAY:
1. Find changed module/class
2. IDE: Find All References
3. Check each reference: "Does this break if I change the signature?"
4. Check transitive dependencies: "What depends on the dependencies?"
5. Build dependency graph mentally
6. Identify breaking changes vs. safe changes

✅ NEW WAY:
Reviewer sees: "Change affects 5 direct dependencies, 
12 transitive dependencies, 0 breaking API changes"
Time: 30 seconds
```

**Manual investigation time:** 30-60 minutes  
**Artifact confidence:** High (static reference analysis)

---

### 4. Data Surface

**What it provides:**
- Persistent state affected by the change
- Database models/schemas impacted
- Data migrations required
- Relationship changes (foreign keys, joins)

**Replaces manual investigation:**
```
❌ OLD WAY:
1. Find changed code that touches database
2. Grep for ORM models (SQLAlchemy, Django, JPA)
3. Check if schema changed (new columns, removed columns)
4. Check if relationships changed (foreign keys, joins)
5. Check if migrations exist
6. Verify data migration safety

✅ NEW WAY:
Reviewer sees: "Change touches User model, 
requires migration to add email_verified column, 
no breaking relationship changes"
Time: 30 seconds
```

**Manual investigation time:** 30-45 minutes  
**Artifact confidence:** Medium (requires ORM framework detection)

---

### 5. Event Surface

**What it provides:**
- Event producers (code that publishes events)
- Event consumers (code that subscribes to events)
- Async interactions (queues, workers, message brokers)
- Event schema changes

**Replaces manual investigation:**
```
❌ OLD WAY:
1. Find changed code that publishes events
2. Search for event consumers (grep for event name)
3. Check if event schema changed (payload structure)
4. Check if consumers handle new/removed fields
5. Check if message broker config changed
6. Verify backward compatibility

✅ NEW WAY:
Reviewer sees: "Change publishes UserCreated event with new field, 
3 consumers exist, all handle optional field safely"
Time: 30 seconds
```

**Manual investigation time:** 45-90 minutes  
**Artifact confidence:** Medium (requires event framework detection)

---

### 6. Validation Surface

**What it provides:**
- Test coverage for changed code
- Test definitions (unit, integration, e2e)
- Test fixtures and assertions affected
- Missing test coverage gaps

**Replaces manual investigation:**
```
❌ OLD WAY:
1. Find changed code
2. Search for corresponding test files
3. Check if tests exist for changed functions
4. Read test cases: "Do they cover the new behavior?"
5. Check if tests need updates
6. Identify coverage gaps

✅ NEW WAY:
Reviewer sees: "Changed function has 2 unit tests, 
no integration test for new error handling path, 
suggested test: test_invalid_email_raises"
Time: 30 seconds
```

**Manual investigation time:** 20-40 minutes  
**Artifact confidence:** High (static test analysis)

---

### 7. Architecture Surface

**What it provides:**
- Complete blast radius of the change
- Cross-cutting concerns (security, performance, compliance)
- Risk indicators (depth, breadth, shared state)
- Confidence scores based on evidence

**Replaces manual investigation:**
```
❌ OLD WAY:
1. Review change with author
2. Ask: "What else does this touch?"
3. Ask: "Is this safe to deploy?"
4. Ask: "Do we need to coordinate with another team?"
5. Ask: "What's the rollback plan?"
6. Document concerns in PR comment

✅ NEW WAY:
Reviewer sees: "Blast radius: 3 services, 12 functions, 
depth 4. Risk: LOW (no breaking changes, full test coverage). 
Confidence: 92%"
Time: 30 seconds
```

**Manual investigation time:** 1-4 hours (including team coordination)  
**Artifact confidence:** High (deterministic analysis + heuristics)

---

## Artifact Structure

```python
@dataclass(frozen=True)
class EngineeringDiscoveryArtifact:
    # Core models (always present)
    repository: RepositoryModel      # What the repo contains
    change: ChangeModel              # What changed
    behavior: BehaviorModel          # What behavior is affected
    
    # Execution-oriented abstractions (always present)
    execution_units: tuple[ExecutionUnit, ...]           # All executable units
    execution_chains: tuple[ExecutionChain, ...]         # Ordered call sequences
    entry_points: tuple[EntryPoint, ...]                 # Where execution begins
    terminal_points: tuple[TerminalPoint, ...]           # Where execution ends
    shared_executions: tuple[SharedExecution, ...]       # Shared infrastructure
    reachable_units: tuple[ExecutionUnit, ...]           # Units reachable from changes
    execution_depth: int                                 # Maximum call chain length
    
    # Enrichment models (optional, graceful degradation)
    dependency: DependencyModel | None                   # Structural dependencies
    data: DataModel | None                               # Persistent state affected
    event: EventModel | None                             # Async interactions
    api: APIModel | None                                 # Externally visible interfaces
    validation: ValidationModel | None                   # Test evidence
    metrics: MetricsModel | None                         # Observable metrics
```

---

## Usage Example

### Before (Manual Investigation)

```markdown
PR #123: "Add email verification"

Reviewer @senior-engineer:
1. Reads diff: 3 files changed, 45 insertions, 12 deletions
2. Finds changed function: `register_user()`
3. IDE: Find Usages → 5 callers
4. IDE: Call Hierarchy → 3 levels deep
5. Grep: "class User" → finds ORM model
6. Grep: "publish.*event" → finds event publisher
7. Search tests: "test_register" → finds 2 tests
8. Writes PR comment (20 min):
   "Looks good, but consider adding integration test 
   for email verification flow. Also, make sure 
   the User model migration is included."
   
Time: 1.5 hours
Confidence: Medium (might have missed something)
```

### After (Engineering Discovery Artifact)

```markdown
PR #123: "Add email verification"

Reviewer reads artifact:
- Change Surface: 1 function modified (register_user), 
  1 endpoint changed (POST /register)
- Execution Surface: 3 entry points, 12 reachable units, 
  depth 4, shares email service with 2 behaviors
- Dependency Surface: 5 direct dependencies, 0 breaking changes
- Data Surface: User model modified (added email_verified column), 
  migration required
- Event Surface: Publishes UserCreated event (new field: email_verified), 
  3 consumers handle optional field
- Validation Surface: 2 unit tests exist, missing integration test 
  for email flow
- Architecture Surface: Blast radius LOW, confidence 94%

Reviewer comment (30 seconds):
"LGTM. Add integration test for email verification flow 
and include User model migration."

Time: 30 seconds
Confidence: High (comprehensive analysis)
```

---

## Key Design Decisions

### 1. Execution-Oriented vs. Data-Oriented

**Decision:** Organize artifact around execution (what runs) rather than data (what's stored).

**Rationale:** 
- Engineers think in terms of execution: "What runs when I deploy this?"
- Execution chains reveal the true blast radius
- Data models are important but secondary to "what executes"

### 2. Immutable Frozen Dataclass

**Decision:** Artifact is immutable once created.

**Rationale:**
- Deterministic: Same inputs → same output
- Thread-safe: Can be cached and shared
- Traceable: Can't be accidentally modified
- Testable: Easy to assert equality

### 3. Optional Enrichment Models

**Decision:** Dependency, data, event, API, validation, metrics are optional.

**Rationale:**
- Graceful degradation: If analysis fails, still produce artifact
- Progressive enhancement: Add analysis dimensions over time
- Performance: Don't block on expensive analysis

### 4. Separate from OperationalChangeModel

**Decision:** EngineeringDiscoveryArtifact is separate from OperationalChangeModel.

**Rationale:**
- OCM is for renderers and AI (rich, detailed)
- Artifact is for humans (concise, execution-focused)
- Different consumers, different representations
- Can evolve independently

---

## Integration Points

### Compiler Pipeline

```
RepositoryModel + ChangeModel + BehaviorModel
    ↓
OperationalCompiler (8 passes)
    ↓
OperationalChangeModel
    ↓
EngineeringDiscoveryCompiler (extracts execution abstractions)
    ↓
EngineeringDiscoveryArtifact
    ↓
GitHubRenderer.render_artifact()
    ↓
PR Comment (human-readable)
```

### Runtime Pipeline

```python
# In Pipeline._compile_operational()
context.ocm = self._operational_compiler.compile(...)

# NEW: Build artifact from OCM
artifact = self._artifact_compiler.compile(
    operational_model=context.ocm
)

# Render artifact
comment = self._github_renderer.render_artifact(
    artifact, 
    context={"repository": ..., "pr_number": ...}
)
```

---

## Success Metrics

A reviewer should be able to answer these questions in 30 seconds:

1. ✅ **What changed?** (Change Surface)
2. ✅ **What runs because of this change?** (Execution Surface)
3. ✅ **What depends on this change?** (Dependency Surface)
4. ✅ **What data is affected?** (Data Surface)
5. ✅ **What async interactions changed?** (Event Surface)
6. ✅ **Is there test coverage?** (Validation Surface)
7. ✅ **What's the blast radius?** (Architecture Surface)

If any question takes longer than 30 seconds, the artifact is incomplete.

---

## Next Steps

1. **Integrate into pipeline:** Update `runtime/pipeline/pipeline.py` to use `EngineeringDiscoveryCompiler`
2. **Add tests:** Create `tests/test_engineering_discovery_compiler.py`
3. **Update renderers:** Ensure `GitHubRenderer.render_artifact()` is the primary render path
4. **Document in architecture.md:** Add artifact to data flow diagrams
5. **Add metrics:** Track "time to review" before/after artifact

---

## Conclusion

The Engineering Discovery Artifact is the **product**. It replaces manual investigation with deterministic analysis, reducing PR review time from hours to minutes while increasing confidence and consistency.

**The artifact is designed. Now it needs to be built and integrated.**