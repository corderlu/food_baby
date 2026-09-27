"""初始化种子数据：管理员、店铺设置、示例菜单。

只在对应表为空时写入，所以重复启动不会覆盖你自己改过的内容。
示例菜品的图片用 Pillow 现场生成粉色渐变 + 爱心 + 菜名的占位图，
以后你在后台传真实照片覆盖即可。
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Admin, Dish, ShopSettings
from ..utils.security import hash_password
from .images import make_placeholder

logger = logging.getLogger("food_baby.seed")

#: (名称, 分类, 描述, 标签, 辣度, 预计分钟, 排序)
SAMPLE_DISHES: tuple[tuple[str, str, str, list[str], int, int, int], ...] = (
    # --- 主食 ---
    ("蛋炒饭", "主食", "米粒颗颗分明，鸡蛋香得很", ["快手", "家常"], 0, 10, 10),
    ("番茄鸡蛋面", "主食", "汤浓面滑，酸酸的很开胃", ["暖胃", "家常"], 0, 15, 20),
    ("扬州炒饭", "主食", "虾仁火腿青豆，料比饭多", ["有料"], 0, 15, 30),
    ("手工水饺", "主食", "现包现煮，一口一个", ["管饱"], 0, 25, 40),
    # --- 热菜 ---
    ("番茄炒蛋", "热菜", "国民下饭菜，汤汁记得拌饭", ["下饭", "经典"], 0, 10, 50),
    ("可乐鸡翅", "热菜", "甜咸入味，骨头都想啃干净", ["甜", "拿手菜"], 0, 25, 60),
    ("红烧排骨", "热菜", "小火慢炖，肉一抿就脱骨", ["硬菜", "费时"], 1, 45, 70),
    ("宫保鸡丁", "热菜", "花生脆、鸡丁嫩，微辣刚好", ["下饭", "微辣"], 1, 20, 80),
    ("麻婆豆腐", "热菜", "麻辣鲜香，拌饭一绝", ["下饭", "辣"], 2, 15, 90),
    ("水煮肉片", "热菜", "红油翻滚，肉片滑嫩", ["重口", "特辣"], 3, 25, 100),
    ("清炒时蔬", "热菜", "当季青菜，少油少盐", ["清淡", "健康"], 0, 8, 110),
    ("蒜蓉粉丝虾", "热菜", "蒜香扑鼻，虾肉弹牙", ["海鲜", "拿手菜"], 0, 20, 120),
    # --- 凉菜 ---
    ("凉拌黄瓜", "凉菜", "拍碎才入味，清爽解腻", ["爽口", "快手"], 1, 5, 130),
    ("口水鸡", "凉菜", "红油浸着嫩鸡肉，越吃越上头", ["麻辣", "开胃"], 2, 20, 140),
    # --- 汤 ---
    ("番茄蛋花汤", "汤", "简单但永远喝不腻", ["清淡", "快手"], 0, 8, 150),
    ("冬瓜排骨汤", "汤", "炖到汤色发白，清甜", ["滋补", "费时"], 0, 60, 160),
    ("紫菜虾皮汤", "汤", "两分钟出锅，鲜得很", ["快手"], 0, 5, 170),
    # --- 甜品 ---
    ("红糖酒酿小圆子", "甜品", "糯叽叽，暖到心里", ["甜", "暖"], 0, 15, 180),
    ("杨枝甘露", "甜品", "芒果 + 西柚 + 椰浆，冰镇更好喝", ["甜", "冰"], 0, 15, 190),
    ("烤红薯", "甜品", "烤箱版，流蜜的那种", ["甜", "冬日"], 0, 50, 200),
    # --- 饮料 ---
    ("柠檬蜂蜜水", "饮料", "现切柠檬，解腻", ["清爽"], 0, 3, 210),
    ("热牛奶", "饮料", "睡前一杯，好睡", ["暖"], 0, 3, 220),
    ("冰镇酸梅汤", "饮料", "自己熬的，不是粉冲的", ["解腻", "冰"], 0, 5, 230),
)

CATEGORY_ORDER: tuple[str, ...] = ("主食", "热菜", "凉菜", "汤", "甜品", "饮料")


def ensure_admin(db: Session) -> bool:
    """没有管理员就建一个，密码取 ADMIN_PASSWORD。返回是否新建。"""
    exists = db.scalar(select(func.count()).select_from(Admin)) or 0
    if exists:
        return False
    db.add(
        Admin(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
        )
    )
    logger.info("已创建初始管理员：%s", settings.admin_username)
    return True


def ensure_settings(db: Session) -> bool:
    existing = db.get(ShopSettings, 1)
    if existing:
        return False
    db.add(ShopSettings(id=1))
    logger.info("已创建默认店铺设置")
    return True


def ensure_dishes(db: Session) -> int:
    """表为空时灌入示例菜品，并为每道菜生成占位图。返回新增数量。"""
    exists = db.scalar(select(func.count()).select_from(Dish)) or 0
    if exists:
        return 0

    created = 0
    for name, category, desc, tags, spicy, minutes, sort_order in SAMPLE_DISHES:
        image_url = ""
        try:
            # out_name 固定，重启不会重复生成文件
            image_url = make_placeholder(
                title=name,
                subtitle=category,
                out_name=f"seed_{category}_{name}.jpg",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("生成占位图失败（%s）：%s", name, exc)

        db.add(
            Dish(
                name=name,
                description=desc,
                image_url=image_url,
                category=category,
                tags=json.dumps(tags, ensure_ascii=False),
                spicy_level=spicy,
                estimated_minutes=minutes,
                is_available=True,
                sort_order=sort_order,
            )
        )
        created += 1

    logger.info("已灌入 %d 道示例菜品", created)
    return created


def seed_all(db: Session) -> dict[str, int | bool]:
    """幂等初始化，应用启动时调用一次。"""
    admin_created = ensure_admin(db)
    settings_created = ensure_settings(db)
    dishes_created = ensure_dishes(db)
    db.commit()
    return {
        "admin_created": admin_created,
        "settings_created": settings_created,
        "dishes_created": dishes_created,
    }
