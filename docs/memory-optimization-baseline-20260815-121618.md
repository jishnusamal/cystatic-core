# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 0 | 0 | 2167 | 3902 | 237 | 12.49 | 173.3 |
| polarsource/polar | 0 | 0 | 18849 | 25066 | 6155 | 70.07 | 602.9 |
| PostHog/posthog | 0 | 0 | 262908 | 617117 | 262003 | 1402.97 | 3738.9 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 79.0 | 79.0 |
| After base repository download | 84.2 | 84.2 |
| After endpoint extraction | 127.5 | 127.5 |
| After dependency/relationship extraction | 127.5 | 127.5 |
| After base graph compilation | 127.8 | 127.8 |
| After base RepositoryModel | 127.8 | 127.8 |
| After head source load | 127.9 | 127.9 |
| Before graph clone | 127.9 | 127.9 |
| peak during graph clone | 155.9 | 155.9 |
| After graph clone | 155.9 | 155.9 |
| After GraphPatcher | 156.1 | 156.1 |
| After head RepositoryModel | 156.1 | 156.1 |
| After Change Compiler | 156.1 | 156.1 |
| After Behavior Compiler | 156.1 | 156.1 |
| After Operational Compiler | 156.1 | 156.1 |
| After Engineering Discovery Compiler | 156.1 | 156.1 |
| After Discovery IR Compiler | 156.1 | 156.1 |
| After ReviewContext Compiler | 156.1 | 156.1 |
| After LLMContext Compiler | 156.1 | 156.1 |
| before LLM request | 156.1 | 156.1 |
| after LLM request | 173.3 | 173.3 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 155.3 | 155.3 |
| After base repository download | 282.8 | 282.8 |
| After endpoint extraction | 340.2 | 340.2 |
| After dependency/relationship extraction | 340.2 | 340.2 |
| After base graph compilation | 395.1 | 395.1 |
| After base RepositoryModel | 395.2 | 395.2 |
| After head source load | 374.7 | 395.4 |
| Before graph clone | 374.7 | 395.4 |
| peak during graph clone | 602.6 | 602.6 |
| After graph clone | 602.6 | 602.6 |
| After GraphPatcher | 602.9 | 602.9 |
| After head RepositoryModel | 602.9 | 602.9 |
| After Change Compiler | 602.9 | 602.9 |
| After Behavior Compiler | 602.9 | 602.9 |
| After Operational Compiler | 602.9 | 602.9 |
| After Engineering Discovery Compiler | 602.9 | 602.9 |
| After Discovery IR Compiler | 602.9 | 602.9 |
| After ReviewContext Compiler | 552.2 | 602.9 |
| After LLMContext Compiler | 552.2 | 602.9 |
| before LLM request | 549.5 | 602.9 |
| after LLM request | 546.1 | 602.9 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 351.6 | 351.6 |
| After base repository download | 1309.9 | 1309.9 |
| After endpoint extraction | 640.0 | 1318.3 |
| After dependency/relationship extraction | 640.0 | 1318.3 |
| After base graph compilation | 1822.6 | 1822.6 |
| After base RepositoryModel | 1840.3 | 1840.3 |
| After head source load | 1692.7 | 1855.9 |
| Before graph clone | 1692.8 | 1855.9 |
| peak during graph clone | 2592.3 | 2591.6 |
| After graph clone | 2592.6 | 2592.6 |
| After GraphPatcher | 2205.2 | 3487.6 |
| After head RepositoryModel | 2237.4 | 3487.6 |
| After Change Compiler | 3684.2 | 3738.9 |
| After Behavior Compiler | 3699.7 | 3738.9 |
| After Operational Compiler | 3153.5 | 3738.9 |
| After Engineering Discovery Compiler | 3154.2 | 3738.9 |
| After Discovery IR Compiler | 3143.3 | 3738.9 |
| After ReviewContext Compiler | 3149.1 | 3738.9 |
| After LLMContext Compiler | 3152.2 | 3738.9 |
| before LLM request | 3093.2 | 3738.9 |
| after LLM request | 2940.7 | 3738.9 |
