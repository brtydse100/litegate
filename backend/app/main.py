from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import api_v1, auth, keys, logs, users
from app.services import local_users


@asynccontextmanager
async def lifespan(_: FastAPI):
    local_users.init_db()
    yield


app = FastAPI(
    title="LiteGate",
    version="2.4.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
