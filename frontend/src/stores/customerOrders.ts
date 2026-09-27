/**
 * 顾客端订单。
 *
 * 她不需要注册登录，所以"我的订单"靠本机 localStorage 记订单号。
 * 换手机 / 清了浏览器数据就看不到了 —— 这是明确的取舍，
 * 详情页支持手动输入订单号找回。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '@/api/customer'
import type { Order } from '@/types/api'

const HISTORY_KEY = 'food_baby_order_history_v1'
const SEEN_KEY = 'food_baby_order_seen_v1'
const MAX_HISTORY = 60

interface HistoryEntry {
  order_no: string
  created_at: string
}

function readHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (e): e is HistoryEntry =>
          typeof e === 'object' && e !== null && typeof (e as HistoryEntry).order_no === 'string',
      )
      .map((e) => ({
        order_no: String(e.order_no),
        created_at: String(e.created_at || ''),
      }))
      .slice(0, MAX_HISTORY)
  } catch {
    return []
  }
}

function readSeen(): Record<string, string> {
  try {
    const raw = localStorage.getItem(SEEN_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, string>) : {}
  } catch {
    return {}
  }
}

export const useCustomerOrderStore = defineStore('customerOrders', () => {
  const history = ref<HistoryEntry[]>(readHistory())
  const orders = ref<Order[]>([])
  /** order_no -> 上次看到的状态，用来判断"状态变了，给她一个提示" */
  const seenStatus = ref<Record<string, string>>(readSeen())
  const loading = ref(false)
  const activeOrder = ref<Order | null>(null)

  const orderNos = computed(() => history.value.map((h) => h.order_no))

  function persistHistory(): void {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value.slice(0, MAX_HISTORY)))
    } catch {
      /* 忽略 */
    }
  }

  function persistSeen(): void {
    try {
      localStorage.setItem(SEEN_KEY, JSON.stringify(seenStatus.value))
    } catch {
      /* 忽略 */
    }
  }

  function remember(order: Order): void {
    if (!order?.order_no) return
    const rest = history.value.filter((h) => h.order_no !== order.order_no)
    history.value = [
      { order_no: order.order_no, created_at: order.created_at || '' },
      ...rest,
    ].slice(0, MAX_HISTORY)
    persistHistory()
  }

  function forget(orderNo: string): void {
    history.value = history.value.filter((h) => h.order_no !== orderNo)
    persistHistory()
  }

  function markSeen(order: Order): void {
    if (!order?.order_no) return
    seenStatus.value = { ...seenStatus.value, [order.order_no]: order.status }
    persistSeen()
  }

  /** 状态相比上次有没有变化（详情页用来做"主厨更新啦"的小提示） */
  function hasStatusChanged(order: Order): boolean {
    const prev = seenStatus.value[order.order_no]
    return Boolean(prev) && prev !== order.status
  }

  async function refreshActive(): Promise<void> {
    activeOrder.value = await api.fetchActiveOrder()
  }

  async function loadHistoryOrders(): Promise<void> {
    if (!orderNos.value.length) {
      orders.value = []
      return
    }
    loading.value = true
    try {
      orders.value = await api.queryOrders(orderNos.value)
    } finally {
      loading.value = false
    }
  }

  /** 详情页轮询：只更新这一单，顺便刷新本机历史里的时间 */
  async function pollOrder(orderNo: string): Promise<Order> {
    const order = await api.fetchOrder(orderNo)
    const idx = orders.value.findIndex((o) => o.order_no === orderNo)
    if (idx >= 0) orders.value[idx] = order
    return order
  }

  return {
    history,
    orders,
    seenStatus,
    loading,
    activeOrder,
    orderNos,
    remember,
    forget,
    markSeen,
    hasStatusChanged,
    refreshActive,
    loadHistoryOrders,
    pollOrder,
  }
})
