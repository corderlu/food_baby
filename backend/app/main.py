"""爱心小食堂 · 后端入口。

启动顺序：
1. 建表（Base.metadata.create_all）
2. 灌种子数据（管理员 / 店铺设置 / 示例菜单 + 占位图），幂等
3. 挂载路由、静态目录
4. 起一个后台协程，定期把"还没开始做"的超时订单自动取消
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .api import admin_auth, admin_dishes, admin_orders, admin_settings, menu, orders
from .config import BACKEND_DIR, settings
from .database import Base, SessionLocal, engine
from .deps import get_current_admin
from .services.images import has_cjk_font, upload_root
from .services.orders import BusinessError, auto_cancel_stale
from .services.seed import seed_all
from .utils.timeutil import iso, now_naive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("food_baby")

#: 前端构建产物目录（frontend/dist），存在就一起发，方便不用 Nginx 的场景
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"


# ---------------------------------------------------------------------------
# 后台巡检
# ---------------------------------------------------------------------------


async def _auto_cancel_loop() -> None:
    interval = max(15, settings.auto_cancel_interval_seconds)
    logger.info(
        "超时自动取消巡检已启动：每 %d 秒检查一次，阈值 %d 分钟（仅未开始制作的订单）",
        interval,
        settings.order_auto_cancel_minutes,
    )
    while True:
        try:
            await asyncio.sleep(interval)
            db = SessionLocal()
            try:
                auto_cancel_stale(db)
            finally:
                db.close()
        except asyncio.CancelledError:
            logger.info("超时巡检已停止")
            raise
        except Exception:  # noqa: BLE001
            logger.exception("超时巡检出错（已忽略，下一轮继续）")


# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logger.info("=" * 62)
    logger.info("爱心小食堂 后端启动中…")

    Base.metadata.create_all(bind=engine)
    db_file = settings.sqlite_path
    logger.info("数据库：%s", db_file)

    upload_root()
    logger.info("上传目录：%s", settings.upload_path)

    if not has_cjk_font():
        logger.warning(
            "未找到中文字体，自动生成的占位图上中文会显示为方块。"
            "Linux 上执行：sudo apt install -y fonts-wqy-zenhei"
        )

    db = SessionLocal()
    try:
        result = seed_all(db)
    finally:
        db.close()
    if result["admin_created"]:
        logger.info(
            "初始管理员：%s / %s（请登录后立刻修改密码）",
            settings.admin_username,
            settings.admin_password,
        )

    task = asyncio.create_task(_auto_cancel_loop())
    logger.info("本地接口文档：http://127.0.0.1:%d/docs", settings.port)
    logger.info("=" * 62)

    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("爱心小食堂 后端已停止")


app = FastAPI(
    title="爱心小食堂 API",
    description="情侣专属点餐系统后端。顾客端无需登录，管理端需要 Bearer Token。",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# 中间件
# ---------------------------------------------------------------------------

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------------------------------------------------------------------------
# 异常处理：把业务异常翻译成中文提示
# ---------------------------------------------------------------------------


@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


# ---------------------------------------------------------------------------
# 路由：管理端鉴权路由先挂，再挂统一要求登录的管理端路由
# ---------------------------------------------------------------------------

app.include_router(admin_auth.router)
app.include_router(menu.router)
app.include_router(orders.router)

for admin_router in (admin_orders.router, admin_dishes.router, admin_settings.router):
    app.include_router(
        admin_router,
        prefix="/api/admin",
        dependencies=[Depends(get_current_admin)],
    )


@app.get("/api/health", tags=["meta"], summary="健康检查 / 部署自检")
def health() -> dict[str, object]:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    finally:
        db.close()

    return {
        "ok": db_ok,
        "app": "爱心小食堂",
        "version": "1.0.0",
        "server_time": iso(now_naive()),
        "database": "sqlite",
        "upload_dir": str(settings.upload_path),
        "cjk_font": has_cjk_font(),
    }


# ---------------------------------------------------------------------------
# 静态资源
# ---------------------------------------------------------------------------

#: 上传的菜品图片（StaticFiles 在 import 期就要求目录存在，所以这里先建一次）
upload_root()
app.mount(
    settings.upload_url_prefix,
    StaticFiles(directory=str(settings.upload_path)),
    name="uploads",
)

#: 如果前端已经 build 过，顺手把 SPA 也发了（非必须，生产走 Nginx 也行）
if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    index_file = FRONTEND_DIST / "index.html"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # response_model=None：返回类型是 FileResponse | JSONResponse 的联合，
    # FastAPI 不能据此推导 Pydantic 模型，必须显式关掉。
    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(full_path: str) -> FileResponse | JSONResponse:
        """单页应用兜底。

        关键点：**不能把 /api 和 /uploads 下的路径也兜成 index.html**。
        否则前端打了一个写错的接口地址，收到的是一整页 HTML，
        axios 解析失败会报"网络不太顺畅"，把真正的 404 藏起来，排查很痛苦。
        这里对这两类前缀直接返回 JSON 404。
        """
        #: 这些前缀下的路径属于"接口/静态资源"，绝不兜成 SPA
        reserved_prefixes = ("api/", "uploads/")
        if full_path in ("api", "uploads") or full_path.startswith(reserved_prefixes):
            return JSONResponse(status_code=404, content={"detail": "接口不存在"})

        candidate = (FRONTEND_DIST / full_path).resolve()
        # 防目录穿越：只允许访问 dist 目录内的文件
        try:
            candidate.relative_to(FRONTEND_DIST.resolve())
        except ValueError:
            return FileResponse(index_file)

        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)
