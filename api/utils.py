from fastapi import Header, HTTPException
import os, json
from .settings import get_settings

# def verify_api_key(x_api_key: str = Header(...)):
#     print(f"Received API Key: {x_api_key} \n{API_KEYS}")
#     if x_api_key not in API_KEYS.values():
#         raise HTTPException(status_code=401, detail="Invalid API Key")
    
def verify_api_key(x_api_key: str = Header(...)):
    settings = get_settings()
    keys = settings.CYSTATIC_KEYS.to_dict() if isinstance(settings.CYSTATIC_KEYS, dict) else json.loads(settings.CYSTATIC_KEYS)
    # print(f"Received API Key: {x_api_key} \n{type(keys)} {keys}")
    
    if x_api_key not in keys.values():
        raise HTTPException(status_code=401, detail="Invalid API key")