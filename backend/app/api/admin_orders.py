"""管理端订单看板接口（挂在 /api/admin 下，统一要求 Bearer Token）。

路由顺序很重要：`/new`、`/seen`、`/status-filter` 这些固定路径必须写在
`/{order_no}` 之前，否则会被当成订单号吃掉（"new" 会被解析成订单号）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from sqlalchemy import func, select

from ..deps import DbSession
from ..models import ACTIVE_STATUSES, STATUS_NAMES, STATUS_PENDING, Order
from ..schemas import StatusUpdate
from ..serializers import order_to_dict
from ..services import orders as order_service
from ..services.orders import get_order_or_404

router = APIRouter(prefix="/orders", tags=["admin-orders"])


def _admin_order(order: Order) -> dict[str, Any]:
    data = order_to_dict(order, include_admin_fields=True)
    data["elapsed_minutes"] = order_service.elapsed_minutes(order)
    return data


# ---------------------------------------------------------------------------
# 固定路径（必须在前）
# ---------------------------------------------------------------------------


@router.get("/status-filter", summary="筛选下拉的选项")
def read_filters() -> dict[str, Any]:
    return {
        "options": [{"value": "all", "label": "全部"}]
        + [{"value": k, "label": v} for k, v in STATUS_NAMES.items()],
        "active_statuses": list(ACTIVE_STATUSES),
    }


@router.get("/new", summary="增量拉取新订单（后台 5 秒轮询用）")
def list_new_orders(
    db: DbSession,
    since_id: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    rows = db.scalars(
        select(Order).where(Order.id > since_id).order_by(Order.id.asc()).limit(limit)
    ).all()
    max_id = db.scalar(select(func.max(Order.id))) or 0
    return {
        "orders": [_admin_order(o) for o in rows],
        "max_id": max_id,
        "has_new": any(o.is_new for o in rows),
    }


@router.post("/seen", summary="把这些新订单标记为已读")
def mark_seen(db: DbSession, order_ids: list[int] | None = Body(default=None)) -> dict[str, Any]:
    count = order_service.mark_seen(db, order_ids)
    return {"updated": count}


@router.post("/auto-cancel-stale", summary="手动触发一次超时自动取消巡检")
def run_auto_cancel(db: DbSession) -> dict[str, Any]:
    rows = order_service.auto_cancel_stale(db)
    return {
        "cancelled": [o.order_no for o in rows],
        "count": len(rows),
        "message": f"已自动取消 {len(rows)} 个超时订单" if rows else "没有超时订单",
    }


@router.get("", summary="订单列表（默认按创建时间倒序）")
def list_orders(
    db: DbSession,
    status: str = Query("all", description="all 或具体状态值"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    stmt = select(Order).order_by(Order.id.desc())
    count_stmt = select(func.count()).select_from(Order)

    if status and status != "all" and status in STATUS_NAMES:
        stmt = stmt.where(Order.status == status)
        count_stmt = count_stmt.where(Order.status == status)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()

    pending_ids = [
        o.id
        for o in db.scalars(
            select(Order)
            .where(Order.status == STATUS_PENDING)
            .order_by(Order.id.desc())
            .limit(50)
        ).all()
    ]

    active = order_service.get_active_order(db)
    return {
        "orders": [_admin_order(o) for o in rows],
        "total": total,
        "pending_ids": pending_ids,
        "active_order_no": active.order_no if active else None,
    }


# ---------------------------------------------------------------------------
# 需要订单号的路由
# ---------------------------------------------------------------------------


@router.get("/{order_no}", summary="订单详情（管理端）")
def read_order(order_no: str, db: DbSession) -> dict[str, Any]:
    order = get_order_or_404(db, order_no)
    return {"order": _admin_order(order)}


@router.post("/{order_no}/status", summary="推进 / 取消订单状态")
def update_status(order_no: str, payload: StatusUpdate, db: DbSession) -> dict[str, Any]:
    order = get_order_or_404(db, order_no)
    updated = order_service.change_status(db, order, payload.status, payload.cancel_reason)
    label = STATUS_NAMES.get(updated.status, updated.status)
    return {"order": _admin_order(updated), "message": f"已更新为「{label}」"}
