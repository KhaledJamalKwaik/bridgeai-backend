from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, JSONResponse
import httpx

from app.core.config import settings

router = APIRouter()


@router.get("/gateway/health")
async def gateway_health():
    return {"status": "ok", "upstream": settings.GATEWAY_UPSTREAM}


@router.api_route("/gateway/proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def gateway_proxy(path: str, request: Request):
    """
    Proxy requests to an upstream service configured in `GATEWAY_UPSTREAM`.

    The middleware in this repo applies a simple in-memory rate limiter. For production use,
    configure a proper gateway (API Gateway, Kong, Traefik, or a Redis-backed limiter).
    """
    upstream = settings.GATEWAY_UPSTREAM
    if not upstream:
        # no upstream configured — return a helpful error
        raise HTTPException(status_code=501, detail="No GATEWAY_UPSTREAM configured")

    url = upstream.rstrip("/") + "/" + path

    # Prepare request to upstream preserving method, headers and body
    method = request.method
    headers = dict(request.headers)
    # remove host to avoid confusion
    headers.pop("host", None)

    body = await request.body()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.request(method, url, headers=headers, content=body, params=request.query_params)
        except httpx.RequestError as e:
            return JSONResponse(status_code=502, content={"detail": "Upstream request failed", "error": str(e)})

    return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
