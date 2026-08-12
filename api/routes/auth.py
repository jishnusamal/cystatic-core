"""Auth routes stub.

TODO: Implement auth endpoints (Clerk webhook, session verification, etc.)
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


# TODO: Add auth endpoints
# @router.post("/webhook")
# async def clerk_webhook(request: Request) -> dict:
#     """Handle Clerk webhook events."""
#     ...
#
# @router.get("/me")
# async def get_current_user(token: str = Depends(verify_token)) -> UserResponse:
#     """Get the current authenticated user."""
#     ...
