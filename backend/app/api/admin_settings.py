"""管理端店铺设置。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from ..deps import DbSession, get_shop_settings
from ..models import Dish
from ..schemas import SettingsUpdate
from ..serializers import dish_to_dict, dump_id_list, settings_to_dict
from ..services.orders import get_active_order

router = APIRouter(prefix="/settings", tags=["admin-settings"])


@router.get("/recommend-candidates", summary="可设为今日推荐的菜品（已上架）")
def recommend_candidates(db: DbSession) -> dict[str, Any]:
    rows = db.scalars(
        select(Dish)
        .where(Dish.is_available.is_(True))
        .order_by(Dish.category, Dish.sort_order, Dish.id)
    ).all()
    return {"dishes": [dish_to_dict(d) for d in rows]}


@router.get("/summary", summary="后台首页摘要卡片数据")
def summary(db: DbSession) -> dict[str, Any]:
    shop = get_shop_settings(db)
    active = get_active_order(db)
    return {
        "settings": settings_to_dict(shop),
        "active_order_no": active.order_no if active else None,
        "active_order_status": active.status if active else None,
    }


@router.get("", summary="读取店铺设置")
def read_settings(db: DbSession) -> dict[str, Any]:
    shop = get_shop_settings(db)
    return {"settings": settings_to_dict(shop)}


@router.patch("", summary="修改店铺设置")
def update_settings(payload: SettingsUpdate, db: DbSession) -> dict[str, Any]:
    shop = get_shop_settings(db)
    data = payload.model_dump(exclude_unset=True)

    if "today_recommend_ids" in data and data["today_recommend_ids"] is not None:
        ids = data.pop("today_recommend_ids")
        # 只保留真实存在且已上架的菜
        if ids:
            valid = set(
                db.scalars(
                    select(Dish.id).where(Dish.id.in_(ids), Dish.is_available.is_(True))
                ).all()
            )
            ids = [i for i in ids if i in valid]
        shop.today_recommend_ids = dump_id_list(ids)
    data.pop("today_recommend_ids", None)

    for field, value in data.items():
        if value is None:
            continue
        if field == "shop_name" and not value:
            value = "爱心小食堂"
        setattr(shop, field, value)

    db.commit()
    db.refresh(shop)
    return {"settings": settings_to_dict(shop), "message": "已保存，顾客端刷新即可看到"}
