#!/usr/bin/env bash
# ==========================================================================
# 爱心小食堂 · 一键部署脚本（阿里云 Ubuntu / Debian）
#
# 用法（在服务器上，用 root 或能 sudo 的账号执行）：
#   chmod +x deploy.sh
#   ./deploy.sh
#
# 脚本做的事：
#   1. 安装 python3-venv、nginx、中文字体（占位图要用）
#   2. 建虚拟环境并装后端依赖
#   3. 构建前端（服务器上需要 node，或者你本地 build 好再上传 dist/）
#   4. 装 systemd 服务 + 写 Nginx 配置
#   5. 生成一份随机 SECRET_KEY
#
# 可重复执行（幂等），改了代码后重跑即可。
# ==========================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
SERVICE_NAME="food-baby"
APP_PORT="${APP_PORT:-8801}"
RUN_USER="${RUN_USER:-$(id -un)}"

info()  { printf '\033[1;35m[爱心小食堂]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[注意]\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] && SUDO="" || SUDO="sudo"

# --------------------------------------------------------------------------
info "1/7 安装系统依赖"
if command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get update -qq
  # fonts-wqy-zenhei：没有中文字体的话，自动生成的占位图上中文会变成方块
  $SUDO apt-get install -y -qq python3 python3-venv python3-pip nginx curl ca-certificates gnupg fonts-wqy-zenhei
elif command -v yum >/dev/null 2>&1; then
  $SUDO yum install -y python3 python3-pip nginx curl wqy-zenhei-fonts
else
  warn "没识别出包管理器，请自行确认 python3 / nginx / 中文字体已安装"
fi

# --------------------------------------------------------------------------
info "2/7 准备 Node（用于构建前端）"
# 免构建的两种走法：服务器上已经有 node，或者你本地 build 好传了 dist 过来
if [[ "${SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
  info "SKIP_FRONTEND_BUILD=1，跳过 Node 安装与前端构建"
elif command -v node >/dev/null 2>&1 && [[ "$(node -v | sed 's/^v//' | cut -d. -f1)" -ge 18 ]]; then
  info "已有 Node $(node -v)，跳过安装"
elif [[ "${SKIP_NODE_INSTALL:-0}" == "1" ]]; then
  warn "SKIP_NODE_INSTALL=1 且本机没有 Node，稍后的前端构建一定会失败"
else
  info "本机没有 Node 18+，开始安装 Node 22 LTS"
  if command -v apt-get >/dev/null 2>&1; then
    # NodeSource 官方源，比 Ubuntu 自带的 nodejs 版本新很多（自带的常常是 12/18）
    NODE_MAJOR="${NODE_MAJOR:-22}"
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource_setup.sh
    $SUDO bash /tmp/nodesource_setup.sh
    rm -f /tmp/nodesource_setup.sh
    $SUDO apt-get install -y -qq nodejs
  elif command -v yum >/dev/null 2>&1; then
    curl -fsSL "https://rpm.nodesource.com/setup_22.x" -o /tmp/nodesource_setup.sh
    $SUDO bash /tmp/nodesource_setup.sh
    rm -f /tmp/nodesource_setup.sh
    $SUDO yum install -y nodejs
  else
    die "没法自动装 Node。请手动装 Node 18+ 后重跑，或者本地 build 好 dist 再执行 SKIP_FRONTEND_BUILD=1 ./deploy.sh"
  fi

  if command -v node >/dev/null 2>&1; then
    info "Node 安装完成：$(node -v) / npm $(npm -v)"
  else
    die "Node 装完了但命令还找不到，重开一个 SSH 会话再试"
  fi
fi

# --------------------------------------------------------------------------
info "3/7 准备后端虚拟环境"
cd "$BACKEND_DIR"
[[ -d .venv ]] || python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip -q
./.venv/bin/python -m pip install -r requirements.txt -q

if [[ ! -f .env ]]; then
  cp .env.example .env
  # 生成随机密钥，避免所有人用同一个默认值
  SECRET="$(head -c 48 /dev/urandom | base64 | tr -d '\n=+/' | cut -c1-48)"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env
  sed -i "s|^PORT=.*|PORT=${APP_PORT}|" .env
  info "已生成 .env（SECRET_KEY 随机）"
else
  info ".env 已存在，保留不动"
fi

# 生产环境用 Nginx 同源反代，不需要 CORS
if grep -q '^CORS_ORIGINS=' .env; then
  sed -i 's|^CORS_ORIGINS=.*|CORS_ORIGINS=|' .env
fi

# --------------------------------------------------------------------------
info "4/7 构建前端"
if [[ -d "$FRONTEND_DIR/dist" && "${SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
  info "SKIP_FRONTEND_BUILD=1，跳过构建，沿用已有 dist/"
elif command -v npm >/dev/null 2>&1; then
  cd "$FRONTEND_DIR"
  if [[ -f pnpm-lock.yaml ]]; then
    # 有锁文件就优先用 pnpm，能装出和本地完全一致的依赖版本。
    # Node 自带的 corepack 可以直接启用 pnpm，不用额外 npm i -g。
    if ! command -v pnpm >/dev/null 2>&1 && command -v corepack >/dev/null 2>&1; then
      info "用 corepack 启用 pnpm"
      $SUDO corepack enable pnpm >/dev/null 2>&1 || corepack enable pnpm >/dev/null 2>&1 || true
    fi
  fi

  if [[ -f pnpm-lock.yaml ]] && command -v pnpm >/dev/null 2>&1; then
    info "使用 pnpm 构建（$(pnpm -v)）"
    pnpm install --frozen-lockfile
    pnpm run build
  else
    info "使用 npm 构建（$(npm -v)）"
    npm install
    npm run build
  fi

  if [[ ! -f dist/index.html ]]; then
    die "前端构建完成但没产出 frontend/dist/index.html，看看上面的构建报错"
  fi
  info "前端已构建到 frontend/dist"
else
  die "SKIP_FRONTEND_BUILD=1，但 frontend/dist 不存在。
     请先在本地执行 cd frontend && pnpm build，把 dist 整个目录上传到服务器同一位置，
     或者不要设 SKIP_FRONTEND_BUILD 让脚本自动构建。"
fi

# --------------------------------------------------------------------------
info "5/7 写入 systemd 服务"
$SUDO tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=爱心小食堂 (Food Baby) FastAPI 后端
After=network.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${BACKEND_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${BACKEND_DIR}/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${APP_PORT} --workers 1
Restart=always
RestartSec=3
StandardOutput=append:/var/log/${SERVICE_NAME}.log
StandardError=append:/var/log/${SERVICE_NAME}.err.log

[Install]
WantedBy=multi-user.target
EOF

$SUDO touch "/var/log/${SERVICE_NAME}.log" "/var/log/${SERVICE_NAME}.err.log"
$SUDO chown "${RUN_USER}" "/var/log/${SERVICE_NAME}.log" "/var/log/${SERVICE_NAME}.err.log"

# --------------------------------------------------------------------------
info "6/7 写入 Nginx 配置"
CONF="/etc/nginx/conf.d/${SERVICE_NAME}.conf"
$SUDO tee "$CONF" >/dev/null <<EOF
# 爱心小食堂 —— 静态文件由 Nginx 直接发，/api 与 /uploads 反代给 FastAPI
# 没有域名时直接监听 80，用公网 IP 访问；以后有域名再换 server_name。

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    # 手机拍的照片可能十几 MB，放宽一点（后端还会自己压到长边 1200）
    client_max_body_size 20m;

    # 上传/压缩图片偶尔慢，给足超时
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;

    root ${FRONTEND_DIR}/dist;
    index index.html;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;
    gzip_comp_level 5;

    # 带 hash 的构建产物可以长期缓存
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
        try_files \$uri =404;
    }

    # 用户上传的菜品图片：一个月缓存
    location /uploads/ {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        expires 30d;
        add_header Cache-Control "public";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # 接口文档（想关掉就把下面这段删了）
    location /docs {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
    }

    # 单页应用：找不到的路径一律回 index.html，否则刷新 /my-orders 会 404
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

# --------------------------------------------------------------------------
info "7/7 启动服务"
$SUDO systemctl daemon-reload
$SUDO systemctl enable "${SERVICE_NAME}" >/dev/null
$SUDO systemctl restart "${SERVICE_NAME}"

# Nginx 默认站点会抢 80 端口，禁掉
if [[ -e /etc/nginx/sites-enabled/default ]]; then
  $SUDO rm -f /etc/nginx/sites-enabled/default
  info "已禁用 Nginx 默认站点（否则它占用 80 端口）"
fi

$SUDO nginx -t
$SUDO systemctl reload nginx
$SUDO systemctl enable nginx >/dev/null

sleep 2
echo
info "部署完成 ♥"
echo
echo "  后端服务状态：  sudo systemctl status ${SERVICE_NAME}"
echo "  后端日志：      sudo tail -f /var/log/${SERVICE_NAME}.log"
echo "  后端错误日志：  sudo tail -f /var/log/${SERVICE_NAME}.err.log"
echo "  Nginx 日志：    sudo tail -f /var/log/nginx/error.log"
echo
echo "  访问地址：      http://<你的服务器公网IP>/"
echo "  管理后台：      http://<你的服务器公网IP>/admin/login"
echo "  默认账号密码：  见 backend/.env 里的 ADMIN_USERNAME / ADMIN_PASSWORD"
echo
warn "记得去阿里云安全组放行 80 端口！"
warn "登录后台后请立刻到「账号」页修改密码。"
echo
echo "  健康检查：      curl -s http://127.0.0.1/api/health | head -c 200"
echo
