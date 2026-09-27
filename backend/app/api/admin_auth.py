"""管理端登录 / 当前管理员 / 修改密码。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..deps import CurrentAdmin, DbSession, get_shop_settings
from ..models import STATUS_COOKING, STATUS_PENDING, Admin, Dish, Order
from ..schemas import ChangePasswordRequest, LoginRequest
from ..serializers import settings_to_dict
from ..services.orders import get_active_order
from ..utils.security import create_access_token, hash_password, verify_password
from ..utils.timeutil import iso, now_naive

router = APIRouter(prefix="/api/admin", tags=["admin-auth"])

#: 初始密码，仅用于判断"是否还在用默认密码"
_DEFAULT_PASSWORD = "admin123"


def _admin_dict(admin: Admin) -> dict[str, Any]:
    return {
        "id": admin.id,
        "username": admin.username,
        "created_at": iso(admin.created_at),
        "last_login_at": iso(admin.last_login_at),
        "using_default_password": verify_password(_DEFAULT_PASSWORD, admin.password_hash),
    }


@router.post("/login", summary="管理员登录，返回 JWT")
def login(payload: LoginRequest, db: DbSession) -> dict[str, Any]:
    admin = db.scalar(select(Admin).where(Admin.username == payload.username).limit(1))
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码不对哦",
        )

    token, expires = create_access_token(str(admin.id), {"username": admin.username})
    admin.last_login_at = now_naive()
    db.commit()
    db.refresh(admin)

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": iso(expires),
        "admin": _admin_dict(admin),
    }


@router.get("/me", summary="当前登录的管理员")
def read_me(admin: CurrentAdmin) -> dict[str, Any]:
    return {"admin": _admin_dict(admin)}


@router.post("/change-password", summary="修改密码")
def change_password(
    payload: ChangePasswordRequest,
    admin: CurrentAdmin,
    db: DbSession,
) -> dict[str, Any]:
    if not verify_password(payload.old_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="原密码不对")

    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码和原密码一样呀")

    admin.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(admin)

    token, expires = create_access_token(str(admin.id), {"username": admin.username})
    return {
        "message": "密码已更新，其他设备上的登录会失效",
        "access_token": token,
        "token_type": "bearer",
        "expires_at": iso(expires),
        "admin": _admin_dict(admin),
    }


@router.get("/overview", summary="后台首页概览（登录后落地页用）")
def overview(admin: CurrentAdmin, db: DbSession) -> dict[str, Any]:
    shop = get_shop_settings(db)
    active = get_active_order(db)
    pending_count = db.scalar(
        select(func.count()).select_from(Order).where(Order.status == STATUS_PENDING)
    )
    cooking_count = db.scalar(
        select(func.count()).select_from(Order).where(Order.status == STATUS_COOKING)
    )
    dish_count = db.scalar(
        select(func.count()).select_from(Dish).where(Dish.is_available.is_(True))
    )
    total_orders = db.scalar(select(func.count()).select_from(Order))

    return {
        "admin": _admin_dict(admin),
        "shop": settings_to_dict(shop),
        "active_order": None,
        "pending_count": pending_count or 0,
        "cooking_count": cooking_count or 0,
        "available_dish_count": dish_count or 0,
        "total_orders": total_orders or 0,
        "active_order_no": active.order_no if active else None,
    }
