# 爱心小食堂 · 情侣专属点餐系统

给女朋友做的手机点餐网页：**她点菜，你接单做菜。**
手机浏览器打开就能用，不需要注册、不需要小程序、不需要支付。

```
她：  浏览菜单 → 加购物车 → 写下"我想吃别的" → 提交 → 看状态做到哪一步了
你：  后台收到提醒（响铃 + 标题闪烁）→ 接单 → 备菜 → 下锅 → 出餐
```

---

## 目录结构

```
food baby/
├── backend/                     FastAPI + SQLite 后端
│   ├── app/
│   │   ├── main.py              入口：建表、灌种子数据、挂路由、起超时巡检
│   │   ├── config.py            全部配置走环境变量 / .env
│   │   ├── database.py          SQLAlchemy 会话（WAL 模式）
│   │   ├── models.py            表结构 + 订单状态机常量
│   │   ├── schemas.py           请求/响应校验
│   │   ├── serializers.py       ORM → JSON
│   │   ├── deps.py              JWT 鉴权依赖
│   │   ├── api/                 路由：menu / orders / admin_*
│   │   ├── services/            orders（业务规则）、images（压缩）、seed（种子）
│   │   └── static/uploads/      上传的菜品图 + 自动生成的占位图（不入库）
│   ├── requirements.txt
│   ├── .env.example             复制成 .env 后按需改（.env 本身不入库）
│   ├── smoke_test.py            94 项接口冒烟测试（TestClient，不污染正式库）
│   └── e2e_test.py              44 项真实 HTTP 测试（需先起前后端）
├── frontend/                    Vue 3 + Vite + Vant + Pinia
│   ├── src/
│   │   ├── views/customer/      顾客端：菜单 / 购物车 / 订单详情 / 我的订单 / 下单成功
│   │   ├── views/admin/         管理端：登录 / 订单看板 / 菜品管理 / 店铺设置 / 账号
│   │   ├── stores/              cart、shop、auth、customerOrders
│   │   ├── api/                 axios 封装 + 接口定义
│   │   ├── utils/sound.ts       Web Audio 合成提示音（不依赖音频文件）
│   │   ├── utils/order.ts       状态元数据（文案/颜色/emoji）
│   │   └── styles/theme.css     主题变量，换配色只改这个文件
│   ├── scripts/measure-overlap.mjs  布局验证脚本（检查操作条不遮住底部导航）
│   ├── vite.config.ts           本地代理 /api 和 /uploads 到 8801
│   └── dist/                    构建产物（不入库，部署时生成）
├── deploy.sh                    阿里云 Ubuntu 一键部署（可重复执行）
├── start-dev.ps1                Windows 本地一键启动
└── .gitattributes               强制 deploy.sh 用 LF 换行（否则 Linux 上跑不起来）
```

---

## 本地开发

环境要求（已验证版本）：Python 3.12、Node 22、pnpm 12。

### 第一次准备

```powershell
# 后端
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env

# 前端
cd ..\frontend
pnpm install
```

### 日常启动

在项目根目录执行：

```powershell
.\start-dev.ps1
```

它会开两个窗口，并打印手机真机预览地址。也可以手动分别启动：

```powershell
# 窗口 1
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8801 --reload

# 窗口 2
cd frontend
pnpm run dev
```

| 地址 | 用途 |
| --- | --- |
| http://127.0.0.1:5273/ | 顾客端（点菜页） |
| http://127.0.0.1:5273/admin/login | 管理后台 |
| http://127.0.0.1:8801/docs | 后端接口文档（Swagger） |

> 端口特意用 **8801 / 5273**，因为 8000 和 5173 常被其他项目占用。
> 想改端口：后端改 `backend/.env` 里的 `PORT`；前端改 `vite.config.ts` 的 `server.port`，
> 同时把 `proxy` 的 target 指向新的后端端口。

### 手机真机预览

手机连**同一个 Wi-Fi**，浏览器打开 `http://<电脑局域网IP>:5273/`。
`start-dev.ps1` 会直接把地址打印出来。前端 Vite 已配置 `host: true`，无需额外设置。

> 如果打不开，多半是 Windows 防火墙拦了 Node。放行一次即可：
> `New-NetFirewallRule -DisplayName "Vite 5273" -Direction Inbound -LocalPort 5273 -Protocol TCP -Action Allow`

---

## 上线到阿里云

### 服务器上拉代码

```bash
# 1. 装 git（新买的服务器通常没有）
sudo apt update && sudo apt install -y git

# 2. 拉代码。仓库是私有的，用 HTTPS 会要求输入用户名 + Personal Access Token
#    （GitHub 从 2021 年起不再支持密码，Token 在 Settings → Developer settings →
#      Personal access tokens 生成，勾选 repo 权限即可）
cd ~
git clone https://github.com/corderlu/food_baby.git "food baby"
cd "food baby"
```

> 也可以配 SSH 免密，但一次性 clone 用 Token 更省事。
> 服务器上如果 `git clone` 卡住不动，多半是网络问题，重试一次通常就好。

### 方式一：一键脚本（推荐）

```bash
chmod +x deploy.sh
./deploy.sh
```

脚本会自动完成 7 步：装系统依赖（含中文字体）→ **装 Node 22**（如果服务器上没有）→
建虚拟环境 → 构建前端 → 写 systemd 服务 → 写 Nginx 配置 → 启动。**可重复执行**，改了代码重跑一次就行。

几个可选开关（一般用不到）：

| 环境变量 | 作用 |
| --- | --- |
| `APP_PORT=8801` | 后端监听端口，默认就是 8801 |
| `NODE_MAJOR=20` | 想装别的 Node 大版本 |
| `SKIP_NODE_INSTALL=1` | 服务器已有 Node，跳过安装 |
| `SKIP_FRONTEND_BUILD=1` | 本地 build 好 dist 上传了，跳过构建（此时必须先有 `frontend/dist`） |
| `RUN_USER=www-data` | 指定 systemd 服务运行用户，默认当前登录用户 |

### 方式二：手动部署

```bash
# 1. 系统依赖（fonts-wqy-zenhei 必须装，否则占位图上中文是方块）
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx curl fonts-wqy-zenhei

# 2. Node（用于构建前端）
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# 3. 后端
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
# 改 .env：把 SECRET_KEY 换成随机串，PORT=8801

# 4. 前端
cd ../frontend
npm install && npm run build     # 或 pnpm install && pnpm run build

# 5. systemd + Nginx 配置见 deploy.sh 里写出的那两份
```

Nginx 配置的关键三点：静态文件由 Nginx 直接发；`/api` 和 `/uploads` 反代到 `127.0.0.1:8801`；
`location /` 用 `try_files $uri $uri/ /index.html` 兜底——否则在 `/my-orders` 页刷新会 404。

### 部署后必做

1. **阿里云安全组放行 80 端口**（默认只开 22，这一步不做的话外网访问不了）。
2. 打开 `http://<公网IP>/admin/login`，用 `admin` / `admin123` 登录。
3. **立刻到「账号」页改密码**——没改的话后台会一直显示警告。
4. 到「店铺设置」里把店名、公告、欢迎语改成你们自己的。

### 以后更新代码

```bash
cd ~/"food baby"
git pull
./deploy.sh          # 重新构建前端 + 重启后端
```

数据库 `backend/food_baby.db` 和上传的图片都在 `.gitignore` 里，**`git pull` 不会覆盖它们**，
你的菜品和订单数据是安全的。

### 关于 HTTPS


现在没有域名，所以是 **HTTP + 公网 IP** 直连。这带来的实际影响：

| 能力 | HTTP 下是否可用 |
| --- | --- |
| 提示音（Web Audio） | ✅ 可用 |
| localStorage（购物车、我的订单） | ✅ 可用 |
| 页面标题闪烁提醒 | ✅ 可用 |
| 手机震动 | ⚠️ 部分安卓可用，iOS Safari 不支持 |
| 加到主屏幕（PWA） | ❌ 需要 HTTPS |
| Supabase 等加密 API | ❌ 用不到，忽略 |

也就是说核心功能一个都不缺。以后买了域名，让 Nginx 监听 443 + 阿里云免费 SSL 证书即可，
代码不用改。

---

## 功能说明

### 顾客端（她）

- **菜单首页**：店铺名、欢迎语、公告、营业状态；今日推荐横向卡片；分类 tab 与滚动联动；
  菜品卡片显示图片、描述、辣度、预计时间、标签。
- **购物车**：加减数量、单项备注、清空；数据存 localStorage，切出去再回来还在。
- **下单**：备注（≤200 字）、**「我想吃别的」许愿框**、期望用餐时间（5 分钟粒度）。
- **订单详情**：五步进度条，**每 10 秒自动刷新**；能看到取消原因。
- **改单**：待接单 / 已接单 / 备菜中都能加菜减菜改备注，**一旦"烹饪中"就锁死**。
- **我的订单**：本机历史订单，支持用订单号找回（换手机时用）。

### 管理端（你）

- **登录**：JWT，token 默认 30 天；失效自动跳登录页。
- **订单看板**：**每 5 秒轮询**。新订单 → 卡片高亮 + 提示音 + 页面标题闪烁 + 手机震动。
  状态筛选、一键推进（接单→备菜→下锅→出餐）、带原因取消、复制单号发给她。
  **她改单时放另一种音效**（两声短嘟），和"新订单"区分开。
- **菜品管理**：增删改、上下架快捷开关、排序、标签、辣度、预计时间。
  **图片上传自动压缩**（长边 1200 / 质量 86 / 纠正 EXIF 旋转 / 生成 400 缩略图），
  也可以一键按菜名生成粉色爱心占位图。
- **店铺设置**：店名、公告、欢迎语、休息提示语、营业开关、今日推荐。
- **账号**：改密码 + 运行状态自检（后端连通性、中文字体是否装好、提示音是否可用）。

---

## 设计取舍（都是有意为之）

| 决定 | 原因 |
| --- | --- |
| 启动自动建表，不用 Alembic | 两人使用、数据量极小；改字段时删 `food_baby.db` 重启即可（先备份） |
| 同时只允许一个未完成订单 | 避免你同时开两锅 |
| 未开始做的订单 **2 小时**自动取消 | 万一下了单你没看到，不会永久堵死她的下单入口 |
| 进「烹饪中」后订单永不自动取消 | 菜都下锅了不能被系统撤单 |
| 订单明细存菜名快照 | 你之后改菜名/删菜，历史订单显示的还是当时那个名字 |
| 我的订单存 localStorage | 她不用注册登录；代价是换手机会看不到，所以做了"用订单号找回" |
| 提示音用 Web Audio 现场合成 | 不用带 mp3 文件，也不会因为音频 404 而"没声音" |
| 顾客端每 60 秒静默刷新菜单 | 你改了菜或切营业状态，她不用手动刷新 |
| 图片在服务端压缩 | 手机原图动辄 5MB，压完通常 100~300KB，她加载快很多 |

---

## 测试

```powershell
# 后端接口冒烟测试（用临时数据库，不影响正式数据）
cd backend
.\.venv\Scripts\python.exe smoke_test.py      # 94 项

# 端到端真实 HTTP 测试（需要后端 8801 + 前端 5273 都在跑）
.\.venv\Scripts\python.exe e2e_test.py        # 44 项
```

前端类型检查与构建：

```powershell
cd frontend
pnpm run type-check     # vue-tsc，0 错误
pnpm run build          # 产物在 dist/
```

---

## 常见问题

**提示音不响？**
浏览器要求用户先交互才能播声音。后台页面上点一下「开启提示音」按钮即可，
这个偏好会记住。如果还是不行，检查手机静音开关和浏览器音量权限。

**页面标题一直闪？**
说明有新订单或她改了单。处理完点「全部标记为看过」就停了。

**她看不到某个菜？**
到「菜品管理」确认那道菜是不是被下架了（开关关掉后顾客端不显示）。

**改了菜名，历史订单也跟着变了吗？**
不会。订单明细存的是下单当时的快照，这就是文档里要求的行为。

**想改配色？**
改 `frontend/src/styles/theme.css` 里的 CSS 变量即可，所有页面都从这里取色。
改完 `pnpm run build` 重新构建。

**数据库想重置（清空所有订单和菜品）？**
停掉后端，删掉 `backend/food_baby.db`，重新启动会自动建表并灌入示例菜品。
上传的图片在 `backend/app/static/uploads/`，想一起清就删掉里面的文件。

### 服务器上的常见问题

**`./deploy.sh: /usr/bin/env: bad interpreter` 或满屏 `$'\r': command not found`**
脚本被存成了 CRLF 换行。仓库里的 `.gitattributes` 已经强制 `*.sh` 用 LF，
正常 clone 不会出这个问题；如果是手动传文件上去的，跑一下：
`sed -i 's/\r$//' deploy.sh`

**`git clone` 卡住很久**
国内服务器访问 GitHub 偶尔会慢或超时，重试一次；连续失败就换 SSH 方式，
或者在你本地 `git bundle` 打包后用 scp 传上去。

**`npm run build` 被 Killed（内存不足）**
1 核 2G 的机器构建 Vite 可能 OOM。加 swap 最省事：
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**外网打不开，但 `curl http://127.0.0.1/api/health` 正常**
阿里云安全组没放行 80 端口，去控制台加一条入方向规则。

**页面能打开但图片是空白/方块**
- 图片空白：`backend/app/static/uploads/` 权限不对，或者 Nginx 的 `/uploads/` 反代没生效。
- 占位图上中文是方块：服务器缺中文字体，`sudo apt install -y fonts-wqy-zenhei` 后重启后端。

**改完代码 `git pull` 重启后看不到变化**
前端要重新构建（`./deploy.sh` 会做）。浏览器也可能缓存了旧的 JS，
强刷一次 `Ctrl+F5`，或者在 Nginx 里确认 `/assets/` 的缓存策略。
