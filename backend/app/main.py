import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import api_v1, auth, keys, logs, users
from app.services import litellm, local_users
from app.version import VERSION


@asynccontextmanager
async def lifespan(_: FastAPI):
    local_users.init_db()
    await litellm.start_client()
    try:
        yield
    finally:
        await litellm.close_client()


app = FastAPI(
    title="LiteGate",
    version=VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def protect_cookie_sessions_from_csrf(request: Request, call_next):
    """Reject cross-site mutations authenticated only by the portal cookie."""
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.cookies.get("litegate_session")
        and not request.headers.get("authorization")
        and not request.headers.get("x-api-key")
    ):
        origin = request.headers.get("origin", "").rstrip("/")
        request_host = request.headers.get("host", "").casefold()
        origin_host = ""
        if "://" in origin:
            origin_host = origin.split("://", 1)[1].split("/", 1)[0].casefold()
        configured_origins = {value.rstrip("/") for value in settings.cors_origins_list}
        if origin and origin_host != request_host and origin not in configured_origins:
            return JSONResponse({"detail": "Cross-site mutation rejected"}, status_code=403)
        if not origin and request.headers.get("sec-fetch-site", "").casefold() == "cross-site":
            return JSONResponse({"detail": "Cross-site mutation rejected"}, status_code=403)
    return await call_next(request)

app.include_router(auth.router, prefix="/api")
app.include_router(keys.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(api_v1.router, prefix="/api")


@app.get("/api/portal-config")
async def portal_config():
    """Public config the frontend reads on load — no auth required."""
    hub_url = (settings.litellm_ui_url.rstrip("/") + "/ui/model_hub_table") if settings.litellm_ui_url else ""
    return {
        "support_ticket_url": settings.support_ticket_url,
        "logo_url": settings.logo_url,
        "litellm_ui_url": hub_url,
        "api_docs_url": "/api/docs",
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health/live")
async def liveness():
    return {"status": "ok"}


@app.get("/api/health/ready")
async def readiness():
    litellm_status, database_status = await asyncio.gather(
        litellm.healthcheck(),
        asyncio.to_thread(local_users.healthcheck),
    )
    ready = bool(litellm_status["ok"] and database_status["ok"])
    payload = {
        "status": "ready" if ready else "not_ready",
        "dependencies": {"litellm": litellm_status, "database": database_status},
    }
    return JSONResponse(payload, status_code=200 if ready else 503)
