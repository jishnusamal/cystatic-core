# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 163 | 1492106 | 1537 | 60 | 0 | 6.15 | 124.9 |
| polarsource/polar | 3023 | 17710874 | 8869 | 853 | 0 | 11.53 | 229.2 |
| PostHog/posthog | 32171 | 406063601 | 258 | 1211 | 0 | 55.11 | 700.1 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 80.7 | 80.7 |
| After repository facts & overlay load | 84.7 | 87.5 |
| After Change Compiler | 84.9 | 87.5 |
| After Behavior Compiler | 84.9 | 87.5 |
| After Operational Compiler | 84.9 | 87.5 |
| After Engineering Discovery Compiler | 84.9 | 87.5 |
| After Discovery IR Compiler | 84.9 | 87.5 |
| After system-model construction | 84.9 | 87.5 |
| After ReviewContext Compiler | 84.9 | 87.5 |
| After LLMContext Compiler | 84.9 | 87.5 |
| After context generation | 84.9 | 87.5 |
| before LLM request | 85.0 | 87.5 |
| after LLM request | 114.6 | 124.9 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 121.1 | 121.1 |
| After repository facts & overlay load | 148.0 | 229.2 |
| After Change Compiler | 147.8 | 229.2 |
| After Behavior Compiler | 147.6 | 229.2 |
| After Operational Compiler | 147.7 | 229.2 |
| After Engineering Discovery Compiler | 147.7 | 229.2 |
| After Discovery IR Compiler | 147.7 | 229.2 |
| After system-model construction | 147.7 | 229.2 |
| After ReviewContext Compiler | 147.7 | 229.2 |
| After LLMContext Compiler | 147.7 | 229.2 |
| After context generation | 147.7 | 229.2 |
| before LLM request | 147.7 | 229.2 |
| after LLM request | 114.8 | 229.2 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 95.7 | 95.7 |
| After repository facts & overlay load | 146.3 | 700.1 |
| After Change Compiler | 146.3 | 700.1 |
| After Behavior Compiler | 146.4 | 700.1 |
| After Operational Compiler | 146.4 | 700.1 |
| After Engineering Discovery Compiler | 146.4 | 700.1 |
| After Discovery IR Compiler | 146.4 | 700.1 |
| After system-model construction | 146.4 | 700.1 |
| After ReviewContext Compiler | 146.6 | 700.1 |
| After LLMContext Compiler | 146.6 | 700.1 |
| After context generation | 146.6 | 700.1 |
| before LLM request | 146.6 | 700.1 |
| after LLM request | 146.8 | 700.1 |
