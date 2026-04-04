from fastapi import Header, HTTPException, Request
from schemas import AnalyzeRequest
import os, json
from .settings import get_settings

def verify_api_key(x_api_key: str = Header(...)):
    settings = get_settings()
    keys = json.loads(settings.cystatic_keys) if isinstance(settings.cystatic_keys, str) else settings.cystatic_keys
    
    if x_api_key not in keys.values():
        raise HTTPException(status_code=401, detail="Invalid API key")