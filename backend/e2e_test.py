"""端到端测试：真实 HTTP 请求，走 Vite 代理（127.0.0.1:5273）。

和 smoke_test.py 的区别：
- smoke_test.py 用 TestClient 直接调 ASGI 应用，验证后端逻辑。
- 这个脚本发真实网络请求，验证「前端 dev server 代理 → 后端」这条链路，
  顺便验证所有中文内容在 UTF-8 下无损（PowerShell 会因为编码把中文写坏，
  所以这个脚本必须用 Python 跑）。

前置：后端 8801 和前端 5273 都已在运行。
用法：.venv\\Scripts\\python.exe e2e_test.py
"""

from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:5273"
API = f"{BASE}/api"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, extra: object = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"  [OK]   {name}")
    else:
        FAILED.append(f"{name} :: {extra}")
        print(f"  [FAIL] {name}  -> {extra}")


def main() -> int:
    # trust_env=False：这台机器开着系统代理（127.0.0.1:7993），
    # httpx 默认会走代理，导致访问本机 5273 被代理拦成 502。
    # 浏览器访问本机地址会走 ProxyOverride 直连，所以关掉代理更贴近真实行为。
    client = httpx.Client(base_url=BASE, timeout=20.0, trust_env=False)

    print("\n=== 0. 前端页面可访问 ===")
    r = client.get("/")
    check("SPA 首页 200", r.status_code == 200, r.status_code)
    check("有 #app 挂载点", '<div id="app">' in r.text)
    check("标题正确", "爱心小食堂" in r.text, r.text[:200])

    print("\n=== 1. 登录 ===")
    r = client.post(f"{API}/admin/login", json={"username": "admin", "password": "admin123"})
    check("登录 200", r.status_code == 200, r.text[:200])
    if r.status_code != 200:
        print("\n登录失败，后面没法继续，先检查后端是否用默认密码")
        return 1
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    print("\n=== 2. 中文内容无损（UTF-8 全链路）===")
    shop = client.get(f"{API}/shop").json()["shop"]
    check(
        "店名读到中文（无乱码）",
        "爱心" in shop["shop_name"] and "食堂" in shop["shop_name"],
        shop["shop_name"],
    )
    check("公告读到中文", "好好吃饭" in shop["announcement"], shop["announcement"])

    menu = client.get(f"{API}/menu").json()
    names = [d["name"] for d in menu["dishes"]]
    check("菜名是正常中文", "番茄炒蛋" in names and "可乐鸡翅" in names, names[:6])
    check("分类是正常中文", menu["categories"][0] == "主食", menu["categories"])
    check("标签解析成数组", isinstance(menu["dishes"][0]["tags"], list), menu["dishes"][0]["tags"])

    print("\n=== 3. 下单（含中文备注与许愿）===")
    ids = [d["id"] for d in menu["dishes"][:5]]
    WISH = "想吃糖醋排骨和草莓蛋糕"
    NOTE = "不要葱，多放肉"
    r = client.post(
        f"{API}/orders",
        json={
            "items": [
                {"dish_id": ids[0], "quantity": 2, "item_note": "少放盐"},
                {"dish_id": ids[1], "quantity": 1},
            ],
            "customer_note": NOTE,
            "dish_request": WISH,
            "expected_time": "18:30",
        },
    )
    check("下单 201", r.status_code == 201, r.text[:300])
    order = r.json()["order"]
    order_no = order["order_no"]
    check("备注中文无损", order["customer_note"] == NOTE, order["customer_note"])
    check("许愿中文无损", order["dish_request"] == WISH, order["dish_request"])
    check("单项备注无损", order["items"][0]["item_note"] == "少放盐", order["items"][0])
    check("菜名快照是中文", order["items"][0]["dish_name"] in names, order["items"][0])

    print("\n=== 4. 后台轮询（前端 5 秒提醒的数据源）===")
    r = client.get(f"{API}/admin/orders/new", params={"since_id": 0})
    check("增量拉取 200", r.status_code == 200, r.status_code)
    fresh = r.json()
    check("has_new 为 true", fresh["has_new"] is True, fresh["has_new"])
    admin_order = client.get(f"{API}/admin/orders/{order_no}").json()["order"]
    check("后台订单里也能看到许愿", admin_order["dish_request"] == WISH, admin_order["dish_request"])
    # 注意：要在"改单之前"取 revision，否则对比的是同一个值
    rev0 = admin_order["revision"]

    print("\n=== 5. 她改单 ===")
    r = client.patch(
        f"{API}/orders/{order_no}",
        json={
            "add": [{"dish_id": ids[2], "quantity": 1}],
            "remove": [{"dish_id": ids[0], "quantity": 1}],
            "customer_note": "不要葱，多放肉，谢谢主厨",
        },
    )
    check("改单 200", r.status_code == 200, r.text[:300])
    modified = r.json()["order"]
    check("改单后备注更新", modified["customer_note"] == "不要葱，多放肉，谢谢主厨", modified["customer_note"])
    check("数量 = 1+1+1", modified["total_items"] == 3, modified["total_items"])

    r = client.get(f"{API}/admin/orders/new", params={"since_id": 0})
    rev1 = r.json()["orders"][0]["revision"]
    check("轮询能看到 revision 增加", rev1 > rev0, f"{rev0} -> {rev1}")
    check("改单不清 is_new", r.json()["orders"][0]["is_new"] is True)

    print("\n=== 6. 状态流转 + 锁死 ===")
    for target, label in (("accepted", "接单"), ("preparing", "备菜"), ("cooking", "下锅")):
        r = client.post(f"{API}/admin/orders/{order_no}/status", json={"status": target})
        check(f"{label} -> {target}", r.status_code == 200 and r.json()["order"]["status"] == target, r.text[:200])

    r = client.patch(f"{API}/orders/{order_no}", json={"add": [{"dish_id": ids[3], "quantity": 1}]})
    check("烹饪中改单被锁（409）", r.status_code == 409, r.status_code)
    check("锁死提示是中文", "改不了" in r.json()["detail"], r.json()["detail"])

    r = client.post(f"{API}/admin/orders/{order_no}/status", json={"status": "served"})
    check("出餐完成", r.status_code == 200 and r.json()["order"]["status"] == "served", r.text[:200])

    print("\n=== 7. 店铺设置（中文写入）===")
    new_name = "宝宝的小厨房 ♥"
    r = client.patch(
        f"{API}/admin/settings",
        json={"shop_name": new_name, "today_recommend_ids": [ids[1]], "announcement": "今天做你最爱吃的"},
    )
    check("设置保存 200", r.status_code == 200, r.text[:200])
    check("店名回读一致", r.json()["settings"]["shop_name"] == new_name, r.json()["settings"]["shop_name"])

    r = client.get(f"{API}/shop")
    check("顾客端读到新店名", r.json()["shop"]["shop_name"] == new_name, r.json()["shop"]["shop_name"])
    check("顾客端读到新公告", r.json()["shop"]["announcement"] == "今天做你最爱吃的")
    check("今日推荐生效", [d["id"] for d in r.json()["recommends"]] == [ids[1]], r.json()["recommends"])

    # 还原，避免影响手动体验
    client.patch(
        f"{API}/admin/settings",
        json={"shop_name": "爱心小食堂", "today_recommend_ids": [], "announcement": "今天也要好好吃饭呀 ♥"},
    )

    print("\n=== 8. 图片上传（经代理，含压缩）===")
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (2400, 1800), (255, 205, 220)).save(buf, "JPEG", quality=95)
    r = client.post(
        f"{API}/admin/dishes/upload-image",
        files={"file": ("pic.jpg", buf.getvalue(), "image/jpeg")},
    )
    check("上传 200", r.status_code == 200, r.text[:300])
    up = r.json()
    check("长边压到 1200", max(up["width"], up["height"]) == 1200, up)
    check("主图经代理可访问", client.get(up["image_url"]).status_code == 200)
    check("缩略图经代理可访问", client.get(up["thumb_url"]).status_code == 200)
    thumb = client.get(up["thumb_url"]).content
    main_bytes = client.get(up["image_url"]).content
    check("缩略图比主图小", len(thumb) < len(main_bytes), f"{len(thumb)} vs {len(main_bytes)}")

    print("\n=== 9. 占位图（中文菜名）===")
    r = client.get(f"{API}/menu")
    first_img = r.json()["dishes"][0]["image_url"]
    check("预置菜品有占位图", first_img.endswith(".jpg"), first_img)
    img = client.get(first_img)
    check("占位图可访问", img.status_code == 200, img.status_code)
    check("占位图是真 JPEG", img.content[:2] == b"\xff\xd8", img.content[:4])

    print("\n=== 10. 清理超时单接口 ===")
    r = client.post(f"{API}/admin/orders/auto-cancel-stale")
    check("手动巡检 200", r.status_code == 200, r.text[:200])
    check(
        "返回中文消息",
        "取消" in r.json()["message"] or "没有超时订单" in r.json()["message"],
        r.json()["message"],
    )
    print("\n=== 11. 422 校验错误也是中文友好 ===")
    r = client.post(f"{API}/orders", json={"items": []})
    check("空购物车 422", r.status_code == 422, r.status_code)

    print("\n" + "=" * 60)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("\n失败明细：")
        for f in FAILED:
            print(f"  - {f}")
    print("=" * 60)

    client.close()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
