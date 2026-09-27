"""ORM → JSON 字典。所有响应都从这里出，字段命名统一 snake_case。"""

from __future__ import annotations

import json
from typing import Any

from .models import (
    ACTIVE_STATUSES,
    EDITABLE_STATUSES,
    Dish,
    Order,
    OrderItem,
    ShopSettings,
    status_name,
)
from .utils.timeutil import iso


def parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        # 容错：也接受 "甜,快手" 这种半路写法
        return [p.strip() for p in str(raw).replace("，", ",").split(",") if p.strip()]
    if isinstance(data, list):
        return [str(t) for t in data]
    return []


def dump_tags(tags: list[str]) -> str:
    return json.dumps(list(tags or []), ensure_ascii=False)


def dish_to_dict(dish: Dish, *, include_unavailable: bool = True) -> dict[str, Any]:
    return {
        "id": dish.id,
        "name": dish.name,
        "description": dish.description,
        "image_url": dish.image_url,
        "thumb_url": dish.image_url,
        "category": dish.category,
        "tags": parse_tags(dish.tags),
        "spicy_level": dish.spicy_level,
        "spicy_name": spicy_name(dish.spicy_level),
        "estimated_minutes": dish.estimated_minutes,
        "is_available": bool(dish.is_available),
        "sort_order": dish.sort_order,
        "created_at": iso(dish.created_at),
        "updated_at": iso(dish.updated_at),
    }


SPICY_NAMES = ("不辣", "微辣", "中辣", "特辣")


def spicy_name(level: int) -> str:
    if 0 <= level < len(SPICY_NAMES):
        return SPICY_NAMES[level]
    return "不辣"


def order_item_to_dict(item: OrderItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "dish_id": item.dish_id,
        "dish_name": item.dish_name,
        "dish_category": item.dish_category,
        "dish_image_url": item.dish_image_url,
        "quantity": item.quantity,
        "item_note": item.item_note,
    }


def order_to_dict(
    order: Order,
    *,
    include_items: bool = True,
    include_admin_fields: bool = False,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "status_name": status_name(order.status),
        "total_items": order.total_items,
        "customer_note": order.customer_note,
        "dish_request": order.dish_request,
        "expected_time": order.expected_time,
        "created_at": iso(order.created_at),
        "updated_at": iso(order.updated_at),
        "accepted_at": iso(order.accepted_at),
        "completed_at": iso(order.completed_at),
        "cancelled_at": iso(order.cancelled_at),
        "cancel_reason": order.cancel_reason,
        "editable": order.status in EDITABLE_STATUSES,
        "active": order.status in ACTIVE_STATUSES,
        "next_status": order.next_status,
        "next_status_name": status_name(order.next_status) if order.next_status else None,
    }
    if include_items:
        data["items"] = [order_item_to_dict(i) for i in order.items]
    if include_admin_fields:
        data["is_new"] = bool(order.is_new)
        data["revision"] = order.revision

    return data


def settings_to_dict(s: ShopSettings) -> dict[str, Any]:
    ids: list[int] = []
    try:
        raw = json.loads(s.today_recommend_ids or "[]")
        if isinstance(raw, list):
            ids = [int(x) for x in raw]
    except (ValueError, TypeError):
        ids = []
    return {
        "shop_name": s.shop_name,
        "announcement": s.announcement,
        "welcome_text": s.welcome_text,
        "business_open": bool(s.business_open),
        "closed_tip": s.closed_tip,
        "today_recommend_ids": ids,
        "updated_at": iso(s.updated_at),
    }


def dump_id_list(ids: list[int]) -> str:
    """把今日推荐 ID 列表序列化成 JSON 字符串（去重 + 排序，读起来稳定）。"""
    return json.dumps(sorted({int(i) for i in ids}), ensure_ascii=False)
