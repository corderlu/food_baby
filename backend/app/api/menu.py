"""顾客端公开接口：店铺信息 + 菜单。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from ..deps import DbSession, ShopSettingsDep
from ..models import Dish
from ..serializers import dish_to_dict, settings_to_dict

router = APIRouter(prefix="/api", tags=["menu"])

#: 前端期望的分类展示顺序；数据库里出现的额外分类会追加在后面
PREFERRED_CATEGORY_ORDER: tuple[str, ...] = ("主食", "热菜", "凉菜", "汤", "甜品", "饮料")


def _sorted_categories(categories: list[str]) -> list[str]:
    known = [c for c in PREFERRED_CATEGORY_ORDER if c in categories]
    extra = sorted(c for c in categories if c not in PREFERRED_CATEGORY_ORDER)
    return known + extra


def _menu_payload(db: DbSession) -> dict[str, Any]:
    dishes = db.scalars(
        select(Dish)
        .where(Dish.is_available.is_(True))
        .order_by(Dish.category, Dish.sort_order, Dish.id)
    ).all()

    items = [dish_to_dict(d) for d in dishes]
    categories: list[str] = []
    for d in items:
        if d["category"] not in categories:
            categories.append(d["category"])

    grouped = [
        {
            "category": c,
            "dishes": [d for d in items if d["category"] == c],
        }
        for c in _sorted_categories(categories)
    ]

    return {
        "categories": _sorted_categories(categories),
        "grouped": grouped,
        "dishes": items,
        "total": len(items),
    }


@router.get("/shop", summary="店铺信息（名称/公告/营业状态/今日推荐）")
def read_shop(db: DbSession, shop: ShopSettingsDep) -> dict[str, Any]:
    data = settings_to_dict(shop)
    recommend_ids: list[int] = data["today_recommend_ids"]

    recommends: list[dict[str, Any]] = []
    if recommend_ids:
        rows = db.scalars(
            select(Dish).where(Dish.id.in_(recommend_ids), Dish.is_available.is_(True))
        ).all()
        by_id = {d.id: d for d in rows}
        recommends = [dish_to_dict(by_id[i]) for i in recommend_ids if i in by_id]

    return {"shop": data, "recommends": recommends}


@router.get("/menu", summary="菜单（分类 + 菜品，只含已上架）")
def read_menu(db: DbSession) -> dict[str, Any]:
    return _menu_payload(db)
