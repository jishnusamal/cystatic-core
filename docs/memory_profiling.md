# Memory Profiling Documentation

This document explains how to enable and use the temporary memory profiling layer in the Factor backend to diagnose memory footprint spikes during PR analysis.

## How to Run Locally

To start the API server locally with memory profiling enabled, prefix the startup command with `MEMORY_PROFILING=true`:

```bash
MEMORY_PROFILING=true infisical run -- uv run uvicorn api.main:app --reload
```

## How to Run on Render

To enable profiling on a Render service deployment:

1. Navigate to the service Dashboard on Render.
2. Go to **Environment**.
3. Add a new environment variable:
   - **Key**: `MEMORY_PROFILING`
   - **Value**: `true`
4. Save the changes. The service will automatically redeploy with memory profiling enabled.

---

## Log Checkpoint Reference

When enabled, the application monitors process Resident Set Size (RSS) and Python heap allocations using `psutil` and `tracemalloc`. 

Look for the following log tags in your service console:
- `[MEMORY]`: Reports RSS progression, deltas ($\Delta$), and peak values at key request stages.
- `[TRACEMALLOC]`: Reports active Python heap footprints (current vs peak).
- `[TRACEMALLOC-TOP]`: Reports the top 15 source locations (file:line) triggering the largest allocations.
