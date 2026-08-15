# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 0 | 0 | 0 | 0 | 0 | 5.75 | 121.4 |
| polarsource/polar | 0 | 0 | 0 | 0 | 0 | 12.00 | 134.5 |
| PostHog/posthog | 0 | 0 | 0 | 0 | 0 | 47.39 | 131.9 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 80.3 | 80.3 |
| After Change Compiler | 85.8 | 85.8 |
| After Behavior Compiler | 85.8 | 85.8 |
| After Operational Compiler | 85.9 | 85.9 |
| After Engineering Discovery Compiler | 85.9 | 85.9 |
| After Discovery IR Compiler | 85.9 | 85.9 |
| After ReviewContext Compiler | 85.9 | 85.9 |
| After LLMContext Compiler | 85.9 | 85.9 |
| before LLM request | 86.0 | 86.0 |
| after LLM request | 121.2 | 121.4 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 122.1 | 122.1 |
| After Change Compiler | 132.4 | 134.5 |
| After Behavior Compiler | 132.4 | 134.5 |
| After Operational Compiler | 132.5 | 134.5 |
| After Engineering Discovery Compiler | 132.5 | 134.5 |
| After Discovery IR Compiler | 132.5 | 134.5 |
| After ReviewContext Compiler | 132.5 | 134.5 |
| After LLMContext Compiler | 132.5 | 134.5 |
| before LLM request | 132.5 | 134.5 |
| after LLM request | 131.5 | 134.5 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 130.5 | 130.5 |
| After Change Compiler | 124.8 | 131.9 |
| After Behavior Compiler | 124.9 | 131.9 |
| After Operational Compiler | 124.9 | 131.9 |
| After Engineering Discovery Compiler | 124.9 | 131.9 |
| After Discovery IR Compiler | 124.9 | 131.9 |
| After ReviewContext Compiler | 125.0 | 131.9 |
| After LLMContext Compiler | 125.0 | 131.9 |
| before LLM request | 125.0 | 131.9 |
| after LLM request | 125.2 | 131.9 |
