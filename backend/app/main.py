import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import SessionLocal
from app.routers import assistant, auth, dashboards, domains, health, industry_map, info_items, intake
from app.services.bootstrap import seed_domains_if_empty, seed_users_if_empty

logger = logging.getLogger(__name__)

_ALLOWED_ORIGINS_ENV = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8080,http://127.0.0.1:8080",
)
ALLOWED_ORIGINS = [o.strip() for o in _ALLOWED_ORIGINS_ENV.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.getenv("SECRET_KEY"):
        logger.warning(
            "⚠️  SECRET_KEY 未通过环境变量配置，当前使用默认不安全值。"
            "生产环境请务必设置随机强密钥：SECRET_KEY=<随机字符串>"
        )
    try:
        db = SessionLocal()
        try:
            seed_domains_if_empty(db)
            seed_users_if_empty(db)
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover
        logger.warning("database bootstrap skipped: %s", exc)
    yield

app = FastAPI(title="Tech Intel API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(domains.router, prefix="/api")
app.include_router(info_items.router, prefix="/api")
app.include_router(intake.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")
app.include_router(dashboards.router, prefix="/api")
app.include_router(industry_map.router, prefix="/api")
