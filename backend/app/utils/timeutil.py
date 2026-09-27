"""统一时间处理。

约定：**数据库里一律存"北京时间"的 naive datetime**（SQLite 不保存时区），
出接口时再用 iso() 补上 +08:00 偏移，前端不需要做时区换算。

这样设计的好处是 SQL 层可以直接比较时间（比如超时自动取消），
坏处是必须严格遵守——所以本模块同时提供 naive 与 aware 两种取值，
业务代码写库用 now_naive()，对外输出用 iso()。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 北京时间固定偏移（中国不使用夏令时）
CN_TZ = timezone(timedelta(hours=8), name="CST")


def now() -> datetime:
    """当前北京时间（带时区），仅用于计算与对外展示。"""
    return datetime.now(CN_TZ)


def now_naive() -> datetime:
    """当前北京时间（naive），用于写入数据库。"""
    return datetime.now(CN_TZ).replace(tzinfo=None)


def to_cn(dt: datetime | None) -> datetime | None:
    """把从数据库取出的 naive datetime 视作北京时间并补上时区。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(CN_TZ)


def iso(dt: datetime | None) -> str | None:
    """转成前端友好的 ISO 8601 字符串（带 +08:00）。"""
    d = to_cn(dt)
    return None if d is None else d.isoformat(timespec="seconds")


def minutes_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return round((now() - to_cn(dt)).total_seconds() / 60.0, 1)
