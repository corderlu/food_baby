"""密码哈希与 JWT。

直接用 bcrypt 库而不是 passlib：passlib 1.7.4 与 bcrypt 4.x 存在著名的
__about__ 兼容性告警，这里绕开它，减少一条无用报错。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import bcrypt
import jwt

from ..config import settings
from .timeutil import now

# bcrypt 只处理前 72 字节，超长密码先截断，避免抛异常
_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    raw = plain.encode("utf-8")[:_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        raw = plain.encode("utf-8")[:_MAX_BYTES]
        return bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> tuple[str, datetime]:
    """生成 JWT，返回 (token, 过期时间)。"""
    issued = now()
    expires = issued + timedelta(hours=settings.token_expire_hours)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解析 JWT，失败（过期/篡改）返回 None。"""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
