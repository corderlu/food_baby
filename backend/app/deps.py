"""FastAPI 依赖：数据库会话、当前管理员、店铺设置。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import Admin, ShopSettings
from .utils.security import decode_access_token

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str = "登录已过期，请重新登录") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_admin(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Admin:
    """从 Authorization: Bearer <token> 解析出管理员。"""
    if not authorization:
        raise _unauthorized("请先登录")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _unauthorized("Authorization 头格式应为 Bearer <token>")

    payload = decode_access_token(parts[1])
    if not payload:
        raise _unauthorized()

    sub = payload.get("sub")
    if sub is None:
        raise _unauthorized()

    try:
        admin_id = int(sub)
    except (TypeError, ValueError):
        raise _unauthorized() from None

    admin = db.get(Admin, admin_id)
    if admin is None:
        raise _unauthorized("账号不存在")
    return admin


CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]


def get_shop_settings(db: DbSession) -> ShopSettings:
    """取店铺设置，缺失时兜底创建，保证接口永远不会因为少一行数据而 500。"""
    s = db.get(ShopSettings, 1)
    if s is None:
        s = ShopSettings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


ShopSettingsDep = Annotated[ShopSettings, Depends(get_shop_settings)]
