# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 0 | 0 | 2167 | 3902 | 237 | 18.85 | 161.6 |
| polarsource/polar | 0 | 0 | 18849 | 25066 | 6155 | 84.58 | 492.2 |
| PostHog/posthog | 0 | 0 | 262908 | 617117 | 262003 | 1430.22 | 3320.2 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 79.0 | 79.0 |
| After base repository download | 83.5 | 83.5 |
| After endpoint extraction | 126.9 | 126.9 |
| After dependency/relationship extraction | 126.9 | 126.9 |
| After base graph compilation | 127.1 | 127.1 |
| After base RepositoryModel | 127.2 | 127.2 |
| After head source load | 127.2 | 127.2 |
| Before graph clone | 127.2 | 127.2 |
| peak during graph clone | 150.4 | 150.4 |
| After graph clone | 150.4 | 150.4 |
| After GraphPatcher | 150.5 | 150.5 |
| After head RepositoryModel | 150.5 | 150.5 |
| After Change Compiler | 150.5 | 150.5 |
| After Behavior Compiler | 150.5 | 150.5 |
| After Operational Compiler | 150.5 | 150.5 |
| After Engineering Discovery Compiler | 150.5 | 150.5 |
| After Discovery IR Compiler | 150.5 | 150.5 |
| After ReviewContext Compiler | 150.5 | 150.5 |
| After LLMContext Compiler | 150.6 | 150.6 |
| before LLM request | 150.6 | 150.6 |
| after LLM request | 148.9 | 161.6 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 141.5 | 141.5 |
| After base repository download | 309.8 | 309.8 |
| After endpoint extraction | 204.4 | 319.5 |
| After dependency/relationship extraction | 204.4 | 319.5 |
| After base graph compilation | 257.7 | 319.5 |
| After base RepositoryModel | 257.4 | 319.5 |
| After head source load | 233.7 | 319.5 |
| Before graph clone | 233.7 | 319.5 |
| peak during graph clone | 486.4 | 486.4 |
| After graph clone | 486.4 | 486.4 |
| After GraphPatcher | 178.8 | 492.2 |
| After head RepositoryModel | 181.7 | 492.2 |
| After Change Compiler | 285.6 | 492.2 |
| After Behavior Compiler | 290.8 | 492.2 |
| After Operational Compiler | 292.2 | 492.2 |
| After Engineering Discovery Compiler | 292.5 | 492.2 |
| After Discovery IR Compiler | 293.2 | 492.2 |
| After ReviewContext Compiler | 293.9 | 492.2 |
| After LLMContext Compiler | 294.5 | 492.2 |
| before LLM request | 297.4 | 492.2 |
| after LLM request | 45.2 | 492.2 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 275.6 | 275.6 |
| After base repository download | 525.5 | 746.2 |
| After endpoint extraction | 219.0 | 746.2 |
| After dependency/relationship extraction | 219.0 | 746.2 |
| After base graph compilation | 1078.6 | 1307.3 |
| After base RepositoryModel | 1094.4 | 1307.3 |
| After head source load | 62.6 | 1307.3 |
| Before graph clone | 62.7 | 1307.3 |
| peak during graph clone | 1654.3 | 2781.4 |
| After graph clone | 1654.7 | 2781.4 |
| After GraphPatcher | 2189.7 | 2781.4 |
| After head RepositoryModel | 2220.8 | 2781.4 |
| After Change Compiler | 3184.5 | 3320.2 |
| After Behavior Compiler | 3232.9 | 3320.2 |
| After Operational Compiler | 3216.2 | 3320.2 |
| After Engineering Discovery Compiler | 3216.4 | 3320.2 |
| After Discovery IR Compiler | 3222.3 | 3320.2 |
| After ReviewContext Compiler | 3226.7 | 3320.2 |
| After LLMContext Compiler | 3228.9 | 3320.2 |
| before LLM request | 3212.7 | 3320.2 |
| after LLM request | 2874.8 | 3320.2 |
