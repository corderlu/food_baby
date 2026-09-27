/** 时间格式化。后端返回的都是带 +08:00 的 ISO 字符串。 */

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

const pad = (n: number) => String(n).padStart(2, '0')

/** HH:MM */
export function hhmm(iso: string | null | undefined): string {
  const d = parse(iso)
  if (!d) return '--:--'
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** MM月DD日 HH:MM */
export function monthDayTime(iso: string | null | undefined): string {
  const d = parse(iso)
  if (!d) return ''
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hhmm(iso)}`
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/** 智能时间：今天只显示时间，昨天显示"昨天 HH:MM"，更早显示"MM月DD日 HH:MM" */
export function smartTime(iso: string | null | undefined): string {
  const d = parse(iso)
  if (!d) return ''
  const now = new Date()

  if (isSameDay(d, now)) {
    const diffMin = Math.floor((now.getTime() - d.getTime()) / 60000)
    if (diffMin < 1) return '刚刚'
    if (diffMin < 60) return `${diffMin} 分钟前`
    return `今天 ${hhmm(iso)}`
  }

  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (isSameDay(d, yesterday)) return `昨天 ${hhmm(iso)}`

  const yearPart = d.getFullYear() === now.getFullYear() ? '' : `${d.getFullYear()}年`
  return `${yearPart}${d.getMonth() + 1}月${d.getDate()}日 ${hhmm(iso)}`
}

/** 完整时间：YYYY-MM-DD HH:MM */
export function fullTime(iso: string | null | undefined): string {
  const d = parse(iso)
  if (!d) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hhmm(iso)}`
}

/** 星期几 */
export function weekday(iso: string | null | undefined): string {
  const d = parse(iso)
  return d ? WEEKDAYS[d.getDay()] : ''
}

/** 已过去多久，用于后台"这单挂了 40 分钟" */
export function elapsedText(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return ''
  const m = Math.max(0, Math.round(minutes))
  if (m < 1) return '刚刚下的'
  if (m < 60) return `已放置 ${m} 分钟`
  const h = Math.floor(m / 60)
  const rest = m % 60
  return rest ? `已放置 ${h} 小时 ${rest} 分` : `已放置 ${h} 小时`
}

/** 把 HH:MM 或 "18:30" 规范化显示 */
export function expectedTimeText(value: string | null | undefined): string {
  if (!value) return ''
  const parts = String(value).split(':')
  if (parts.length < 2) return String(value)
  return `${parts[0].padStart(2, '0')}:${parts[1].padStart(2, '0')}`
}

/** 当前时间 HH:MM，用于"期望用餐时间"的默认值 */
export function currentHHMM(offsetMinutes = 30): string {
  const d = new Date(Date.now() + offsetMinutes * 60000)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 今天日期，形如 2026年9月27日 周日 */
export function todayText(): string {
  const d = new Date()
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${WEEKDAYS[d.getDay()]}`
}
