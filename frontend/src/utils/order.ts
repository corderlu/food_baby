/** 订单状态相关的元数据。 */

import type { OrderStatus } from '@/types/api'

export interface StatusMeta {
  label: string
  color: string
  emoji: string
  hint: string
}

export const STATUS_META: Record<OrderStatus, StatusMeta> = {
  pending: {
    label: '待接单',
    color: 'var(--s-pending)',
    emoji: '📨',
    hint: '主厨还没看到，稍等一下下～',
  },
  accepted: {
    label: '已接单',
    color: 'var(--s-accepted)',
    emoji: '👌',
    hint: '主厨接单啦，马上就动手',
  },
  preparing: {
    label: '备菜中',
    color: 'var(--s-preparing)',
    emoji: '🔪',
    hint: '正在洗菜切菜，材料准备中',
  },
  cooking: {
    label: '烹饪中',
    color: 'var(--s-cooking)',
    emoji: '🍳',
    hint: '下锅啦！香味已经出来了',
  },
  served: {
    label: '出餐完成',
    color: 'var(--s-served)',
    emoji: '🍽️',
    hint: '可以吃啦，快来！',
  },
  cancelled: {
    label: '已取消',
    color: 'var(--s-cancelled)',
    emoji: '💤',
    hint: '这单已经取消了',
  },
}

export const FLOW: OrderStatus[] = ['pending', 'accepted', 'preparing', 'cooking', 'served']

export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status as OrderStatus] ?? STATUS_META.pending
}

export function flowIndex(status: string): number {
  const i = FLOW.indexOf(status as OrderStatus)
  return i < 0 ? 0 : i
}

export function isDone(status: string): boolean {
  return status === 'served' || status === 'cancelled'
}

/** 后台"下一步"按钮的文案 */
export function nextActionLabel(next: string | null): string {
  switch (next) {
    case 'accepted':
      return '接单'
    case 'preparing':
      return '开始备菜'
    case 'cooking':
      return '下锅烹饪'
    case 'served':
      return '出餐完成'
    default:
      return '推进状态'
  }
}

export function nextActionIcon(next: string | null): string {
  switch (next) {
    case 'accepted':
      return '✅'
    case 'preparing':
      return '🔪'
    case 'cooking':
      return '🍳'
    case 'served':
      return '🍽️'
    default:
      return '➡️'
  }
}
