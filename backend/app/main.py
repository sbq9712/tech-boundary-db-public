import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import SessionLocal
from app.routers import assistant, assistant_stream, auth, breadth, breadth_qa, conversations, dashboards, delivery_intel, domains, health, industry_map, info_items, intake, parameter_observations, uploads, users
from app.services.bootstrap import seed_domains_if_empty, seed_users_if_empty
from app.services.upload_ingestion import recover_pending_uploads

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
            # 域表种子（/data/domains.json 可选）失败不得阻断管理员引导：
            # 隔离/最小化部署目录里没有 domains.json 时曾把 seed_users 一并跳过，
            # 结果库中无任何用户、无人能登录（八 隔离复现）。
            try:
                seed_domains_if_empty(db)
            except Exception as exc:  # pragma: no cover
                logger.warning("domain seed skipped: %s", exc)
            seed_users_if_empty(db)
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover
        logger.warning("database bootstrap skipped: %s", exc)
    if os.getenv("TECHDB_UPLOAD_RECOVERY_ENABLED", "true").lower() in {"1", "true", "yes"}:
        threading.Thread(
            target=recover_pending_uploads,
            name="upload-ingestion-recovery",
            daemon=True,
        ).start()
    # 广度问答索引持久队列：导入记录 → canonical-qa 增量索引的收口。
    # 独立开关（默认开）；崩溃/重启后遗留 processing 任务自动续跑。
    if os.getenv("TECHDB_BREADTH_INDEX_WORKER_ENABLED", "true").lower() in {"1", "true", "yes"}:
        from app.services.breadth_index_queue import run_worker

        threading.Thread(
            target=run_worker,
            name="breadth-index-queue",
            daemon=True,
        ).start()
    yield

app = FastAPI(title="Tech Intel API", version="0801", lifespan=lifespan)

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
app.include_router(assistant_stream.router, prefix="/api")
app.include_router(dashboards.router, prefix="/api")
app.include_router(industry_map.router, prefix="/api")
app.include_router(parameter_observations.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(delivery_intel.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(breadth.router, prefix="/api")
app.include_router(breadth_qa.router, prefix="/api")
