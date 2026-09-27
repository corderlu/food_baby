/**
 * 提示音：用 Web Audio 现场合成，不依赖任何 mp3 文件。
 *
 * 为什么这么做：
 * 1. 部署时少一个静态资源，也不会因为文件 404 而"没声音"。
 * 2. 浏览器要求用户交互后才能播放声音，所以需要 unlock()，
 *    由"开启提示音"按钮触发一次。
 * 3. HTTP（非 HTTPS）环境下 Web Audio 依然可用，比 Service Worker 靠谱。
 */

let ctx: AudioContext | null = null
let unlocked = false

type Ctor = typeof AudioContext

function getCtor(): Ctor | null {
  const w = window as unknown as { AudioContext?: Ctor; webkitAudioContext?: Ctor }
  return w.AudioContext || w.webkitAudioContext || null
}

export function isSupported(): boolean {
  return getCtor() !== null
}

export function isUnlocked(): boolean {
  return unlocked
}

/** 必须在用户点击的回调里调用一次，否则后续自动播放会被浏览器拦截。 */
export async function unlock(): Promise<boolean> {
  const Ctor = getCtor()
  if (!Ctor) return false
  try {
    if (!ctx) ctx = new Ctor()
    if (ctx.state === 'suspended') await ctx.resume()
    // 播放一个听不见的极短音，彻底激活音频上下文
    const gain = ctx.createGain()
    gain.gain.value = 0.0001
    const osc = ctx.createOscillator()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.01)
    unlocked = ctx.state === 'running'
    return unlocked
  } catch {
    return false
  }
}

function beep(
  freq: number,
  startAt: number,
  duration: number,
  volume: number,
  type: OscillatorType = 'sine',
): void {
  if (!ctx) return
  const t0 = ctx.currentTime + startAt

  const osc = ctx.createOscillator()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t0)

  const gain = ctx.createGain()
  // 快起慢落，像小铃铛
  gain.gain.setValueAtTime(0.0001, t0)
  gain.gain.exponentialRampToValueAtTime(volume, t0 + 0.012)
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration)

  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(t0)
  osc.stop(t0 + duration + 0.05)
}

/** 新订单：叮——咚（上行三度，明亮一点） */
export function playNewOrder(): void {
  if (!ctx || ctx.state !== 'running') return
  beep(988, 0, 0.42, 0.3) // B5
  beep(1319, 0.17, 0.5, 0.24) // E6
  beep(1568, 0.34, 0.6, 0.16) // G6 泛音
}

/** 顾客改单：两声短促的嘟（比新订单轻，避免和"新单"混淆） */
export function playModified(): void {
  if (!ctx || ctx.state !== 'running') return
  beep(880, 0, 0.18, 0.22) // A5
  beep(880, 0.24, 0.18, 0.22)
}

/** 一次"新单 + 改单"都有时的组合提示 */
export function playMixed(): void {
  if (!ctx || ctx.state !== 'running') return
  playModified()
  beep(988, 0.5, 0.42, 0.3)
  beep(1319, 0.67, 0.5, 0.24)
}

/* --------------------------------------------------------------------------
   页面标题闪烁（不需要任何权限，最可靠的"提醒"）
   -------------------------------------------------------------------------- */

const ORIGINAL_TITLE = '爱心小食堂'
let flashTimer: number | null = null
let flashOn = false

export function startTitleFlash(text = '🔔 有新订单！'): void {
  if (flashTimer !== null) return
  flashOn = true
  flashTimer = window.setInterval(() => {
    document.title = flashOn ? text : ORIGINAL_TITLE
    flashOn = !flashOn
  }, 900)
}

export function stopTitleFlash(): void {
  if (flashTimer !== null) {
    window.clearInterval(flashTimer)
    flashTimer = null
  }
  flashOn = false
  document.title = ORIGINAL_TITLE
}

/** 手机震动（部分安卓浏览器支持，iOS Safari 不支持，失败就算了） */
export function vibrate(pattern: number | number[] = [200, 100, 200]): void {
  try {
    if ('vibrate' in navigator) navigator.vibrate(pattern)
  } catch {
    /* 忽略 */
  }
}
