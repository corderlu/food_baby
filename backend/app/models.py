"""数据模型（对应需求文档第 6 章，并补上实现所需字段）。

对文档的几处偏差，都是有意的：
1. settings 表在文档里被截断成 `business_`，这里用 `business_open` 明确表达营业开关。
2. orders 表新增 `dish_request`：文档没写"我想吃别的"，但这是明确要求，
   单独字段存储，方便后台一眼看到，不与 customer_note 混淆。
3. orders 表新增 `day_seq` 与 `is_new`：分别用于生成当日订单序号、标记"新订单未读高亮"。
4. orders 表新增 `auto_cancel_exempt`：进入烹饪中后置 1，永不自动取消。
5. order_items 新增 `unit_price_note` 之外的字段一律不加，保持快照语义简单。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .utils.timeutil import now_naive

# ---------------------------------------------------------------------------
# 订单状态
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_PREPARING = "preparing"
STATUS_COOKING = "cooking"
STATUS_SERVED = "served"
STATUS_CANCELLED = "cancelled"

#: 正常流转顺序（不含 cancelled）
STATUS_FLOW: list[str] = [
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_PREPARING,
    STATUS_COOKING,
    STATUS_SERVED,
]

STATUS_NAMES: dict[str, str] = {
    STATUS_PENDING: "待接单",
    STATUS_ACCEPTED: "已接单",
    STATUS_PREPARING: "备菜中",
    STATUS_COOKING: "烹饪中",
    STATUS_SERVED: "出餐完成",
    STATUS_CANCELLED: "已取消",
}

#: 未完成（占用"同时只能一单"名额）
ACTIVE_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_PREPARING,
    STATUS_COOKING,
)

#: 顾客可自行修改订单明细 / 取消的状态（一旦进锅就锁死）
EDITABLE_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_PREPARING,
)

#: 可被系统自动取消的状态（"还没开始做"）
AUTO_CANCELLABLE_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_PREPARING,
)

#: 管理员手动可切换到下一状态
NEXT_STATUS: dict[str, str] = {
    STATUS_PENDING: STATUS_ACCEPTED,
    STATUS_ACCEPTED: STATUS_PREPARING,
    STATUS_PREPARING: STATUS_COOKING,
    STATUS_COOKING: STATUS_SERVED,
}


def status_name(status: str) -> str:
    return STATUS_NAMES.get(status, status)


# ---------------------------------------------------------------------------
# 表
# ---------------------------------------------------------------------------


class Admin(Base):
    """管理员（只有你一个人用）。"""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive, onupdate=now_naive, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Admin {self.id} {self.username}>"


class Dish(Base):
    """菜品。"""

    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="其他", nullable=False, index=True)
    #: JSON 字符串，如 ["甜","快手"]
    tags: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    #: 0 不辣 1 微辣 2 中辣 3 特辣
    spicy_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive, onupdate=now_naive, nullable=False)

    __table_args__ = (Index("ix_dishes_category_sort", "category", "sort_order"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Dish {self.id} {self.name}>"


class Order(Base):
    """订单。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    #: 当日序号，用于生成 XXX 部分
    day_seq: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_PENDING, nullable=False, index=True
    )
    #: 顾客备注（少辣、不要葱…）
    customer_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: "我想吃别的"——菜单里没有的许愿菜
    dish_request: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: 期望用餐时间，形如 "18:30"
    expected_time: Mapped[str] = mapped_column(String(10), default="", nullable=False)

    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: 后台是否还没看过（用于新订单高亮 + 提示音）
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    #: 修改次数（她加菜/减菜一次 +1）
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: 1 = 不参与超时自动取消
    auto_cancel_exempt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive, onupdate=now_naive, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_orders_status_created", "status", "created_at"),)

    # --- 便捷判断 ---
    @property
    def editable(self) -> bool:
        return self.status in EDITABLE_STATUSES

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def next_status(self) -> str | None:
        return NEXT_STATUS.get(self.status)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order {self.id} {self.order_no} {self.status}>"


class OrderItem(Base):
    """订单明细（菜品信息为下单当时的快照，改名不影响历史订单）。"""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: 菜品 ID，仅作追溯用，不做外键（菜品可能被删）
    dish_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dish_name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: 下单时的分类 / 图片，纯为展示方便
    dish_category: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    dish_image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    item_note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")

    # 注意：对 dish_id 不加唯一约束。新增菜品时用 "dish_id 相同则累加数量" 的
    # 方式去重，减菜到 0 直接删除行；不加约束可以让"同菜两条"这种脏数据也能被读取，
    # 后台页面点减号时不会报错。

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OrderItem {self.id} {self.dish_name} x{self.quantity}>"


class ShopSettings(Base):
    """店铺设置，全表固定只有 id=1 这一行。"""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    shop_name: Mapped[str] = mapped_column(String(80), default="爱心小食堂", nullable=False)
    announcement: Mapped[str] = mapped_column(
        Text, default="今天也要好好吃饭呀 ♥", nullable=False
    )
    #: 营业开关（手动）
    business_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: 休息中给顾客看的提示
    closed_tip: Mapped[str] = mapped_column(
        Text, default="主厨休息中，先去逛逛菜单吧～", nullable=False
    )
    #: 今日推荐菜品 ID，JSON 数组字符串
    today_recommend_ids: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    #: 店铺欢迎语（顾客端首页大标题下的小字）
    welcome_text: Mapped[str] = mapped_column(
        Text, default="想吃什么就点什么，我全都做给你吃 ♥", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive, onupdate=now_naive, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ShopSettings {self.shop_name} open={self.business_open}>"
