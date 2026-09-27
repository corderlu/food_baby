"""订单业务逻辑。

这里集中处理所有"规则"，路由层只负责鉴权与参数绑定的搬运，
好处是规则可以被脚本、后台任务和测试直接复用。
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    ACTIVE_STATUSES,
    AUTO_CANCELLABLE_STATUSES,
    EDITABLE_STATUSES,
    NEXT_STATUS,
    STATUS_ACCEPTED,
    STATUS_CANCELLED,
    STATUS_COOKING,
    STATUS_NAMES,
    STATUS_SERVED,
    Dish,
    Order,
    OrderItem,
    ShopSettings,
    status_name,
)
from ..schemas import OrderCreate, OrderItemIn, OrderModify
from ..utils.timeutil import now_naive


class BusinessError(Exception):
    """业务规则不满足。路由层捕获后按 `status_code` 返回中文提示。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


AUTO_CANCEL_REASON = "超过 {minutes} 分钟未开始制作，系统已自动取消（主厨可能睡着了～）"


# ---------------------------------------------------------------------------
# 订单号
# ---------------------------------------------------------------------------


def next_order_no(db: Session) -> tuple[str, int]:
    """生成 LOVE-YYYYMMDD-XXX，日序号从 1 递增。"""
    today = now_naive()
    prefix = f"LOVE-{today:%Y%m%d}-"

    last_no = db.scalar(
        select(Order.order_no)
        .where(Order.order_no.like(f"{prefix}%"))
        .order_by(Order.order_no.desc())
        .limit(1)
    )
    seq = 1
    if last_no:
        tail = last_no.rsplit("-", 1)[-1]
        if tail.isdigit():
            seq = int(tail) + 1

    # 理论上不会撞（两人使用），但仍做一次兜底
    for _ in range(1000):
        candidate = f"{prefix}{seq:03d}"
        exists = db.scalar(select(Order.id).where(Order.order_no == candidate).limit(1))
        if not exists:
            return candidate, seq
        seq += 1
    raise BusinessError("当日订单号已用尽，请稍后再试", 500)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def get_active_order(db: Session) -> Order | None:
    """当前未完成的订单（同时只允许存在一个）。"""
    return db.scalar(
        select(Order)
        .where(Order.status.in_(ACTIVE_STATUSES))
        .order_by(Order.id.desc())
        .limit(1)
    )


def get_order_by_no(db: Session, order_no: str) -> Order | None:
    return db.scalar(select(Order).where(Order.order_no == order_no).limit(1))


def get_order_or_404(db: Session, order_no: str) -> Order:
    order = get_order_by_no(db, order_no)
    if order is None:
        raise BusinessError("找不到这个订单号，是不是拼错了？", 404)
    return order


def recalc_total(order: Order) -> int:
    total = sum(int(i.quantity) for i in order.items)
    order.total_items = total
    return total


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


def _load_dishes(db: Session, dish_ids: set[int]) -> dict[int, Dish]:
    if not dish_ids:
        return {}
    rows = db.scalars(select(Dish).where(Dish.id.in_(dish_ids))).all()
    return {d.id: d for d in rows}


def _merge_items(items: list[OrderItemIn]) -> list[OrderItemIn]:
    """同一道菜出现多次时合并数量，并保留第一条的备注。"""
    merged: dict[int, OrderItemIn] = {}
    for it in items:
        if it.dish_id in merged:
            merged[it.dish_id].quantity += it.quantity
        else:
            merged[it.dish_id] = OrderItemIn(
                dish_id=it.dish_id, quantity=it.quantity, item_note=it.item_note
            )
    return list(merged.values())


def create_order(db: Session, payload: OrderCreate, shop: ShopSettings) -> Order:
    if not shop.business_open:
        raise BusinessError(shop.closed_tip or "主厨休息中，暂时不能下单", 409)

    existing = get_active_order(db)
    if existing is not None:
        raise BusinessError(
            f"还有一单没做完呢（{existing.order_no} · {status_name(existing.status)}），"
            "做完这单再接新的啦～",
            409,
        )

    items = _merge_items(payload.items)
    if not items:
        raise BusinessError("购物车是空的，先选几道菜吧")

    dishes = _load_dishes(db, {i.dish_id for i in items})
    missing = [i.dish_id for i in items if i.dish_id not in dishes or not dishes[i.dish_id].is_available]
    if missing:
        raise BusinessError("有菜品已经下架了，请返回菜单重新选择", 409)

    order_no, seq = next_order_no(db)
    order = Order(
        order_no=order_no,
        day_seq=seq,
        status="pending",
        customer_note=payload.customer_note,
        dish_request=payload.dish_request,
        expected_time=payload.expected_time,
        is_new=True,
        revision=0,
    )
    for it in items:
        dish = dishes[it.dish_id]
        order.items.append(
            OrderItem(
                dish_id=dish.id,
                dish_name=dish.name,
                dish_category=dish.category,
                dish_image_url=dish.image_url,
                quantity=it.quantity,
                item_note=it.item_note,
            )
        )
    recalc_total(order)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


# ---------------------------------------------------------------------------
# 顾客改单
# ---------------------------------------------------------------------------


def _apply_remove(db: Session, order: Order, dish_id: int, quantity: int) -> None:
    for item in list(order.items):
        if item.dish_id != dish_id:
            continue
        if quantity >= item.quantity:
            order.items.remove(item)
        else:
            item.quantity -= quantity
        return
    raise BusinessError("订单里没有这道菜，没法减少")


def modify_order(db: Session, order: Order, payload: OrderModify, shop: ShopSettings) -> Order:
    if order.status not in EDITABLE_STATUSES:
        raise BusinessError(
            f"订单已经{status_name(order.status)}了，改不了啦～，想吃别的可以直接跟我说",
            409,
        )

    changed = False

    if payload.remove:
        for it in _merge_items(payload.remove):
            _apply_remove(db, order, it.dish_id, it.quantity)
            changed = True

    if payload.add:
        add_items = _merge_items(payload.add)
        dishes = _load_dishes(db, {i.dish_id for i in add_items})
        for it in add_items:
            dish = dishes.get(it.dish_id)
            if dish is None or not dish.is_available:
                raise BusinessError(f"菜品已经下架了，加不进去（id={it.dish_id}）", 409)

        # 已存在的明细直接累加数量，避免同一道菜出现两行
        by_dish = {i.dish_id: i for i in order.items if i.dish_id is not None}
        for it in add_items:
            if it.dish_id in by_dish:
                by_dish[it.dish_id].quantity += it.quantity
                if it.item_note and not by_dish[it.dish_id].item_note:
                    by_dish[it.dish_id].item_note = it.item_note
            else:
                dish = dishes[it.dish_id]
                order.items.append(
                    OrderItem(
                        dish_id=dish.id,
                        dish_name=dish.name,
                        dish_category=dish.category,
                        dish_image_url=dish.image_url,
                        quantity=it.quantity,
                        item_note=it.item_note,
                    )
                )
            changed = True

    if payload.customer_note is not None:
        order.customer_note = payload.customer_note
        changed = True
    if payload.dish_request is not None:
        order.dish_request = payload.dish_request
        changed = True
    if payload.expected_time is not None:
        order.expected_time = payload.expected_time
        changed = True

    if not changed:
        raise BusinessError("没有要修改的内容")

    if not order.items:
        raise BusinessError("菜全删完啦，如果想取消订单请点「取消订单」", 409)

    recalc_total(order)
    order.revision += 1
    # 改完单等于又"动"了一下，重置超时计时基准。
    # 注意：不要清 is_new —— 那会让"她改了一单你还没看过"的提示音漏掉。
    # 后台用 revision > 0 来判断是"改单提醒"还是"新单提醒"。
    order.updated_at = now_naive()
    db.commit()
    db.refresh(order)
    return order


def cancel_by_customer(db: Session, order: Order, reason: str = "") -> Order:
    if order.status not in EDITABLE_STATUSES:
        raise BusinessError(
            f"订单已经{status_name(order.status)}了，这时候取消就浪费啦", 409
        )
    _do_cancel(order, reason or "顾客主动取消")
    db.commit()
    db.refresh(order)
    return order


# ---------------------------------------------------------------------------
# 状态流转（管理端）
# ---------------------------------------------------------------------------


def _do_cancel(order: Order, reason: str) -> None:
    order.status = STATUS_CANCELLED
    order.cancel_reason = reason
    order.cancelled_at = now_naive()
    order.is_new = False


def change_status(db: Session, order: Order, target: str, cancel_reason: str = "") -> Order:
    current = order.status

    if target == current:
        raise BusinessError(f"订单已经是「{STATUS_NAMES.get(current, current)}」了")

    if target == STATUS_CANCELLED:
        if current not in EDITABLE_STATUSES:
            raise BusinessError(
                f"订单已经{status_name(current)}，不能再取消了", 409
            )
        if not cancel_reason.strip():
            cancel_reason = "主厨取消了这一单"
        _do_cancel(order, cancel_reason.strip())
        db.commit()
        db.refresh(order)
        return order

    expected = NEXT_STATUS.get(current)
    if expected is None:
        raise BusinessError(
            f"订单已是「{status_name(current)}」，没有下一步了", 409
        )
    if target != expected:
        raise BusinessError(
            f"状态不能从「{status_name(current)}」直接跳到「{status_name(target)}」，"
            f"下一步应该是「{status_name(expected)}」",
            409,
        )

    order.status = target
    # 注意：这里不清 is_new。后台靠"自己推进了状态"来停止提示音，
    # 而 is_new 保留到管理员显式标记已读，避免她改了单而你没听到提示。

    if target == STATUS_ACCEPTED:
        order.accepted_at = now_naive()
    elif target == STATUS_COOKING:
        # 进锅了：永不自动取消
        order.auto_cancel_exempt = True
    elif target == STATUS_SERVED:
        order.completed_at = now_naive()
        order.auto_cancel_exempt = True

    db.commit()
    db.refresh(order)
    return order


def mark_seen(db: Session, order_ids: list[int] | None = None) -> int:
    """把新订单标记为已读（后台点"我知道了"或播放过提示音后调用）。"""
    stmt = select(Order).where(Order.is_new.is_(True))
    if order_ids:
        stmt = stmt.where(Order.id.in_(order_ids))
    rows = db.scalars(stmt).all()
    for o in rows:
        o.is_new = False
    if rows:
        db.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# 超时自动取消
# ---------------------------------------------------------------------------

logger = logging.getLogger("food_baby.orders")


def auto_cancel_stale(db: Session, minutes: int | None = None) -> list[Order]:
    """把"还没开始做"且放置超时的订单自动取消，释放下单名额。

    只作用于 pending / accepted / preparing；进入 cooking 的订单永不自动取消。
    """
    limit = settings.order_auto_cancel_minutes if minutes is None else minutes
    if limit <= 0:
        return []

    # 用 created_at 作为基准，updated_at 会随改单/改状态刷新
    deadline = now_naive() - timedelta(minutes=limit)
    rows = db.scalars(
        select(Order).where(
            Order.status.in_(AUTO_CANCELLABLE_STATUSES),
            Order.auto_cancel_exempt.is_(False),
            Order.created_at <= deadline,
        )
    ).all()

    if not rows:
        return []

    reason = AUTO_CANCEL_REASON.format(minutes=limit)
    for o in rows:
        _do_cancel(o, reason)
        logger.info("订单 %s 超过 %d 分钟未开始制作，已自动取消", o.order_no, limit)
    db.commit()
    for o in rows:
        db.refresh(o)
    return rows


def elapsed_minutes(order: Order) -> float | None:
    """订单从下单到现在过了多少分钟（后台用来提示「这单挂了多久」）。"""
    if order.created_at is None:
        return None
    return round((now_naive() - order.created_at).total_seconds() / 60.0, 1)
