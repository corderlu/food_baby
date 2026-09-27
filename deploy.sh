#!/usr/bin/env bash
# ==========================================================================
# 爱心小食堂 · 一键部署脚本（阿里云 Ubuntu / Debian）
#
# 用法（在服务器上，用 root 或能 sudo 的账号执行）：
#   chmod +x deploy.sh
#   ./deploy.sh
#
# 脚本做的事（7 步）：
#   1. 安装系统依赖：python3-venv、nginx、中文字体（占位图要用）
#   2. 没有 Node 18+ 就自动装 Node 22 LTS
#   3. 建虚拟环境、装后端依赖、生成随机 SECRET_KEY
#   4. 构建前端
#   5. 装 systemd 服务并启动
#   6. 写一个【独立端口】的 Nginx server 块
#   7. 校验 + reload，失败自动回滚
#
# 可重复执行（幂等），改了代码后重跑即可。
#
# --------------------------------------------------------------------------
# 重要：这个脚本被设计成【绝不影响服务器上已有的网站】
#
#   如果你服务器上已经跑了别的站点，请务必先设好 NGINX_PORT，
#   用一个不和现有站点冲突的端口（默认 8080）：
#       NGINX_PORT=8080 ./deploy.sh
#
#   脚本遵守以下几条纪律：
#     * 只写自己的配置文件 /etc/nginx/conf.d/food-baby.conf，不碰别人的文件
#     * 不使用 default_server（这和"抢占默认站点"是一回事，会和已有站点冲突）
#     * 不删除 /etc/nginx/sites-enabled/default（那可能是你现有站点的配置！）
#     * reload 之前先跑 nginx -t；配置不合法就回滚到旧文件并清空启用链接
#     * 后端起不来就不动 Nginx，避免把你现有站点一起弄挂
# ==========================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
SERVICE_NAME="food-baby"

#: 后端进程监听的端口（只在 127.0.0.1 上，不对外）
APP_PORT="${APP_PORT:-8801}"
#: Nginx 对外提供的端口。
#: 默认 8080 而不是 80 —— 80 很可能已经被服务器上原有网站占用，
#: 两个站点都监听 80 且都用 IP 访问是无法区分的（HTTP 没有 Host 就分不开）。
NGINX_PORT="${NGINX_PORT:-8080}"
#: systemd 服务运行用户
RUN_USER="${RUN_USER:-$(id -un)}"

info()  { printf '\033[1;35m[爱心小食堂]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[注意]\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] && SUDO="" || SUDO="sudo"

# 这两个不能一样，否则 Nginx 反代到自己形成死循环
if [[ "$NGINX_PORT" == "$APP_PORT" ]]; then
  die "NGINX_PORT (${NGINX_PORT}) 不能和 APP_PORT (${APP_PORT}) 相同"
fi

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
info "6/7 写入 Nginx 配置（独立端口 ${NGINX_PORT}，不影响已有站点）"

CONF_D="/etc/nginx/conf.d"
if [[ ! -d "$CONF_D" ]]; then
  # 有些 Nginx 把 conf.d 放在 sites-available/sites-enabled 体系里
  if [[ -d /etc/nginx/sites-available ]]; then
    CONF_D="/etc/nginx/sites-available"
    warn "没有 /etc/nginx/conf.d，改用 $CONF_D"
  else
    die "找不到 Nginx 配置目录，请确认 Nginx 装好了"
  fi
fi

CONF="$CONF_D/${SERVICE_NAME}.conf"
LINK="/etc/nginx/sites-enabled/${SERVICE_NAME}.conf"
BACKUP=""

# 先看看这个端口是不是已经被别的站点占了，占了就直接停手，别硬来
if command -v nginx >/dev/null 2>&1; then
  if $SUDO grep -rqsE "listen[[:space:]]+([0-9.\[\]:]*:)?${NGINX_PORT}([[:space:];]|$)" \
       /etc/nginx/sites-enabled "$CONF_D" 2>/dev/null; then
    warn "Nginx 里已经有站点在监听 ${NGINX_PORT} 端口了，为避免冲突先停在这里。"
    echo
    echo "  看看是谁占用的："
    $SUDO grep -rnsE "listen[[:space:]]+([0-9.\[\]:]*:)?${NGINX_PORT}([[:space:];]|$)" \
      /etc/nginx/sites-enabled "$CONF_D" 2>/dev/null | sed 's/^/    /' || true
    echo
    echo "  解决办法：换一个没人用的端口重跑，例如"
    echo "    NGINX_PORT=8090 ./deploy.sh"
    echo
    die "端口 ${NGINX_PORT} 被占用"
  fi
fi

# 备份旧配置，出问题好回滚（只备份自己的文件，不碰别人的）
if [[ -f "$CONF" ]]; then
  BACKUP="${CONF}.bak.$(date +%Y%m%d%H%M%S)"
  $SUDO cp "$CONF" "$BACKUP"
  info "已备份旧配置到 $BACKUP"
fi

$SUDO tee "$CONF" >/dev/null <<EOF
# ==========================================================================
# 爱心小食堂 (food-baby) —— 由 deploy.sh 自动生成
#
# 只监听 ${NGINX_PORT} 端口，且【不设 default_server】。
# 这样它不会抢占服务器上已有站点的默认虚拟主机，
# 现有网站继续在它自己的端口/域名上跑，互不影响。
#
# 想改端口：编辑这里，或者重新执行 NGINX_PORT=xxxx ./deploy.sh
# ==========================================================================

server {
    listen ${NGINX_PORT};
    listen [::]:${NGINX_PORT};
    server_name _;

    # 日志单独放，方便排查，也不会和别的站点混在一起
    access_log /var/log/nginx/${SERVICE_NAME}.access.log;
    error_log  /var/log/nginx/${SERVICE_NAME}.error.log;

    # 手机拍的照片可能十几 MB，放宽一点（后端还会自己压到长边 1200）
    client_max_body_size 20m;

    # 上传/压缩图片偶尔慢，给足超时
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;

    # 前端构建产物
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

    # 后端接口
    location /api/ {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # 接口文档（不想对外暴露就把这两段删掉）
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

# 如果 Nginx 用的是 sites-enabled 体系，需要建软链接才会生效
if [[ "$CONF_D" == "/etc/nginx/sites-available" ]]; then
  $SUDO ln -sfn "$CONF" "$LINK"
  info "已创建启用链接 $LINK"
fi

# ==========================================================================
# 7. 先起后端，确认活着，再动 Nginx
#    顺序很重要：后端没起来就别 reload Nginx，
#    否则你现有网站也可能跟着一起挂。
# ==========================================================================
info "7/7 启动后端服务并校验 Nginx"

$SUDO systemctl daemon-reload
$SUDO systemctl enable "${SERVICE_NAME}" >/dev/null
$SUDO systemctl restart "${SERVICE_NAME}"

# 等后端就绪（最多 30 秒）
BACKEND_OK=0
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null 2>&1; then
    BACKEND_OK=1
    break
  fi
  sleep 1
done

if [[ "$BACKEND_OK" != "1" ]]; then
  warn "后端在 ${APP_PORT} 端口没有就绪，Nginx 配置保持不动（不会影响你已有站点）"
  echo
  echo "  看看后端日志："
  $SUDO tail -n 30 "/var/log/${SERVICE_NAME}.err.log" 2>/dev/null | sed 's/^/    /' || true
  echo
  die "后端启动失败，请把上面的日志发我"
fi
info "后端已就绪：http://127.0.0.1:${APP_PORT}/api/health"

# 校验 Nginx 配置；不合法就回滚，绝不让它带着坏配置 reload
if ! $SUDO nginx -t 2>&1 | sed 's/^/  /'; then
  warn "nginx -t 校验失败，正在回滚这次的配置改动…"

  if [[ -n "$BACKUP" ]]; then
    $SUDO cp "$BACKUP" "$CONF"
    info "已恢复备份 $BACKUP"
    if $SUDO nginx -t >/dev/null 2>&1; then
      $SUDO systemctl reload nginx
      info "Nginx 已恢复原状，你现有站点不受影响"
    else
      warn "回滚后 nginx -t 仍不通过，请手动检查"
    fi
  else
    $SUDO rm -f "$CONF"
    [[ -n "${LINK:-}" ]] && $SUDO rm -f "$LINK"
    info "已移除本次新增的配置"
    if $SUDO nginx -t >/dev/null 2>&1; then
      $SUDO systemctl reload nginx
      info "Nginx 已恢复原状，你现有站点不受影响"
    fi
  fi

  echo
  die "Nginx 配置没通过校验。最常见的原因是 ${NGINX_PORT} 端口被占用，换个端口重试：NGINX_PORT=8090 ./deploy.sh"
fi

$SUDO systemctl reload nginx
$SUDO systemctl enable nginx >/dev/null 2>&1 || true

# 通过 Nginx 再验一次整条链路
sleep 1
if curl -fsS "http://127.0.0.1:${NGINX_PORT}/api/health" >/dev/null 2>&1; then
  info "经 Nginx 访问接口正常"
else
  warn "Nginx 已 reload，但通过 ${NGINX_PORT} 端口访问接口失败，检查 Nginx 日志："
  warn "  sudo tail -f /var/log/nginx/${SERVICE_NAME}.error.log"
fi

# 如果服务器上用了 ufw 且没放行这个端口，顺手提示（不自动改，怕动到你的规则）
if command -v ufw >/dev/null 2>&1; then
  if ! $SUDO ufw status 2>/dev/null | grep -q "${NGINX_PORT}"; then
    warn "ufw 似乎没放行 ${NGINX_PORT} 端口。需要的话执行：sudo ufw allow ${NGINX_PORT}/tcp"
  fi
fi

echo
info "部署完成 ♥（没有动过服务器上其它站点的任何配置）"
echo
echo "  后端服务状态：  sudo systemctl status ${SERVICE_NAME}"
echo "  后端日志：      sudo tail -f /var/log/${SERVICE_NAME}.log"
echo "  后端错误日志：  sudo tail -f /var/log/${SERVICE_NAME}.err.log"
echo "  Nginx 日志：    sudo tail -f /var/log/nginx/${SERVICE_NAME}.error.log"
echo "  本次写入的配置：$CONF"
echo
warn "还差两步才能真正访问："
warn "  1. 阿里云安全组放行 ${NGINX_PORT} 端口（入方向 TCP）"
warn "  2. 云服务器系统防火墙如果开了，也要放行（ufw allow ${NGINX_PORT}/tcp）"
echo
echo "  点菜页：        http://<你的公网IP>:${NGINX_PORT}/"
echo "  管理后台：      http://<你的公网IP>:${NGINX_PORT}/admin/login"
echo "  默认账号密码：  见 backend/.env 里的 ADMIN_USERNAME / ADMIN_PASSWORD"
echo
warn "登录后台后请立刻到「账号」页修改密码。"
echo
echo "  服务器本机自检：curl -s http://127.0.0.1:${NGINX_PORT}/api/health"
echo
