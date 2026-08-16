# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 163 | 1492106 | 1537 | 60 | 0 | 102.07 | 144.8 |
| polarsource/polar | 3023 | 17710874 | 8869 | 853 | 0 | 100.74 | 311.2 |
| PostHog/posthog | 32171 | 406063601 | 160946 | 1211 | 0 | 144.46 | 1043.2 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 80.2 | 80.2 |
| After repository facts & overlay load | 111.9 | 112.9 |
| After Change Compiler | 111.9 | 112.9 |
| After Behavior Compiler | 111.9 | 112.9 |
| After Operational Compiler | 111.9 | 112.9 |
| After Engineering Discovery Compiler | 111.9 | 112.9 |
| After Discovery IR Compiler | 111.9 | 112.9 |
| After system-model construction | 111.9 | 112.9 |
| After ReviewContext Compiler | 111.9 | 112.9 |
| After LLMContext Compiler | 111.9 | 112.9 |
| After context generation | 111.9 | 112.9 |
| before LLM request | 111.9 | 112.9 |
| after LLM request | 114.6 | 144.8 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 128.1 | 128.1 |
| After repository facts & overlay load | 311.1 | 311.1 |
| After Change Compiler | 311.1 | 311.1 |
| After Behavior Compiler | 311.1 | 311.1 |
| After Operational Compiler | 311.2 | 311.2 |
| After Engineering Discovery Compiler | 311.2 | 311.2 |
| After Discovery IR Compiler | 311.2 | 311.2 |
| After system-model construction | 311.2 | 311.2 |
| After ReviewContext Compiler | 311.2 | 311.2 |
| After LLMContext Compiler | 311.2 | 311.2 |
| After context generation | 311.2 | 311.2 |
| before LLM request | 311.2 | 311.2 |
| after LLM request | 167.0 | 311.2 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 168.0 | 168.0 |
| After repository facts & overlay load | 590.9 | 1043.2 |
| After Change Compiler | 590.9 | 1043.2 |
| After Behavior Compiler | 591.0 | 1043.2 |
| After Operational Compiler | 591.0 | 1043.2 |
| After Engineering Discovery Compiler | 591.0 | 1043.2 |
| After Discovery IR Compiler | 591.0 | 1043.2 |
| After system-model construction | 591.0 | 1043.2 |
| After ReviewContext Compiler | 591.1 | 1043.2 |
| After LLMContext Compiler | 591.1 | 1043.2 |
| After context generation | 591.1 | 1043.2 |
| before LLM request | 591.1 | 1043.2 |
| after LLM request | 193.0 | 1043.2 |
