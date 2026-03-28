#!/usr/bin/env python3
"""Optional Python entrypoint: call the Cystatic API with repo metadata."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = os.environ.get("CYSTATIC_API_URL")
    if not base:
        print("CYSTATIC_API_URL is required", file=sys.stderr)
        return 1
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    ref = os.environ.get("CYSTATIC_REF") or os.environ.get("GITHUB_SHA", "main")
    payload = {
        "repo_url": f"https://github.com/{repo}" if repo else "",
        "ref": ref,
        "changed_paths": [],
    }
    url = base.rstrip("/") + "/v1/blast-radius"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(resp.read().decode())
    except urllib.error.URLError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
