# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 163 | 1492106 | 1537 | 60 | 0 | 5.34 | 131.2 |
| polarsource/polar | 3023 | 17710874 | 8869 | 853 | 0 | 10.14 | 228.3 |
| PostHog/posthog | 32171 | 406063601 | 258 | 1211 | 0 | 47.99 | 783.0 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 81.0 | 81.0 |
| After repository facts & overlay load | 88.9 | 88.9 |
| After Change Compiler | 89.1 | 89.1 |
| After Behavior Compiler | 89.1 | 89.1 |
| After Operational Compiler | 89.1 | 89.1 |
| After Engineering Discovery Compiler | 89.1 | 89.1 |
| After Discovery IR Compiler | 89.2 | 89.2 |
| After system-model construction | 89.2 | 89.2 |
| After ReviewContext Compiler | 89.2 | 89.2 |
| After LLMContext Compiler | 89.2 | 89.2 |
| After context generation | 89.2 | 89.2 |
| before LLM request | 89.2 | 89.2 |
| after LLM request | 126.7 | 126.7 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 131.5 | 131.5 |
| After repository facts & overlay load | 152.4 | 228.3 |
| After Change Compiler | 152.4 | 228.3 |
| After Behavior Compiler | 152.5 | 228.3 |
| After Operational Compiler | 152.5 | 228.3 |
| After Engineering Discovery Compiler | 152.5 | 228.3 |
| After Discovery IR Compiler | 152.6 | 228.3 |
| After system-model construction | 152.6 | 228.3 |
| After ReviewContext Compiler | 152.6 | 228.3 |
| After LLMContext Compiler | 152.6 | 228.3 |
| After context generation | 152.6 | 228.3 |
| before LLM request | 152.6 | 228.3 |
| after LLM request | 152.8 | 228.3 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 158.7 | 158.7 |
| After repository facts & overlay load | 132.5 | 783.0 |
| After Change Compiler | 132.5 | 783.0 |
| After Behavior Compiler | 132.6 | 783.0 |
| After Operational Compiler | 132.7 | 783.0 |
| After Engineering Discovery Compiler | 132.7 | 783.0 |
| After Discovery IR Compiler | 132.8 | 783.0 |
| After system-model construction | 132.8 | 783.0 |
| After ReviewContext Compiler | 132.9 | 783.0 |
| After LLMContext Compiler | 132.9 | 783.0 |
| After context generation | 132.9 | 783.0 |
| before LLM request | 132.9 | 783.0 |
| after LLM request | 131.2 | 783.0 |
