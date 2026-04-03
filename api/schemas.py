"""Request and response models for the API."""

from __future__ import annotations
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str = "ok"
    

class AnalyzeRequest(BaseModel):
    """Minimal payload to trigger an analysis run."""
    repo: str = Field(..., description="Clone URL or web URL for the repository")
    pr_number: int = Field(default=0, description="Pull request number")
    diff_url: str = Field(..., description="URL for the diff of the PR")
    diff: str = Field(..., description="The diff content")
    
    """
    repo='cystatichq/cystatic-demo-python-app' 
    pr_number=1 
    diff_url='https://api.github.com/repos/cystatichq/cystatic-demo-python-app/pulls/1' 
    diff='diff --git a/app/auth.py b/app/auth.py\nindex 8a0a131..bc29a72 100644\n--- a/app/auth.py\n+++ b/app/auth.py\n@@ -6,4 +6,5 @@\n \n def authenticate(username: str, password: str) -> bool:\n     ""Return True when the username and password match.""\n-    return USERS.get(username) == password\n+    return True\n+    # return USERS.get(username) == password\n'
    """

class BlastRadiusResponse(BaseModel):
    affected_files: list[str]
    impact_score: float
    risk_level: str
