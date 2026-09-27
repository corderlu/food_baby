"""管理端菜品管理 + 图片上传压缩。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select

from ..deps import DbSession
from ..models import Dish, OrderItem
from ..schemas import DishCreate, DishToggle, DishUpdate
from ..serializers import dish_to_dict, dump_tags
from ..services.images import (
    ImageProcessError,
    delete_upload,
    make_placeholder,
    process_upload,
)

logger = logging.getLogger("food_baby.dishes")

router = APIRouter(prefix="/dishes", tags=["admin-dishes"])


@router.get("/categories", summary="已有分类（用于表单下拉）")
def read_categories(db: DbSession) -> dict[str, Any]:
    rows = db.scalars(select(Dish.category).distinct().order_by(Dish.category)).all()
    preferred = ["主食", "热菜", "凉菜", "汤", "甜品", "饮料"]
    known = [c for c in preferred if c in rows]
    extra = [c for c in rows if c not in preferred]
    return {"categories": known + extra}


@router.get("", summary="菜品列表（含已下架，后台用）")
def list_dishes(
    db: DbSession,
    category: str | None = Query(None),
    keyword: str | None = Query(None, max_length=40),
    only_available: bool = Query(False),
) -> dict[str, Any]:
    stmt = select(Dish).order_by(Dish.category, Dish.sort_order, Dish.id)
    if category:
        stmt = stmt.where(Dish.category == category)
    if keyword:
        stmt = stmt.where(Dish.name.like(f"%{keyword.strip()}%"))
    if only_available:
        stmt = stmt.where(Dish.is_available.is_(True))

    rows = db.scalars(stmt).all()
    dishes = [dish_to_dict(d) for d in rows]
    categories: list[str] = []
    for d in dishes:
        if d["category"] not in categories:
            categories.append(d["category"])

    return {
        "dishes": dishes,
        "total": len(dishes),
        "categories": categories,
        "available_count": sum(1 for d in dishes if d["is_available"]),
    }


@router.post("", status_code=201, summary="新增菜品")
def create_dish(payload: DishCreate, db: DbSession) -> dict[str, Any]:
    image_url = payload.image_url
    if not image_url:
        # 没给图就顺手生成一张占位图，前台不会出现空白卡片
        try:
            image_url = make_placeholder(payload.name, payload.category)
        except Exception as exc:  # noqa: BLE001
            logger.warning("生成占位图失败：%s", exc)
            image_url = ""

    dish = Dish(
        name=payload.name,
        description=payload.description,
        image_url=image_url,
        category=payload.category or "其他",
        tags=dump_tags(payload.tags),
        spicy_level=payload.spicy_level,
        estimated_minutes=payload.estimated_minutes,
        is_available=payload.is_available,
        sort_order=payload.sort_order,
    )
    db.add(dish)
    db.commit()
    db.refresh(dish)
    return {"dish": dish_to_dict(dish), "message": "菜品已添加"}


# ---------------------------------------------------------------------------
# 图片上传（固定路径，写在 /{dish_id} 前）
# ---------------------------------------------------------------------------


@router.post("/upload-image", summary="上传菜品图片（服务端自动压缩 + 生成缩略图）")
async def upload_image(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    try:
        result = await run_in_threadpool(process_upload, raw, file.filename or "")
    except ImageProcessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("图片处理失败")
        raise HTTPException(status_code=500, detail="图片处理失败，换一张试试") from exc

    return {"image_url": result["image_url"], "thumb_url": result["thumb_url"], **{
        k: v for k, v in result.items() if k in ("width", "height", "bytes")
    }}


@router.post("/placeholder", summary="按菜名生成一张占位图")
def create_placeholder(
    name: str = Form(..., min_length=1, max_length=40),
    subtitle: str = Form("", max_length=20),
) -> dict[str, Any]:
    try:
        url = make_placeholder(name, subtitle)
    except Exception as exc:  # noqa: BLE001
        logger.exception("生成占位图失败")
        raise HTTPException(status_code=500, detail="占位图生成失败") from exc
    return {"image_url": url, "thumb_url": url}


# ---------------------------------------------------------------------------
# 需要 dish_id 的路由
# ---------------------------------------------------------------------------


def _get_dish_or_404(db: DbSession, dish_id: int) -> Dish:
    dish = db.get(Dish, dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="菜品不存在")
    return dish


@router.get("/{dish_id}", summary="菜品详情")
def read_dish(dish_id: int, db: DbSession) -> dict[str, Any]:
    return {"dish": dish_to_dict(_get_dish_or_404(db, dish_id))}


@router.patch("/{dish_id}", summary="编辑菜品")
def update_dish(dish_id: int, payload: DishUpdate, db: DbSession) -> dict[str, Any]:
    dish = _get_dish_or_404(db, dish_id)
    data = payload.model_dump(exclude_unset=True)

    old_image = dish.image_url
    if "tags" in data and data["tags"] is not None:
        dish.tags = dump_tags(data.pop("tags"))
    data.pop("tags", None)

    for field, value in data.items():
        if value is None:
            continue
        if field == "category" and not value:
            value = "其他"
        setattr(dish, field, value)

    # 换成新图时，删掉自己上传的旧图（外链 URL 不会被删）
    if "image_url" in data and old_image and old_image != dish.image_url:
        try:
            delete_upload(old_image)
        except Exception as exc:  # noqa: BLE001
            logger.warning("删除旧图失败（%s）：%s", old_image, exc)

    db.commit()
    db.refresh(dish)
    return {"dish": dish_to_dict(dish), "message": "已保存"}


@router.post("/{dish_id}/toggle", summary="上架 / 下架快捷切换")
def toggle_dish(dish_id: int, payload: DishToggle, db: DbSession) -> dict[str, Any]:
    dish = _get_dish_or_404(db, dish_id)
    dish.is_available = payload.is_available
    db.commit()
    db.refresh(dish)
    return {
        "dish": dish_to_dict(dish),
        "message": "已上架" if dish.is_available else "已下架",
    }


@router.delete("/{dish_id}", summary="删除菜品（历史订单不受影响）")
def delete_dish(
    dish_id: int,
    db: DbSession,
    force: bool = Query(False, description="该菜出现在历史订单里时，需要 force=true 才允许删除"),
) -> dict[str, Any]:
    dish = _get_dish_or_404(db, dish_id)

    used = db.scalar(
        select(func.count()).select_from(OrderItem).where(OrderItem.dish_id == dish_id)
    ) or 0
    if used and not force:
        raise HTTPException(
            status_code=409,
            detail=f"这道菜在 {used} 条历史订单里出现过。删掉不影响历史订单显示，但确认要删吗？",
        )

    image = dish.image_url
    name = dish.name
    db.delete(dish)
    db.commit()

    try:
        delete_upload(image)
    except Exception as exc:  # noqa: BLE001
        logger.warning("删除菜品图片失败（%s）：%s", image, exc)

    return {"message": f"「{name}」已删除", "history_kept": used}
