# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 163 | 1492106 | 1537 | 60 | 0 | 5.70 | 133.3 |
| polarsource/polar | 3023 | 17710874 | 8869 | 853 | 0 | 10.08 | 230.2 |
| PostHog/posthog | 32171 | 406063601 | 258 | 1211 | 0 | 47.81 | 764.4 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 80.6 | 80.6 |
| After repository facts & overlay load | 91.1 | 91.1 |
| After Change Compiler | 91.2 | 91.2 |
| After Behavior Compiler | 91.2 | 91.2 |
| After Operational Compiler | 91.2 | 91.2 |
| After Engineering Discovery Compiler | 91.2 | 91.2 |
| After Discovery IR Compiler | 91.2 | 91.2 |
| After system-model construction | 91.2 | 91.2 |
| After ReviewContext Compiler | 91.3 | 91.3 |
| After LLMContext Compiler | 91.3 | 91.3 |
| After context generation | 91.3 | 91.3 |
| before LLM request | 91.3 | 91.3 |
| after LLM request | 128.7 | 133.3 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 130.8 | 130.8 |
| After repository facts & overlay load | 146.9 | 230.2 |
| After Change Compiler | 144.0 | 230.2 |
| After Behavior Compiler | 144.1 | 230.2 |
| After Operational Compiler | 144.1 | 230.2 |
| After Engineering Discovery Compiler | 144.1 | 230.2 |
| After Discovery IR Compiler | 144.1 | 230.2 |
| After system-model construction | 144.1 | 230.2 |
| After ReviewContext Compiler | 144.1 | 230.2 |
| After LLMContext Compiler | 144.1 | 230.2 |
| After context generation | 144.1 | 230.2 |
| before LLM request | 144.2 | 230.2 |
| after LLM request | 127.3 | 230.2 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 99.0 | 99.0 |
| After repository facts & overlay load | 145.8 | 764.4 |
| After Change Compiler | 145.8 | 764.4 |
| After Behavior Compiler | 146.0 | 764.4 |
| After Operational Compiler | 146.0 | 764.4 |
| After Engineering Discovery Compiler | 146.0 | 764.4 |
| After Discovery IR Compiler | 146.1 | 764.4 |
| After system-model construction | 146.1 | 764.4 |
| After ReviewContext Compiler | 146.2 | 764.4 |
| After LLMContext Compiler | 146.2 | 764.4 |
| After context generation | 146.2 | 764.4 |
| before LLM request | 146.3 | 764.4 |
| after LLM request | 146.0 | 764.4 |
