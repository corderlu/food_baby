"""应用配置：全部通过环境变量 / .env 注入，避免硬编码。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 服务 ---
    host: str = "0.0.0.0"
    port: int = 8801

    # --- 鉴权 ---
    secret_key: str = "please-change-this-to-a-random-secret-string"
    token_expire_hours: int = 720
    jwt_algorithm: str = "HS256"

    # --- 数据库 ---
    database_url: str = "sqlite:///./food_baby.db"

    # --- 初始管理员 ---
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # --- CORS ---
    cors_origins: str = "http://localhost:5273,http://127.0.0.1:5273"

    # --- 上传 ---
    upload_dir: str = "app/static/uploads"
    upload_url_prefix: str = "/uploads"
    image_max_side: int = 1200
    image_thumb_side: int = 400
    image_jpeg_quality: int = 86

    # --- 订单超时 ---
    order_auto_cancel_minutes: int = 120
    auto_cancel_interval_seconds: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        if not p.is_absolute():
            p = BACKEND_DIR / p
        return p

    @property
    def sqlite_path(self) -> Path | None:
        """如果是 sqlite，返回数据库文件的绝对路径（用于启动日志展示）。"""
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        raw = self.database_url[len(prefix) :]
        p = Path(raw)
        if not p.is_absolute():
            p = BACKEND_DIR / p
        return p


settings = Settings()
