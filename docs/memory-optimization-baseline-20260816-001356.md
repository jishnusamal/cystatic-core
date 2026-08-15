# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 0 | 0 | 0 | 0 | 0 | 14.50 | 123.1 |
| polarsource/polar | 0 | 0 | 0 | 0 | 0 | 170.23 | 285.2 |
| PostHog/posthog | 0 | 0 | 0 | 0 | 0 | 43.08 | 147.1 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 74.3 | 74.3 |
| After Change Compiler | 106.4 | 106.4 |
| After Behavior Compiler | 106.4 | 106.4 |
| After Operational Compiler | 106.4 | 106.4 |
| After Engineering Discovery Compiler | 106.4 | 106.4 |
| After Discovery IR Compiler | 106.4 | 106.4 |
| After ReviewContext Compiler | 106.4 | 106.4 |
| After LLMContext Compiler | 106.4 | 106.4 |
| before LLM request | 106.4 | 106.4 |
| after LLM request | 101.9 | 123.1 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 107.7 | 107.7 |
| After Change Compiler | 148.8 | 285.2 |
| After Behavior Compiler | 148.9 | 285.2 |
| After Operational Compiler | 148.9 | 285.2 |
| After Engineering Discovery Compiler | 148.9 | 285.2 |
| After Discovery IR Compiler | 148.9 | 285.2 |
| After ReviewContext Compiler | 148.9 | 285.2 |
| After LLMContext Compiler | 149.0 | 285.2 |
| before LLM request | 149.0 | 285.2 |
| after LLM request | 145.2 | 285.2 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 144.4 | 144.4 |
| After Change Compiler | 138.7 | 147.1 |
| After Behavior Compiler | 138.7 | 147.1 |
| After Operational Compiler | 138.8 | 147.1 |
| After Engineering Discovery Compiler | 138.8 | 147.1 |
| After Discovery IR Compiler | 138.8 | 147.1 |
| After ReviewContext Compiler | 138.8 | 147.1 |
| After LLMContext Compiler | 138.8 | 147.1 |
| before LLM request | 138.9 | 147.1 |
| after LLM request | 137.3 | 147.1 |
