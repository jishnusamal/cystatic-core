# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 0 | 0 | 2167 | 3902 | 237 | 17.70 | 185.6 |
| polarsource/polar | 0 | 0 | 18849 | 25066 | 6155 | 123.56 | 649.9 |
| PostHog/posthog | 0 | 0 | 262908 | 617117 | 262003 | 2151.79 | 4040.8 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 67.6 | 67.6 |
| After base repository download | 72.3 | 72.3 |
| After parsing | 147.7 | 147.7 |
| After symbol extraction | 135.1 | 154.8 |
| After endpoint extraction | 135.2 | 154.8 |
| After dependency/relationship extraction | 135.2 | 154.8 |
| After base graph compilation | 184.0 | 184.0 |
| After base RepositoryModel | 184.1 | 184.1 |
| After head source load | 183.6 | 185.6 |
| Before graph clone | 183.6 | 185.6 |
| peak during graph clone | 177.1 | 185.5 |
| After graph clone | 177.1 | 185.6 |
| After GraphPatcher | 175.4 | 185.6 |
| After head RepositoryModel | 175.5 | 185.6 |
| After Change Compiler | 175.7 | 185.6 |
| After Behavior Compiler | 175.8 | 185.6 |
| After Operational Compiler | 175.9 | 185.6 |
| After Engineering Discovery Compiler | 175.9 | 185.6 |
| After Discovery IR Compiler | 175.9 | 185.6 |
| After ReviewContext Compiler | 175.9 | 185.6 |
| After LLMContext Compiler | 175.9 | 185.6 |
| before LLM request | 172.6 | 185.6 |
| after LLM request | 60.4 | 185.6 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 105.5 | 105.5 |
| After base repository download | 226.3 | 226.3 |
| After parsing | 592.8 | 596.8 |
| After symbol extraction | 438.0 | 596.8 |
| After endpoint extraction | 438.1 | 596.8 |
| After dependency/relationship extraction | 438.1 | 596.8 |
| After base graph compilation | 546.7 | 649.9 |
| After base RepositoryModel | 546.8 | 649.9 |
| After head source load | 528.2 | 649.9 |
| Before graph clone | 528.2 | 649.9 |
| peak during graph clone | 439.7 | 548.8 |
| After graph clone | 439.8 | 649.9 |
| After GraphPatcher | 175.9 | 649.9 |
| After head RepositoryModel | 178.7 | 649.9 |
| After Change Compiler | 370.2 | 649.9 |
| After Behavior Compiler | 376.5 | 649.9 |
| After Operational Compiler | 379.2 | 649.9 |
| After Engineering Discovery Compiler | 379.4 | 649.9 |
| After Discovery IR Compiler | 380.2 | 649.9 |
| After ReviewContext Compiler | 380.8 | 649.9 |
| After LLMContext Compiler | 381.4 | 649.9 |
| before LLM request | 384.1 | 649.9 |
| after LLM request | 45.2 | 649.9 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 353.9 | 353.9 |
| After base repository download | 730.9 | 744.6 |
| After parsing | 1970.0 | 2758.0 |
| After symbol extraction | 95.3 | 2758.0 |
| After endpoint extraction | 95.5 | 2758.0 |
| After dependency/relationship extraction | 95.5 | 2758.0 |
| After base graph compilation | 1442.4 | 2758.0 |
| After base RepositoryModel | 1461.4 | 2758.0 |
| After head source load | 54.6 | 2758.0 |
| Before graph clone | 54.6 | 2758.0 |
| peak during graph clone | 2818.4 | 3008.8 |
| After graph clone | 2818.7 | 3008.8 |
| After GraphPatcher | 2489.2 | 4040.8 |
| After head RepositoryModel | 2521.5 | 4040.8 |
| After Change Compiler | 3174.0 | 4040.8 |
| After Behavior Compiler | 3121.0 | 4040.8 |
| After Operational Compiler | 2672.8 | 4040.8 |
| After Engineering Discovery Compiler | 2673.8 | 4040.8 |
| After Discovery IR Compiler | 2665.1 | 4040.8 |
| After ReviewContext Compiler | 2621.0 | 4040.8 |
| After LLMContext Compiler | 2622.5 | 4040.8 |
| before LLM request | 2572.0 | 4040.8 |
| after LLM request | 1396.2 | 4040.8 |
