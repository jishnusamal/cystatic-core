# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 0 | 0 | 2167 | 3902 | 237 | 25.16 | 210.4 |
| polarsource/polar | 0 | 0 | 18849 | 25066 | 6155 | 99.76 | 848.5 |
| PostHog/posthog | 0 | 0 | 262908 | 617117 | 262003 | 1914.97 | 2940.5 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 78.9 | 78.9 |
| After base repository download | 83.9 | 83.9 |
| After parsing | 158.3 | 158.3 |
| After symbol extraction | 169.0 | 169.0 |
| After endpoint extraction | 169.0 | 169.0 |
| After dependency/relationship extraction | 169.0 | 169.0 |
| After base graph compilation | 193.9 | 193.9 |
| After base RepositoryModel | 193.9 | 193.9 |
| After head source load | 194.0 | 194.0 |
| Before graph clone | 194.0 | 194.0 |
| peak during graph clone | 202.0 | 202.0 |
| After graph clone | 202.0 | 202.0 |
| After GraphPatcher | 202.1 | 202.1 |
| After head RepositoryModel | 202.2 | 202.2 |
| After Change Compiler | 202.2 | 202.2 |
| After Behavior Compiler | 202.2 | 202.2 |
| After Operational Compiler | 202.2 | 202.2 |
| After Engineering Discovery Compiler | 202.2 | 202.2 |
| After Discovery IR Compiler | 202.2 | 202.2 |
| After ReviewContext Compiler | 202.2 | 202.2 |
| After LLMContext Compiler | 202.2 | 202.2 |
| before LLM request | 202.2 | 202.2 |
| after LLM request | 200.5 | 210.4 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 183.6 | 183.6 |
| After base repository download | 337.0 | 337.0 |
| After parsing | 720.0 | 720.0 |
| After symbol extraction | 799.5 | 799.5 |
| After endpoint extraction | 799.5 | 799.5 |
| After dependency/relationship extraction | 799.5 | 799.5 |
| After base graph compilation | 816.0 | 816.0 |
| After base RepositoryModel | 816.0 | 816.0 |
| After head source load | 816.1 | 816.1 |
| Before graph clone | 816.1 | 816.1 |
| peak during graph clone | 765.1 | 848.5 |
| After graph clone | 765.1 | 848.5 |
| After GraphPatcher | 669.4 | 848.5 |
| After head RepositoryModel | 669.4 | 848.5 |
| After Change Compiler | 669.4 | 848.5 |
| After Behavior Compiler | 669.4 | 848.5 |
| After Operational Compiler | 669.4 | 848.5 |
| After Engineering Discovery Compiler | 669.4 | 848.5 |
| After Discovery IR Compiler | 669.4 | 848.5 |
| After ReviewContext Compiler | 669.4 | 848.5 |
| After LLMContext Compiler | 669.4 | 848.5 |
| before LLM request | 669.4 | 848.5 |
| after LLM request | 669.4 | 848.5 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 639.5 | 639.5 |
| After base repository download | 1513.4 | 1513.4 |
| After parsing | 492.9 | 2940.5 |
| After symbol extraction | 1098.7 | 2940.5 |
| After endpoint extraction | 1098.9 | 2940.5 |
| After dependency/relationship extraction | 1098.9 | 2940.5 |
| After base graph compilation | 688.3 | 2940.5 |
| After base RepositoryModel | 555.0 | 2940.5 |
| After head source load | 71.9 | 2940.5 |
| Before graph clone | 71.9 | 2940.5 |
| peak during graph clone | 1930.2 | 2222.9 |
| After graph clone | 1930.5 | 2940.5 |
| After GraphPatcher | 698.3 | 2940.5 |
| After head RepositoryModel | 718.5 | 2940.5 |
| After Change Compiler | 1244.0 | 2940.5 |
| After Behavior Compiler | 951.6 | 2940.5 |
| After Operational Compiler | 1399.4 | 2940.5 |
| After Engineering Discovery Compiler | 1402.9 | 2940.5 |
| After Discovery IR Compiler | 1428.6 | 2940.5 |
| After ReviewContext Compiler | 1226.9 | 2940.5 |
| After LLMContext Compiler | 1182.5 | 2940.5 |
| before LLM request | 1102.4 | 2940.5 |
| after LLM request | 45.6 | 2940.5 |
