# AGENT.md

## Purpose

`cystatic-core` contains the core Factor engineering intelligence engine and backend.

This repository is **production-critical**. Code written here may become part of Factor's long-lived architecture, so agents must optimize for:

1. Correctness
2. Understandability
3. Reliability
4. Maintainability
5. Architectural coherence
6. Security
7. Testability
8. Performance where it materially matters

Do not optimize for minimum lines of code or fastest implementation at the expense of the above.

---

# 1. Prime Directive

> **Understand the existing system before changing it.**

Before modifying code:

* Inspect the relevant module(s).
* Trace the execution path.
* Identify callers and dependencies.
* Read relevant tests.
* Read `architecture.md` when the change touches architecture or system boundaries.
* Search the repository before creating new abstractions.
* Prefer extending existing patterns over introducing competing patterns.

Do not make architectural assumptions from filenames alone.

If the architecture is unclear, investigate it before coding.

---

# 2. Repository Integrity

The repository is the source of truth.

Never:

* Invent APIs that do not exist.
* Assume an external dependency behaves a certain way without checking it.
* Duplicate existing functionality without justification.
* Delete apparently unused code without verifying references.
* Change public behavior unintentionally.
* Introduce a new abstraction merely because it is locally convenient.

When uncertain, inspect the codebase.

---

# 3. Python Engineering Standards

Write modern, idiomatic Python.

Prefer:

* Small, cohesive functions.
* Explicit interfaces.
* Clear naming.
* Type hints.
* Immutable data where practical.
* Composition over unnecessary inheritance.
* Dependency injection where it improves testability.
* Standard-library solutions when they are sufficient.

Avoid:

* God classes.
* God functions.
* Deep nesting.
* Clever one-liners that reduce readability.
* Hidden global state.
* Mutable global configuration.
* Broad exception handling.
* Silent failures.
* Unnecessary metaprogramming.
* Premature abstractions.

### Type safety

Type hints should be used for:

* Function parameters.
* Return values.
* Public interfaces.
* Important internal data structures.

Do not use `Any` as an escape hatch unless there is a concrete reason.

When introducing `Any`, document why static typing cannot reasonably express the type.

Prefer precise types over:

```python
Any
dict
list
object
```

when the actual structure is known.

---

# 4. Error Handling

Errors must be explicit and actionable.

Do not:

```python
try:
    ...
except Exception:
    pass
```

Do not silently swallow failures.

Catch exceptions at the level where they can actually be handled.

Use domain-specific exceptions when they improve clarity.

Errors should preserve useful context.

Prefer:

```python
raise AnalysisError(
    f"Failed to analyze PR {pr_id}"
) from exc
```

over hiding the original failure.

---

# 5. Async / Concurrency

Do not mix synchronous and asynchronous execution casually.

Before introducing async code:

* Understand the existing execution model.
* Check whether the dependency is sync or async.
* Avoid blocking the event loop.
* Avoid unnecessary concurrency.
* Ensure cancellation and failure behavior are understood.

Concurrency should be introduced because it solves a real problem, not because it looks faster.

---

# 6. Dependencies

Before adding a dependency:

1. Search the repository for an existing solution.
2. Check whether the standard library is sufficient.
3. Consider dependency size and maintenance.
4. Consider security implications.
5. Consider whether the dependency creates architectural coupling.

Do not introduce dependencies for trivial functionality.

Pin or constrain versions according to the repository's existing dependency strategy.

Do not upgrade major dependencies casually.

Dependency upgrades should be treated as potentially architectural changes when they alter behavior or interfaces.

---

# 7. Testing

Every meaningful behavioral change should have appropriate tests.

Tests should verify **behavior**, not implementation details.

Prefer:

* Unit tests for isolated logic.
* Integration tests for component boundaries.
* End-to-end tests for critical workflows.

When fixing a bug:

> **Add a regression test before or alongside the fix whenever practical.**

A test suite that passes but does not exercise the changed behavior is not sufficient evidence.

Do not weaken or delete tests merely to make a change pass.

If an existing test is incorrect, explain why and replace it with a test representing the correct invariant.

---

# 8. Determinism

Core analysis behavior should be deterministic whenever possible.

Avoid introducing nondeterminism through:

* Unordered iteration when ordering matters.
* Randomness without controlled seeds.
* Time-dependent behavior.
* Environment-dependent behavior.
* Race conditions.
* Unstable external APIs.

When nondeterminism is unavoidable, isolate it behind a clear boundary.

---

# 9. Observability

Production-critical behavior should be observable.

Use appropriate:

* Structured logging.
* Metrics.
* Error reporting.
* Tracing where appropriate.

Logs should provide enough context to diagnose failures without exposing secrets or sensitive data.

Never log:

* API keys.
* Access tokens.
* Passwords.
* Credentials.
* Private user data unless explicitly required and appropriately protected.

---

# 10. Security

Treat all external input as untrusted.

Validate:

* API input.
* Repository data.
* GitHub data.
* Webhook payloads.
* Configuration.
* User-provided identifiers.
* File paths.
* External service responses.

Never:

* Hard-code secrets.
* Commit credentials.
* Disable security checks without justification.
* Trust external payloads blindly.
* Execute arbitrary input without validation.

Follow least-privilege principles.

---

# 11. Database Changes

Database schema changes must be deliberate.

Before modifying the schema:

* Understand existing models.
* Search for all consumers.
* Check migrations.
* Consider backwards compatibility.
* Consider existing production data.
* Consider rollback behavior.

Never modify a schema casually as part of an unrelated feature.

For destructive migrations, explicitly consider:

* Data loss.
* Migration ordering.
* Deployment sequencing.
* Existing clients.
* Rollback strategy.

---

# 12. API / Interface Stability

Treat interfaces as contracts.

Before changing an interface:

* Find all callers.
* Understand the compatibility requirements.
* Update tests.
* Update dependent code.
* Update relevant documentation.

Avoid breaking changes unless there is a clear reason.

When breaking behavior is necessary, make the migration explicit.

---

# 13. Architecture

`architecture.md` is the **living architectural source of truth** for `cystatic-core`.

It should describe the architecture that actually exists—not the architecture we wish existed.

## Required architecture update rule

> **Any architectural change—major OR minor—requires an update to `architecture.md` in the same change.**

This includes, but is not limited to:

* Adding or removing modules.
* Introducing a new service/component.
* Changing module responsibilities.
* Changing dependency direction.
* Introducing a new abstraction.
* Removing an abstraction.
* Changing data flow.
* Changing execution flow.
* Introducing a new integration.
* Changing persistence architecture.
* Changing queues/event systems.
* Changing agent boundaries.
* Changing API boundaries.
* Moving functionality between modules.
* Introducing significant caching.
* Introducing a new processing pipeline.
* Changing ownership of state.
* Changing synchronization/concurrency architecture.

Do **not** wait for a later documentation pass.

If the architecture changes, update the architecture documentation **in the same PR/commit**.

---

# 14. Architecture Documentation Standard

When updating `architecture.md`, document:

### What changed

Clearly describe the architectural change.

### Why it changed

Document the engineering/product reason.

### New structure

Explain:

* Components.
* Responsibilities.
* Dependencies.
* Data flow.
* Interfaces.
* Ownership of state.

### Consequences

Document important:

* Tradeoffs.
* Constraints.
* Failure modes.
* Scalability implications.
* Operational implications.

The documentation should be understandable to an engineer who has never worked in the repository.

---

# 15. Small Changes Still Count

Do not interpret "minor architecture change" as "only major rewrites."

For example, changing:

```text
Analyzer
   ↓
Repository
```

to:

```text
Analyzer
   ↓
AnalysisService
   ↓
Repository
```

is an architectural change even if the diff is only 100 lines.

Update `architecture.md`.

Likewise, moving business logic from one module to another can constitute an architectural change even if functionality remains identical.

---

# 16. Architecture Drift

Agents must actively look for architecture drift.

Architecture drift occurs when:

```text
architecture.md
       ≠
actual code
```

If you discover that the documentation is already inaccurate:

1. Determine the actual architecture.
2. Do not blindly conform the code to stale documentation.
3. Update `architecture.md` to represent reality.
4. Mention the discrepancy in the change summary when relevant.

Never preserve an incorrect architecture merely because the documentation says so.

---

# 17. Refactoring

Refactoring is encouraged when it improves the system materially.

Good reasons to refactor:

* Repeated logic.
* Excessive coupling.
* High complexity.
* Poor separation of concerns.
* Difficult testing.
* Frequent regressions.
* Unclear ownership.
* Repeated agent confusion.
* Excessive change amplification.
* Performance problems.
* Security problems.

Do not refactor unrelated areas merely because they could be cleaner.

Prefer:

> **Small, reversible, well-tested refactors.**

Avoid large rewrites unless the existing architecture fundamentally prevents progress.

---

# 18. Technical Debt

Technical debt should be treated as an engineering liability, not a moral failure.

When introducing intentional debt:

* Understand why it exists.
* Keep the scope limited.
* Record important debt.
* Avoid building additional systems on top of known unstable foundations when practical.

Prioritize debt based on:

```text
Impact
× Frequency
× Risk
× Strategic Importance
÷ Remediation Effort
```

Do not spend engineering time polishing low-impact code while high-impact architectural problems remain unresolved.

---

# 19. AI-Agent Specific Rules

Because agents actively modify this repository, agents must optimize for **safe change**, not merely successful code generation.

Before implementation:

1. Understand the task.
2. Map the relevant architecture.
3. Inspect existing patterns.
4. Identify invariants.
5. Identify tests.
6. Identify potential side effects.

During implementation:

* Keep changes scoped.
* Do not modify unrelated files without reason.
* Avoid speculative improvements.
* Preserve existing behavior unless the task requires changing it.
* Prefer explicit code over clever abstractions.

After implementation:

1. Run relevant tests.
2. Run type checking.
3. Run linting.
4. Review the diff.
5. Check for accidental behavior changes.
6. Check architecture impact.
7. Update `architecture.md` if architecture changed.

---

# 20. Agent Context Efficiency

Do not read the entire repository indiscriminately.

Start from:

```text
Task
 ↓
Relevant entry point
 ↓
Call graph
 ↓
Dependencies
 ↓
Tests
 ↓
Architecture
```

Expand context only when necessary.

However, **do not sacrifice correctness for token efficiency**.

If understanding the change requires broader repository context, inspect it.

---

# 21. Change Scope

Every change should have a clear boundary.

A PR should answer:

> **What changed, and why?**

Avoid mixing:

* Feature work
* Large refactors
* Dependency upgrades
* Formatting changes
* Unrelated bug fixes

in one change unless they are genuinely coupled.

Small diffs are easier to review, test, revert, and reason about.

---

# 22. Code Review Standard

Before considering work complete, review your own diff as if you were reviewing another engineer's PR.

Check:

### Correctness

* Does it actually solve the problem?
* Are edge cases handled?
* Could it regress existing behavior?

### Architecture

* Does it fit existing boundaries?
* Did it introduce unnecessary coupling?
* Did responsibilities move?

### Reliability

* What happens when dependencies fail?
* What happens with malformed input?
* What happens under retries?

### Security

* Are inputs trusted incorrectly?
* Could sensitive information leak?

### Testing

* Is the new behavior tested?
* Is regression coverage sufficient?

### Maintainability

* Will another engineer understand this in six months?

### Documentation

* Does `architecture.md` still accurately describe the system?

---

# 23. Definition of Done

A change is not complete merely because the implementation works locally.

For meaningful changes:

* [ ] Implementation is complete.
* [ ] Relevant tests pass.
* [ ] New behavior has appropriate test coverage.
* [ ] Type checking passes.
* [ ] Linting passes.
* [ ] No unnecessary unrelated changes remain.
* [ ] Error handling is appropriate.
* [ ] Security implications were considered.
* [ ] Performance implications were considered where relevant.
* [ ] `architecture.md` was updated if architecture changed.
* [ ] The final diff has been reviewed.

---

# 24. Non-Negotiable Rules

These rules override convenience:

1. **Do not break existing behavior unintentionally.**
2. **Do not silently swallow errors.**
3. **Do not introduce secrets into source control.**
4. **Do not bypass tests to make a change pass.**
5. **Do not use `Any` casually.**
6. **Do not create duplicate abstractions without investigating existing ones.**
7. **Do not introduce unnecessary dependencies.**
8. **Do not make architectural changes without updating `architecture.md`.**
9. **Do not leave architecture documentation knowingly stale.**
10. **Do not perform large unrelated refactors during feature work.**
11. **Do not optimize prematurely.**
12. **Do not sacrifice correctness for implementation speed.**
13. **Do not assume code behavior—verify it.**
14. **Do not declare a change complete without reviewing the resulting diff.**

---

# 25. Engineering Philosophy

The goal is not to produce the smallest diff.

The goal is not to produce the cleverest implementation.

The goal is:

> **Build a system that remains easy to understand, change, test, operate, and extend as Factor grows.**

AI makes writing code cheap.

That makes **architecture, correctness, context, and system coherence more important—not less**.

Every change should leave `cystatic-core` at least as understandable as it was before.

When making a choice, prefer the solution that a competent engineer—or a future coding agent—can understand and safely modify six months from now.