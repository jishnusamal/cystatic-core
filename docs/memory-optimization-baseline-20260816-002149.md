# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 163 | 1492106 | 1537 | 60 | 0 | 5.75 | 129.2 |
| polarsource/polar | 3023 | 17710874 | 8869 | 853 | 0 | 13.30 | 236.0 |
| PostHog/posthog | 32171 | 406063601 | 258 | 1211 | 0 | 48.23 | 682.2 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 80.4 | 80.4 |
| After repository facts & overlay load | 83.2 | 86.2 |
| After Change Compiler | 83.3 | 86.2 |
| After Behavior Compiler | 83.4 | 86.2 |
| After Operational Compiler | 83.4 | 86.2 |
| After Engineering Discovery Compiler | 83.4 | 86.2 |
| After Discovery IR Compiler | 83.5 | 86.2 |
| After system-model construction | 83.5 | 86.2 |
| After ReviewContext Compiler | 83.6 | 86.2 |
| After LLMContext Compiler | 83.6 | 86.2 |
| After context generation | 83.6 | 86.2 |
| before LLM request | 83.6 | 86.2 |
| after LLM request | 124.3 | 124.3 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 130.1 | 130.1 |
| After repository facts & overlay load | 152.1 | 236.0 |
| After Change Compiler | 151.4 | 236.0 |
| After Behavior Compiler | 150.7 | 236.0 |
| After Operational Compiler | 150.7 | 236.0 |
| After Engineering Discovery Compiler | 150.7 | 236.0 |
| After Discovery IR Compiler | 150.7 | 236.0 |
| After system-model construction | 150.7 | 236.0 |
| After ReviewContext Compiler | 150.8 | 236.0 |
| After LLMContext Compiler | 150.8 | 236.0 |
| After context generation | 150.8 | 236.0 |
| before LLM request | 150.9 | 236.0 |
| after LLM request | 147.5 | 236.0 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 86.8 | 86.8 |
| After repository facts & overlay load | 146.9 | 682.2 |
| After Change Compiler | 146.9 | 682.2 |
| After Behavior Compiler | 147.0 | 682.2 |
| After Operational Compiler | 147.1 | 682.2 |
| After Engineering Discovery Compiler | 147.1 | 682.2 |
| After Discovery IR Compiler | 147.2 | 682.2 |
| After system-model construction | 147.2 | 682.2 |
| After ReviewContext Compiler | 147.3 | 682.2 |
| After LLMContext Compiler | 147.3 | 682.2 |
| After context generation | 147.3 | 682.2 |
| before LLM request | 147.3 | 682.2 |
| after LLM request | 147.5 | 682.2 |
