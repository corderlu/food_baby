"""Pydantic 模型（请求体 / 响应体）。

响应体不直接用 ORM 序列化，而是走 api 层的手工组装函数，
这样下划线命名转 camelCase、时间格式化、tags 反序列化都能集中控制。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------


class StrictModel(BaseModel):
    """多传字段直接报错，避免前端笔误被静默忽略。"""

    model_config = ConfigDict(extra="forbid")


def _clean_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------


class LoginRequest(StrictModel):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("username", "password", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class ChangePasswordRequest(StrictModel):
    old_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Annotated[str, Field(min_length=6, max_length=128)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    admin: dict[str, Any]


# ---------------------------------------------------------------------------
# 菜品
# ---------------------------------------------------------------------------


class DishBase(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    description: Annotated[str, Field(max_length=500)] = ""
    image_url: Annotated[str, Field(max_length=500)] = ""
    category: Annotated[str, Field(max_length=40)] = "其他"
    tags: list[Annotated[str, Field(max_length=20)]] = Field(default_factory=list)
    spicy_level: Annotated[int, Field(ge=0, le=3)] = 0
    estimated_minutes: Annotated[int, Field(ge=0, le=600)] = 20
    is_available: bool = True
    sort_order: int = 0

    @field_validator("name", "description", "image_url", "category", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return _clean_text(v)

    @field_validator("tags", mode="before")
    @classmethod
    def _norm_tags(cls, v: Any) -> Any:
        """允许前端传字符串 "甜,快手" 或数组 ["甜","快手"]。"""
        if v is None:
            return []
        if isinstance(v, str):
            parts = [p.strip() for p in v.replace("，", ",").split(",")]
            return [p for p in parts if p]
        if isinstance(v, (list, tuple)):
            out: list[str] = []
            for item in v:
                s = _clean_text(item)
                if s:
                    out.append(s[:20])
            return out
        return []


class DishCreate(DishBase):
    pass


class DishUpdate(StrictModel):
    """全部字段可选，只更新传了的字段。"""

    name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    description: Annotated[str, Field(max_length=500)] | None = None
    image_url: Annotated[str, Field(max_length=500)] | None = None
    category: Annotated[str, Field(max_length=40)] | None = None
    tags: list[Annotated[str, Field(max_length=20)]] | None = None
    spicy_level: Annotated[int, Field(ge=0, le=3)] | None = None
    estimated_minutes: Annotated[int, Field(ge=0, le=600)] | None = None
    is_available: bool | None = None
    sort_order: int | None = None

    @field_validator("name", "description", "image_url", "category", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return None if v is None else _clean_text(v)

    @field_validator("tags", mode="before")
    @classmethod
    def _norm_tags(cls, v: Any) -> Any:
        if v is None:
            return None
        return DishBase._norm_tags(v)


class DishToggle(StrictModel):
    is_available: bool


# ---------------------------------------------------------------------------
# 店铺设置
# ---------------------------------------------------------------------------


class SettingsUpdate(StrictModel):
    shop_name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    announcement: Annotated[str, Field(max_length=500)] | None = None
    welcome_text: Annotated[str, Field(max_length=200)] | None = None
    business_open: bool | None = None
    closed_tip: Annotated[str, Field(max_length=200)] | None = None
    today_recommend_ids: list[int] | None = None

    @field_validator("shop_name", "announcement", "welcome_text", "closed_tip", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return None if v is None else _clean_text(v)

    @field_validator("today_recommend_ids", mode="before")
    @classmethod
    def _norm_ids(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            parts = [p.strip() for p in v.replace("，", ",").split(",")]
            return [int(p) for p in parts if p.isdigit()]
        return [int(x) for x in v]


# ---------------------------------------------------------------------------
# 订单
# ---------------------------------------------------------------------------


class OrderItemIn(StrictModel):
    dish_id: int
    quantity: Annotated[int, Field(ge=1, le=99)] = 1
    item_note: Annotated[str, Field(max_length=100)] = ""

    @field_validator("item_note", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return _clean_text(v)


class OrderCreate(StrictModel):
    items: Annotated[list[OrderItemIn], Field(min_length=1)]
    customer_note: Annotated[str, Field(max_length=200)] = ""
    dish_request: Annotated[str, Field(max_length=200)] = ""
    expected_time: Annotated[str, Field(max_length=10)] = ""

    @field_validator("customer_note", "dish_request", "expected_time", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return _clean_text(v)

    @field_validator("expected_time")
    @classmethod
    def _check_time(cls, v: str) -> str:
        """允许空、HH:MM、HH:MM:SS 三种。"""
        if not v:
            return ""
        parts = v.split(":")
        if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
            raise ValueError("期望用餐时间格式应为 HH:MM")
        hh, mm = int(parts[0]), int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("期望用餐时间超出范围")
        return f"{hh:02d}:{mm:02d}"


class OrderModify(StrictModel):
    """她改单：只描述本次的增 / 减，后端做增量计算。"""

    add: list[OrderItemIn] = Field(default_factory=list)
    remove: list[OrderItemIn] = Field(default_factory=list)
    customer_note: Annotated[str, Field(max_length=200)] | None = None
    dish_request: Annotated[str, Field(max_length=200)] | None = None
    expected_time: Annotated[str, Field(max_length=10)] | None = None

    @field_validator("customer_note", "dish_request", "expected_time", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return None if v is None else _clean_text(v)

    @field_validator("expected_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        return OrderCreate._check_time(v)


class StatusUpdate(StrictModel):
    status: Literal["accepted", "preparing", "cooking", "served", "cancelled"]
    cancel_reason: Annotated[str, Field(max_length=200)] = ""

    @field_validator("cancel_reason", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return _clean_text(v)


class OrderQuery(StrictModel):
    order_nos: Annotated[list[str], Field(max_length=50)]


class CartItem(StrictModel):
    """顾客端本机购物车（只在 localStorage 里，本地校验用）。"""

    dish_id: int
    quantity: Annotated[int, Field(ge=1, le=99)] = 1
    item_note: Annotated[str, Field(max_length=100)] = ""
