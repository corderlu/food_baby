"""SQLite + SQLAlchemy 会话管理。

设计取舍：两人使用的单机服务，启动时自动建表即可，不引入 Alembic 迁移工具。
修改字段时最省事的做法是删掉 food_baby.db 重启（历史订单会一起丢掉），
所以升级前请先备份该文件。
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def _resolve_url() -> str:
    """把相对 sqlite 路径固定到 backend/ 目录，避免因启动目录不同而生成多份数据库。"""
    prefix = "sqlite:///"
    url = settings.database_url
    if url.startswith(prefix):
        p = settings.sqlite_path
        if p is not None:
            return f"{prefix}{p.as_posix()}"
    return url


SQLALCHEMY_DATABASE_URL = _resolve_url()

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
    """开启外键约束 + WAL 模式（读写并发更友好）。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """脚本 / 后台任务里用的上下文管理器。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
