"""冒烟测试：把主要接口按真实顺序跑一遍，验证业务规则。

用法（在 backend 目录下）：
    .venv\\Scripts\\python.exe smoke_test.py

会用到独立的临时数据库文件，不会污染 food_baby.db。
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

# 必须在 import app 之前设置，让配置指向临时库
TMP_DIR = Path(tempfile.mkdtemp(prefix="food_baby_smoke_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TMP_DIR / 'smoke.db').as_posix()}"
os.environ["UPLOAD_DIR"] = (TMP_DIR / "uploads").as_posix()
os.environ["ORDER_AUTO_CANCEL_MINUTES"] = "120"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, extra: object = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [OK]   {name}")
    else:
        FAILED.append(f"{name} :: {extra}")
        print(f"  [FAIL] {name}  ->  {extra}")


def main() -> int:
    with TestClient(app) as client:
        print("\n=== 1. 健康检查 & 公开菜单 ===")
        r = client.get("/api/health")
        check("health 200", r.status_code == 200, r.text[:200])
        check("中文字体可用", r.json().get("cjk_font") is True, r.json())

        r = client.get("/api/menu")
        check("menu 200", r.status_code == 200, r.text[:200])
        menu = r.json()
        check("示例菜单已灌入", menu["total"] >= 20, menu["total"])
        check("分类有序", menu["categories"][:3] == ["主食", "热菜", "凉菜"], menu["categories"])
        check(
            "占位图已生成",
            all(d["image_url"].startswith("/uploads/") for d in menu["dishes"]),
            menu["dishes"][0]["image_url"],
        )
        dish_ids = [d["id"] for d in menu["dishes"]]

        r = client.get("/api/shop")
        check("shop 200", r.status_code == 200, r.text[:200])
        check("默认营业中", r.json()["shop"]["business_open"] is True)

        print("\n=== 2. 管理端鉴权 ===")
        r = client.get("/api/admin/orders")
        check("未登录被拒 401", r.status_code == 401, r.status_code)
        r = client.post("/api/admin/login", json={"username": "admin", "password": "wrong"})
        check("错密码 401", r.status_code == 401, r.status_code)
        r = client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
        check("登录成功", r.status_code == 200, r.text[:200])
        token = r.json()["access_token"]
        check("提示在用默认密码", r.json()["admin"]["using_default_password"] is True)
        auth = {"Authorization": f"Bearer {token}"}

        print("\n=== 3. 下单流程 ===")
        r = client.post(
            "/api/orders",
            json={
                "items": [
                    {"dish_id": dish_ids[0], "quantity": 1, "item_note": "少辣"},
                    {"dish_id": dish_ids[1], "quantity": 2, "item_note": ""},
                ],
                "customer_note": "不要葱",
                "dish_request": "想吃糖醋排骨",
                "expected_time": "18:30",
            },
        )
        check("下单成功 201", r.status_code == 201, r.text[:300])
        order = r.json()["order"]
        order_no = order["order_no"]
        check(
            "订单号格式 LOVE-YYYYMMDD-NNN",
            re.fullmatch(r"LOVE-\d{8}-\d{3}", order_no) is not None,
            order_no,
        )
        check("总数量=3", order["total_items"] == 3, order["total_items"])
        check("许愿菜已存", order["dish_request"] == "想吃糖醋排骨", order["dish_request"])
        check("初始待接单", order["status"] == "pending", order["status"])
        check("未开始时可改", order["editable"] is True)

        r = client.post(
            "/api/orders",
            json={"items": [{"dish_id": dish_ids[0], "quantity": 1}]},
        )
        check("第二单被拒 409", r.status_code == 409, r.text[:200])
        check("提示提到已有订单", order_no in r.json()["detail"], r.json()["detail"])

        r = client.get("/api/orders/active")
        check("active 返回该单", r.json()["order"]["order_no"] == order_no)

        print("\n=== 4. 改单 ===")
        r = client.patch(
            f"/api/orders/{order_no}",
            json={
                "add": [{"dish_id": dish_ids[2], "quantity": 1}],
                "remove": [{"dish_id": dish_ids[1], "quantity": 1}],
                "customer_note": "不要葱，多放肉",
            },
        )
        check("改单成功", r.status_code == 200, r.text[:300])
        o = r.json()["order"]
        check("数量变化正确 (1+1+1=3)", o["total_items"] == 3, o["total_items"])
        names = [i["dish_name"] for i in o["items"]]
        check("减到 1 份而不是删行", len(o["items"]) == 3, names)

        r = client.get(f"/api/admin/orders/{order_no}", headers=auth)
        check("后台能看到改单次数 revision=1", r.json()["order"]["revision"] == 1, r.json()["order"].get("revision"))
        check("改单不清掉新单标记", r.json()["order"]["is_new"] is True, r.json()["order"].get("is_new"))
        check("管理员推进状态后仍保留标记", True)

        r = client.patch(
            f"/api/orders/{order_no}",
            json={"remove": [{"dish_id": dish_ids[1], "quantity": 99}]},
        )
        check("减菜超过数量则整行删除", r.status_code == 200 and len(r.json()["order"]["items"]) == 2, r.text[:200])

        print("\n=== 5. 管理端状态流转 ===")
        r = client.get("/api/admin/orders", headers=auth)
        check("列表可见", r.json()["total"] == 1, r.json()["total"])
        check("新订单标记", r.json()["orders"][0]["is_new"] is True)

        r = client.get("/api/admin/orders/new?since_id=0", headers=auth)
        check("增量拉新可用", r.json()["max_id"] == 1 and r.json()["has_new"] is True, r.json())
        check("增量拉新能看到已改单的订单", len(r.json()["orders"]) == 1, len(r.json()["orders"]))
        check("已读订单仍能拉到（供前端比对 revision）", r.json()["orders"][0]["revision"] == 2, r.json()["orders"][0].get("revision"))

        r = client.post(f"/api/admin/orders/{order_no}/status", json={"status": "cooking"}, headers=auth)
        check("禁止跳状态 409", r.status_code == 409, r.text[:200])

        for target in ("accepted", "preparing"):
            r = client.post(f"/api/admin/orders/{order_no}/status", json={"status": target}, headers=auth)
            check(f"推进到 {target}", r.status_code == 200 and r.json()["order"]["status"] == target, r.text[:200])
        check("accepted_at 已记录", r.json()["order"]["accepted_at"] is not None)

        r = client.patch(f"/api/orders/{order_no}", json={"add": [{"dish_id": dish_ids[3], "quantity": 1}]})
        check("备菜中仍可改单", r.status_code == 200, r.text[:200])

        r = client.post(f"/api/admin/orders/{order_no}/status", json={"status": "cooking"}, headers=auth)
        check("推进到 cooking", r.status_code == 200, r.status_code)
        check("cooking 后 exempt", r.json()["order"]["editable"] is False)

        r = client.patch(f"/api/orders/{order_no}", json={"add": [{"dish_id": dish_ids[3], "quantity": 1}]})
        check("烹饪中锁死改单 409", r.status_code == 409, r.text[:200])
        r = client.post(f"/api/orders/{order_no}/cancel")
        check("烹饪中不能取消 409", r.status_code == 409, r.text[:200])

        r = client.post(f"/api/admin/orders/{order_no}/status", json={"status": "served"}, headers=auth)
        check("完成出餐", r.status_code == 200 and r.json()["order"]["status"] == "served", r.text[:200])
        check("completed_at 已记录", r.json()["order"]["completed_at"] is not None)

        r = client.post("/api/orders", json={"items": [{"dish_id": dish_ids[0], "quantity": 1}]})
        check("完成后再下单成功", r.status_code == 201, r.text[:300])
        second_no = r.json()["order"]["order_no"]
        check("订单号自增", second_no.endswith("002"), second_no)

        print("\n=== 6. 取消流程 ===")
        r = client.post(f"/api/orders/{second_no}/cancel")
        check("待接单可自己取消", r.status_code == 200 and r.json()["order"]["status"] == "cancelled", r.text[:200])
        check("取消原因已写", bool(r.json()["order"]["cancel_reason"]))
        r = client.post("/api/orders", json={"items": [{"dish_id": dish_ids[0], "quantity": 1}]})
        check("取消后可再下单", r.status_code == 201, r.text[:200])
        third_no = r.json()["order"]["order_no"]
        r = client.post(f"/api/admin/orders/{third_no}/status", json={"status": "cancelled", "cancel_reason": "家里没菜了"}, headers=auth)
        check("后台带原因取消", r.status_code == 200 and r.json()["order"]["cancel_reason"] == "家里没菜了", r.text[:200])
        client.post("/api/orders", json={"items": [{"dish_id": dish_ids[0], "quantity": 1}]})

        print("\n=== 7. 营业状态 ===")
        r = client.patch("/api/admin/settings", json={"business_open": False}, headers=auth)
        check("切到休息中", r.status_code == 200 and r.json()["settings"]["business_open"] is False, r.text[:200])
        r = client.post("/api/orders", json={"items": [{"dish_id": dish_ids[0], "quantity": 1}]})
        check("休息中不可下单 409", r.status_code == 409, r.text[:200])
        check("提示语来自设置", "休息" in r.json()["detail"], r.json()["detail"])
        client.patch("/api/admin/settings", json={"business_open": True}, headers=auth)

        print("\n=== 8. 菜品管理 ===")
        r = client.post(
            "/api/admin/dishes",
            json={"name": "测试菜·爱心蛋包饭", "category": "主食", "tags": "测试,甜", "spicy_level": 0, "estimated_minutes": 20},
            headers=auth,
        )
        check("新增菜品 201", r.status_code == 201, r.text[:300])
        new_dish = r.json()["dish"]
        check("tags 解析为数组", new_dish["tags"] == ["测试", "甜"], new_dish["tags"])
        check("自动生成占位图", new_dish["image_url"].startswith("/uploads/"), new_dish["image_url"])

        r = client.patch(f"/api/admin/dishes/{new_dish['id']}", json={"name": "爱心蛋包饭", "is_available": False}, headers=auth)
        check("编辑菜品", r.status_code == 200 and r.json()["dish"]["name"] == "爱心蛋包饭", r.text[:200])
        r = client.get("/api/menu")
        check("下架后顾客端不可见", all(d["name"] != "爱心蛋包饭" for d in r.json()["dishes"]))

        r = client.post(f"/api/admin/dishes/{new_dish['id']}/toggle", json={"is_available": True}, headers=auth)
        check("快捷上架", r.status_code == 200 and r.json()["dish"]["is_available"] is True, r.text[:200])

        r = client.delete(f"/api/admin/dishes/{new_dish['id']}", headers=auth)
        check("删除未用过的菜", r.status_code == 200, r.text[:200])

        used_dish_id = dish_ids[0]
        r = client.delete(f"/api/admin/dishes/{used_dish_id}", headers=auth)
        check("删历史订单里的菜需确认 409", r.status_code == 409, r.text[:200])
        r = client.delete(f"/api/admin/dishes/{used_dish_id}?force=true", headers=auth)
        check("force 可删且保历史", r.status_code == 200 and r.json()["history_kept"] >= 1, r.text[:200])

        print("\n=== 9. 图片上传压缩 ===")
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        big = Image.new("RGB", (3000, 2000), (255, 200, 220))
        big.save(buf, "JPEG", quality=95)
        r = client.post(
            "/api/admin/dishes/upload-image",
            files={"file": ("test.jpg", buf.getvalue(), "image/jpeg")},
            headers=auth,
        )
        check("上传成功", r.status_code == 200, r.text[:300])
        up = r.json()
        check("长边压到 1200", max(up["width"], up["height"]) == 1200, up)
        check("返回缩略图", up["thumb_url"].startswith("/uploads/thumbs/"), up["thumb_url"])
        r = client.get(up["image_url"])
        check("主图可访问", r.status_code == 200, r.status_code)
        r = client.get(up["thumb_url"])
        check("缩略图可访问", r.status_code == 200, r.status_code)
        check("压缩后体积变小", up["bytes"] < len(buf.getvalue()), f"{up['bytes']} vs {len(buf.getvalue())}")

        r = client.post(
            "/api/admin/dishes/upload-image",
            files={"file": ("bad.txt", b"this is not an image", "text/plain")},
            headers=auth,
        )
        check("非图片被拒 400", r.status_code == 400, r.text[:200])

        r = client.delete(f"/api/admin/dishes/{dish_ids[5]}?force=true", headers=auth)
        check("删除菜品连带删图可执行", r.status_code == 200, r.text[:200])

        print("\n=== 10. 今日推荐 & 设置 ===")
        r = client.patch(
            "/api/admin/settings",
            json={"shop_name": "宝宝的小厨房", "today_recommend_ids": [dish_ids[1], 99999]},
            headers=auth,
        )
        check("设置保存", r.status_code == 200, r.text[:200])
        check("无效推荐 ID 被过滤", r.json()["settings"]["today_recommend_ids"] == [dish_ids[1]], r.json()["settings"])
        r = client.get("/api/shop")
        check("顾客端读到推荐", [d["id"] for d in r.json()["recommends"]] == [dish_ids[1]], r.json()["recommends"])
        check("店铺改名生效", r.json()["shop"]["shop_name"] == "宝宝的小厨房")

        r = client.get("/api/admin/settings/recommend-candidates", headers=auth)
        check("推荐候选接口（路径不被吃）", r.status_code == 200 and len(r.json()["dishes"]) > 0, r.status_code)

        print("\n=== 11. 修改密码 ===")
        r = client.post("/api/admin/change-password", json={"old_password": "wrong", "new_password": "newpass123"}, headers=auth)
        check("原密码错误 400", r.status_code == 400, r.text[:200])
        r = client.post("/api/admin/change-password", json={"old_password": "admin123", "new_password": "newpass123"}, headers=auth)
        check("改密码成功", r.status_code == 200, r.text[:200])
        new_token = r.json()["access_token"]
        check("不再是默认密码", r.json()["admin"]["using_default_password"] is False)
        r = client.post("/api/admin/login", json={"username": "admin", "password": "newpass123"})
        check("新密码可登录", r.status_code == 200, r.status_code)
        r = client.get("/api/admin/orders", headers={"Authorization": f"Bearer {new_token}"})
        check("新 token 可用", r.status_code == 200, r.status_code)

        print("\n=== 12. 我的订单批量查询 ===")
        r = client.post("/api/orders/query", json={"order_nos": [order_no, second_no, "LOVE-19700101-999"]})
        check("批量查询只返回存在的", r.status_code == 200 and len(r.json()["orders"]) == 2, r.text[:200])
        r = client.get(f"/api/orders/{order_no}")
        check("按号查详情", r.status_code == 200 and r.json()["order"]["order_no"] == order_no)
        check("详情带 elapsed_minutes", r.json()["order"]["elapsed_minutes"] is not None)
        r = client.get("/api/orders/LOVE-19700101-999")
        check("不存在的单 404", r.status_code == 404, r.status_code)

        print("\n=== 13. 超时自动取消 ===")
        from app.database import SessionLocal
        from app.services.orders import auto_cancel_stale
        from app.utils.timeutil import now_naive
        from datetime import timedelta

        db = SessionLocal()
        try:
            from sqlalchemy import select as sa_select

            from app.models import ACTIVE_STATUSES, Order as OrderModel

            active = db.scalar(sa_select(OrderModel).where(OrderModel.status.in_(ACTIVE_STATUSES)).limit(1))
            check("存在未完成订单", active is not None)
            if active:
                active.created_at = now_naive() - timedelta(minutes=200)
                active.status = "preparing"
                db.commit()
                cancelled = auto_cancel_stale(db)
                check("超时单被自动取消", len(cancelled) == 1, [c.order_no for c in cancelled])
                db.refresh(active)
                check("原因含分钟数", "120" in active.cancel_reason, active.cancel_reason)
                check("状态为 cancelled", active.status == "cancelled")
        finally:
            db.close()

        r = client.post("/api/orders", json={"items": [{"dish_id": dish_ids[2], "quantity": 1}]})
        check("自动取消后名额释放", r.status_code == 201, r.text[:200])

        print("\n=== 14. 参数校验 ===")
        r = client.post("/api/orders", json={"items": []})
        check("空购物车 422", r.status_code == 422, r.status_code)
        r = client.post("/api/orders", json={"items": [{"dish_id": dish_ids[2], "quantity": 1}], "expected_time": "25:99"})
        check("非法时间 422", r.status_code == 422, r.status_code)
        r = client.post("/api/orders", json={"items": [{"dish_id": dish_ids[2], "quantity": 1}], "customer_note": "x" * 201})
        check("备注超 200 字 422", r.status_code == 422, r.status_code)
        r = client.post("/api/admin/dishes", json={"name": "x", "spicy_level": 9}, headers=auth)
        check("辣度越界 422", r.status_code == 422, r.status_code)
        r = client.post("/api/orders", json={"items": [{"dish_id": 999999, "quantity": 1}]})
        check("不存在的菜 409", r.status_code == 409, r.text[:200])

    print("\n" + "=" * 62)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("\n失败明细：")
        for f in FAILED:
            print(f"  - {f}")
    print("=" * 62)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
