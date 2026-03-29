# Cystatic System Architecture

## High-Level Flow

```mermaid

flowchart TD
   A[PR Created/New commit on existing PR] --> B[GitHub Actions Workflow]
   B --> C[FastAPI Server]
   C --> D["Source Adapter (GitHub/Gitlab/Bitbucket/Custom)"]
   D --> E["Language Adapter (Python/TS)"]
   E --> F["Core Engine"]
   F --> G["Output Adapter (Github/Gitlab/Slack/...)"]

```