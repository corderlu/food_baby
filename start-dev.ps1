# ==========================================================================
# 爱心小食堂 · Windows 本地一键启动（开发用）
#
# 同时开两个窗口：后端 8801 + 前端 5273，然后用手机连局域网 IP 就能真机预览。
#
# 用法（在项目根目录右键「在终端中打开」，或 PowerShell 里执行）：
#   .\start-dev.ps1
# ==========================================================================

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot

Write-Host ""
Write-Host "  ♥ 爱心小食堂 · 本地开发启动" -ForegroundColor Magenta
Write-Host "  ================================" -ForegroundColor Magenta
Write-Host ""

# ---- 检查环境 ----
$py = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host "  没找到后端虚拟环境，先执行：" -ForegroundColor Yellow
    Write-Host "    cd backend" -ForegroundColor White
    Write-Host "    python -m venv .venv" -ForegroundColor White
    Write-Host "    .\.venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor White
    exit 1
}

if (-not (Test-Path (Join-Path $Root 'backend\.env'))) {
    Copy-Item (Join-Path $Root 'backend\.env.example') (Join-Path $Root 'backend\.env')
    Write-Host "  已从 .env.example 生成 backend\.env" -ForegroundColor Yellow
}

if (-not (Test-Path (Join-Path $Root 'frontend\node_modules'))) {
    Write-Host "  前端依赖还没装，请先执行：cd frontend; pnpm install" -ForegroundColor Yellow
    exit 1
}

# ---- 找局域网 IP，方便手机访问 ----
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -First 1 -ExpandProperty IPAddress)

Write-Host "  后端：http://127.0.0.1:8801    (接口文档 /docs)" -ForegroundColor Cyan
Write-Host "  前端：http://127.0.0.1:5273" -ForegroundColor Cyan
if ($lanIp) {
    Write-Host ""
    Write-Host "  手机真机预览（连同一个 Wi-Fi）：" -ForegroundColor Green
    Write-Host "    点菜页：    http://${lanIp}:5273/" -ForegroundColor Green
    Write-Host "    管理后台：  http://${lanIp}:5273/admin/login" -ForegroundColor Green
}
Write-Host ""
Write-Host "  按 Ctrl+C 或关掉这两个窗口即可停止" -ForegroundColor DarkGray
Write-Host ""

# ---- 启动后端 ----
Start-Process -FilePath 'powershell' -ArgumentList @(
    '-NoExit', '-Command',
    "`$host.UI.RawUI.WindowTitle = '爱心小食堂 · 后端 8801'; Set-Location '$Root\backend'; & '$py' -m uvicorn app.main:app --host 0.0.0.0 --port 8801 --reload"
)

Start-Sleep -Seconds 2

# ---- 启动前端 ----
Start-Process -FilePath 'powershell' -ArgumentList @(
    '-NoExit', '-Command',
    "`$host.UI.RawUI.WindowTitle = '爱心小食堂 · 前端 5273'; Set-Location '$Root\frontend'; pnpm run dev"
)

Write-Host "  两个窗口已经开起来了 ♥" -ForegroundColor Magenta
Write-Host ""
