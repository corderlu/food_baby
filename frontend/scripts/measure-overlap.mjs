/**
 * 验证「有底部操作条 + 底部导航」的三个页面都不互相遮挡：
 *   1. /admin/settings  —— 保存设置条
 *   2. /cart            —— 提交订单条（带购物车数据）
 *   3. /               —— 去下单条（菜单页）
 *
 * 纯验证脚本。用法（需要先启动前后端 + 远程调试的浏览器）：
 *   node scripts/measure-overlap.mjs <debugPort> [页面]
 * 不带页面参数时依次检查全部三个。
 */

const PORT = process.argv[2] || '9222'
const BASE = 'http://127.0.0.1:5273'
const ONLY = process.argv[3]
const VIEWPORT = { width: 390, height: 844, deviceScaleFactor: 2, mobile: true }

const PAGES = [
  { key: 'settings', url: '/admin/settings', bar: '.savebar', label: '店铺设置' },
  { key: 'cart', url: '/cart', bar: '.actionbar', label: '购物车' },
  { key: 'menu', url: '/', bar: '.actionbar', label: '点菜首页' },
]

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class Session {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        if (msg.error) reject(new Error(JSON.stringify(msg.error)))
        else resolve(msg.result)
      }
    })
  }
  send(method, params = {}) {
    const id = ++this.id
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }
}

async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl)
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true })
    ws.addEventListener('error', reject, { once: true })
  })
  return new Session(ws)
}

async function evaluate(session, expression) {
  const r = await session.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval failed')
  return r.result.value
}

const PROBE = (barSelector) => `(() => {
  const q = (s) => document.querySelector(s);
  const tabbar = q('.van-tabbar');
  const bar = q(${JSON.stringify(barSelector)});
  if (!tabbar) return { error: '找不到 van-tabbar' };
  if (!bar) return { note: '这个页面当前没有操作条（例如购物车为空）' };
  const t = tabbar.getBoundingClientRect();
  const b = bar.getBoundingClientRect();
  return {
    barClass: bar.className,
    barPosition: getComputedStyle(bar).position,
    tabbarTop: Math.round(t.top),
    barBottom: Math.round(b.bottom),
    barTop: Math.round(b.top),
    overlapPx: Math.round(b.bottom - t.top),
    gapPx: Math.round(t.top - b.bottom),
    viewportH: window.innerHeight,
    barFullyVisible: b.top >= 0 && b.bottom <= window.innerHeight + 1,
    tabs: [...document.querySelectorAll('.van-tabbar-item')].map((el) => {
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { text: el.innerText.trim(), clickable: Boolean(hit && el.contains(hit)) };
    }),
  };
})()`

async function main() {
  const login = await fetch(`${BASE}/api/admin/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  }).then((r) => r.json())
  if (!login.access_token) throw new Error('登录失败')

  const pages = ONLY ? PAGES.filter((p) => p.key === ONLY) : PAGES
  const targets = await fetch(`http://127.0.0.1:${PORT}/json/list`).then((r) => r.json())
  const page = targets.find((t) => t.type === 'page')
  if (!page) throw new Error('没有 page target')
  const session = await connect(page.webSocketDebuggerUrl)
  await session.send('Page.enable')
  await session.send('Runtime.enable')
  await session.send('Emulation.setDeviceMetricsOverride', VIEWPORT)

  await session.send('Page.navigate', { url: `${BASE}/` })
  await sleep(2500)
  await evaluate(session, `localStorage.setItem('food_baby_token', ${JSON.stringify(login.access_token)}); 'ok'`)

  // 往购物车塞两道菜，这样 /cart 和首页才会出现操作条
  await evaluate(
    session,
    `(() => {
       const menu = ${JSON.stringify(null)};
       localStorage.setItem('food_baby_cart_v1', JSON.stringify({
         lines: [{ dish_id: 1, quantity: 2, item_note: '少放盐' }, { dish_id: 5, quantity: 1, item_note: '' }],
         note: '', dishRequest: '', expectedTime: '18:30'
       }));
       return 'ok';
     })()`,
  )

  const ok = []
  const bad = []

  for (const p of pages) {
    await session.send('Page.navigate', { url: BASE + p.url })
    await sleep(3800)
    const report = await evaluate(session, PROBE(p.bar))
    console.log(`\n  ---- ${p.label} (${p.url}) ----`)
    console.log('  ' + JSON.stringify(report))

    if (report.error) {
      bad.push(`${p.label}: ${report.error}`)
      continue
    }
    if (report.note) {
      console.log(`  [SKIP] ${p.label}: ${report.note}`)
      continue
    }

    const push = (name, cond, extra) => {
      const line = `${p.label} · ${name}${extra ? ' :: ' + extra : ''}`
      ;(cond ? ok : bad).push(line)
    }
    push('操作条不遮住导航', report.overlapPx <= 1, `overlap=${report.overlapPx}px`)
    push('无明显缝隙', Math.abs(report.gapPx) <= 1, `gap=${report.gapPx}px`)
    push('操作条完整可见', report.barFullyVisible, `top=${report.barTop} bottom=${report.barBottom}`)
    push(
      '所有 tab 可点击',
      report.tabs.every((t) => t.clickable),
      JSON.stringify(report.tabs),
    )

    const shot = await session.send('Page.captureScreenshot', { format: 'png' })
    const fs = await import('node:fs')
    fs.writeFileSync(`scripts/_shot-${p.key}.png`, Buffer.from(shot.data, 'base64'))
  }

  console.log('\n  ====================================')
  console.log(`  通过 ${ok.length} 项，失败 ${bad.length} 项`)
  ok.forEach((s) => console.log('  [OK]   ' + s))
  bad.forEach((s) => console.log('  [FAIL] ' + s))
  console.log('  ====================================')

  session.ws.close()
  process.exit(bad.length ? 1 : 0)
}

main().catch((e) => {
  console.error('验证失败：', e.message)
  process.exit(2)
})
