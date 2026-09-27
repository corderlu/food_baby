"""顾客端订单接口：提交、查看、改单、取消。无需登录。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from ..deps import DbSession, ShopSettingsDep
from ..models import STATUS_NAMES, Order
from ..schemas import OrderCreate, OrderModify, OrderQuery
from ..serializers import order_to_dict
from ..services import orders as order_service
from ..services.orders import elapsed_minutes, get_order_or_404

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/statuses", summary="订单状态字典（前端画进度条用）")
def read_statuses() -> dict[str, Any]:
    flow = ["pending", "accepted", "preparing", "cooking", "served"]
    return {
        "flow": flow,
        "names": STATUS_NAMES,
        "cancelled": "cancelled",
    }


@router.get("/active", summary="当前未完成的订单（同时只允许一单）")
def read_active_order(db: DbSession) -> dict[str, Any]:
    order = order_service.get_active_order(db)
    return {"order": order_to_dict(order) if order else None}


@router.post("", status_code=201, summary="提交订单")
def create_order(payload: OrderCreate, db: DbSession, shop: ShopSettingsDep) -> dict[str, Any]:
    order = order_service.create_order(db, payload, shop)
    return {"order": order_to_dict(order)}


@router.post("/query", summary="按订单号批量查询（我的订单页用）")
def query_orders(payload: OrderQuery, db: DbSession) -> dict[str, Any]:
    if not payload.order_nos:
        return {"orders": []}
    rows = db.scalars(
        select(Order).where(Order.order_no.in_(payload.order_nos)).order_by(Order.id.desc())
    ).all()
    return {"orders": [order_to_dict(o) for o in rows]}


@router.get("/{order_no}", summary="订单详情")
def read_order(order_no: str, db: DbSession) -> dict[str, Any]:
    order = get_order_or_404(db, order_no)
    data = order_to_dict(order)
    data["elapsed_minutes"] = elapsed_minutes(order)
    return {"order": data}


@router.patch("/{order_no}", summary="改单（加菜/减菜/改备注），烹饪中之后不可改")
def modify_order(
    order_no: str,
    payload: OrderModify,
    db: DbSession,
    shop: ShopSettingsDep,
) -> dict[str, Any]:
    order = get_order_or_404(db, order_no)
    updated = order_service.modify_order(db, order, payload, shop)
    return {"order": order_to_dict(updated), "message": "改好啦～主厨已经看到最新菜单"}


@router.post("/{order_no}/cancel", summary="顾客主动取消订单")
def cancel_order(order_no: str, db: DbSession) -> dict[str, Any]:
    order = get_order_or_404(db, order_no)
    updated = order_service.cancel_by_customer(db, order)
    return {"order": order_to_dict(updated), "message": "已取消，下次想吃什么随时点～"}
