# Memory Optimization Baseline

> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories.

## Repository Metrics Summary

| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |
|---|---|---|---|---|---|---|---|
| pallets/click | 0 | 0 | 2167 | 3902 | 237 | 21.34 | 196.8 |
| polarsource/polar | 0 | 0 | 18849 | 25066 | 6155 | 89.77 | 676.2 |
| PostHog/posthog | 0 | 0 | 262908 | 617117 | 262003 | 1788.66 | 3183.2 |

## Checkpoint Details (RSS / Peak RSS in MB)

### pallets/click (PR #3762)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 79.1 | 79.1 |
| After base repository download | 83.7 | 83.7 |
| After parsing | 157.9 | 157.9 |
| After symbol extraction | 151.5 | 162.8 |
| After endpoint extraction | 151.5 | 162.8 |
| After dependency/relationship extraction | 151.5 | 162.8 |
| After base graph compilation | 185.9 | 185.9 |
| After base RepositoryModel | 186.0 | 186.0 |
| After head source load | 186.0 | 186.3 |
| Before graph clone | 186.0 | 186.3 |
| peak during graph clone | 194.8 | 194.8 |
| After graph clone | 194.8 | 194.8 |
| After GraphPatcher | 194.9 | 194.9 |
| After head RepositoryModel | 194.9 | 194.9 |
| After Change Compiler | 194.9 | 194.9 |
| After Behavior Compiler | 194.9 | 194.9 |
| After Operational Compiler | 195.0 | 195.0 |
| After Engineering Discovery Compiler | 195.0 | 195.0 |
| After Discovery IR Compiler | 195.0 | 195.0 |
| After ReviewContext Compiler | 195.0 | 195.0 |
| After LLMContext Compiler | 195.0 | 195.0 |
| before LLM request | 194.8 | 195.0 |
| after LLM request | 61.1 | 196.8 |

### polarsource/polar (PR #9204)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 113.3 | 113.3 |
| After base repository download | 225.9 | 225.9 |
| After parsing | 599.5 | 600.6 |
| After symbol extraction | 547.2 | 600.6 |
| After endpoint extraction | 547.2 | 600.6 |
| After dependency/relationship extraction | 547.2 | 600.6 |
| After base graph compilation | 575.0 | 676.2 |
| After base RepositoryModel | 575.2 | 676.2 |
| After head source load | 426.5 | 676.2 |
| Before graph clone | 426.5 | 676.2 |
| peak during graph clone | 314.4 | 426.5 |
| After graph clone | 314.5 | 676.2 |
| After GraphPatcher | 179.9 | 676.2 |
| After head RepositoryModel | 180.2 | 676.2 |
| After Change Compiler | 355.7 | 676.2 |
| After Behavior Compiler | 360.6 | 676.2 |
| After Operational Compiler | 363.1 | 676.2 |
| After Engineering Discovery Compiler | 363.2 | 676.2 |
| After Discovery IR Compiler | 364.0 | 676.2 |
| After ReviewContext Compiler | 364.5 | 676.2 |
| After LLMContext Compiler | 365.2 | 676.2 |
| before LLM request | 367.8 | 676.2 |
| after LLM request | 67.2 | 676.2 |

### PostHog/posthog (PR #72474)

| Checkpoint | Current RSS (MB) | Peak RSS (MB) |
|---|---|---|
| request start | 396.6 | 396.6 |
| After base repository download | 582.4 | 673.6 |
| After parsing | 399.9 | 3183.2 |
| After symbol extraction | 252.5 | 3183.2 |
| After endpoint extraction | 252.7 | 3183.2 |
| After dependency/relationship extraction | 252.7 | 3183.2 |
| After base graph compilation | 1611.7 | 3183.2 |
| After base RepositoryModel | 1639.3 | 3183.2 |
| After head source load | 58.7 | 3183.2 |
| Before graph clone | 58.7 | 3183.2 |
| peak during graph clone | 1317.0 | 1697.5 |
| After graph clone | 1317.3 | 3183.2 |
| After GraphPatcher | 1657.6 | 3183.2 |
| After head RepositoryModel | 1589.6 | 3183.2 |
| After Change Compiler | 1806.3 | 3183.2 |
| After Behavior Compiler | 1676.9 | 3183.2 |
| After Operational Compiler | 1176.5 | 3183.2 |
| After Engineering Discovery Compiler | 1183.0 | 3183.2 |
| After Discovery IR Compiler | 1215.6 | 3183.2 |
| After ReviewContext Compiler | 1291.4 | 3183.2 |
| After LLMContext Compiler | 1283.0 | 3183.2 |
| before LLM request | 1325.6 | 3183.2 |
| after LLM request | 433.5 | 3183.2 |
