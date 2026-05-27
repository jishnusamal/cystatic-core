from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from api.settings import get_settings

router = APIRouter()


@router.api_route(
    "/health",
    methods=["GET", "HEAD"],
    dependencies=[Depends(get_settings)],
)
async def health(request: Request):
    if request.method == "HEAD":
        return Response(status_code=status.HTTP_200_OK)
    return {"status": "ok"}
