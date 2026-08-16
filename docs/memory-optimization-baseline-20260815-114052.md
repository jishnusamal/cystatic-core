# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 0 | 0 | 2167 | 3902 | 237 | 24.64 | 174.2 |
| polarsource/polar | 0 | 0 | 18849 | 25066 | 6155 | 60.69 | 549.9 |
| PostHog/posthog | 0 | 0 | 262908 | 617117 | 262003 | 1362.13 | 3932.7 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 79.0 | 79.0 |
| After base repository download | 84.2 | 84.2 |
| After endpoint extraction | 128.3 | 128.3 |
| After dependency/relationship extraction | 128.3 | 128.3 |
| After base graph compilation | 128.7 | 128.7 |
| After base RepositoryModel | 128.7 | 128.7 |
| After head source load | 128.8 | 128.8 |
| Before graph clone | 128.8 | 128.8 |
| peak during graph clone | 156.3 | 156.3 |
| After graph clone | 156.3 | 156.3 |
| After GraphPatcher | 156.4 | 156.4 |
| After head RepositoryModel | 156.5 | 156.5 |
| After Change Compiler | 156.5 | 156.5 |
| After Behavior Compiler | 156.5 | 156.5 |
| After Operational Compiler | 156.5 | 156.5 |
| After Engineering Discovery Compiler | 156.5 | 156.5 |
| After Discovery IR Compiler | 156.5 | 156.5 |
| After ReviewContext Compiler | 156.5 | 156.5 |
| After LLMContext Compiler | 156.5 | 156.5 |
| before LLM request | 156.5 | 156.5 |
| after LLM request | 174.2 | 174.2 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 156.2 | 156.2 |
| After base repository download | 318.0 | 318.0 |
| After endpoint extraction | 347.7 | 347.7 |
| After dependency/relationship extraction | 347.7 | 347.7 |
| After base graph compilation | 372.8 | 372.8 |
| After base RepositoryModel | 372.8 | 372.8 |
| After head source load | 250.8 | 372.8 |
| Before graph clone | 250.8 | 372.8 |
| peak during graph clone | 547.6 | 547.6 |
| After graph clone | 547.6 | 547.6 |
| After GraphPatcher | 549.6 | 549.6 |
| After head RepositoryModel | 549.6 | 549.6 |
| After Change Compiler | 549.8 | 549.8 |
| After Behavior Compiler | 549.8 | 549.8 |
| After Operational Compiler | 549.8 | 549.8 |
| After Engineering Discovery Compiler | 549.8 | 549.8 |
| After Discovery IR Compiler | 549.8 | 549.8 |
| After ReviewContext Compiler | 549.8 | 549.8 |
| After LLMContext Compiler | 549.9 | 549.9 |
| before LLM request | 549.9 | 549.9 |
| after LLM request | 549.9 | 549.9 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 359.0 | 359.0 |
| After base repository download | 1186.2 | 1186.2 |
| After endpoint extraction | 888.9 | 1258.2 |
| After dependency/relationship extraction | 888.9 | 1258.2 |
| After base graph compilation | 2290.8 | 2290.8 |
| After base RepositoryModel | 2280.2 | 2291.0 |
| After head source load | 2005.8 | 2295.7 |
| Before graph clone | 2005.8 | 2295.7 |
| peak during graph clone | 3394.5 | 3393.8 |
| After graph clone | 3394.8 | 3394.8 |
| After GraphPatcher | 2184.4 | 3932.7 |
| After head RepositoryModel | 2219.0 | 3932.7 |
| After Change Compiler | 2954.9 | 3932.7 |
| After Behavior Compiler | 3023.5 | 3932.7 |
| After Operational Compiler | 2372.8 | 3932.7 |
| After Engineering Discovery Compiler | 2373.2 | 3932.7 |
| After Discovery IR Compiler | 2370.6 | 3932.7 |
| After ReviewContext Compiler | 2402.8 | 3932.7 |
| After LLMContext Compiler | 2407.8 | 3932.7 |
| before LLM request | 2351.9 | 3932.7 |
| after LLM request | 2140.1 | 3932.7 |
