/**
 * 购物车。
 *
 * 存 localStorage：她点了一半切出去看微信，回来东西还在。
 * 只存 dish_id + 数量 + 单项备注，菜品的名字/图片每次从菜单接口补，
 * 这样你在后台改了菜名或换了图，她那边刷新就能看到最新的。
 */
import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { CartLine, Dish, OrderItemInput } from '@/types/api'

const STORAGE_KEY = 'food_baby_cart_v1'

interface PersistedCart {
  lines: Array<{ dish_id: number; quantity: number; item_note: string }>
  note: string
  dishRequest: string
  expectedTime: string
}

interface Snapshot {
  dish_id: number
  quantity: number
  item_note: string
}

function load(): PersistedCart {
  const fallback: PersistedCart = { lines: [], note: '', dishRequest: '', expectedTime: '' }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<PersistedCart>
    const lines = Array.isArray(parsed.lines) ? parsed.lines : []
    return {
      lines: lines
        .filter((l) => typeof l?.dish_id === 'number' && l.dish_id > 0)
        .map((l) => ({
          dish_id: Number(l.dish_id),
          quantity: Math.min(99, Math.max(1, Number(l.quantity) || 1)),
          item_note: String(l.item_note || '').slice(0, 100),
        })),
      note: String(parsed.note || '').slice(0, 200),
      dishRequest: String(parsed.dishRequest || '').slice(0, 200),
      expectedTime: String(parsed.expectedTime || ''),
    }
  } catch {
    return fallback
  }
}

export const useCartStore = defineStore('cart', () => {
  const persisted = load()

  /** 只存快照，展示信息通过 attach() 从菜单补全 */
  const snapshot = ref<Snapshot[]>(persisted.lines)
  const note = ref(persisted.note)
  const dishRequest = ref(persisted.dishRequest)
  const expectedTime = ref(persisted.expectedTime)
  /** dish_id -> 菜单里的菜品，由菜单页写入 */
  const dishMap = ref<Record<number, Dish>>({})

  const lines = computed<CartLine[]>(() =>
    snapshot.value.map((s) => {
      const dish = dishMap.value[s.dish_id]
      return {
        dish_id: s.dish_id,
        quantity: s.quantity,
        item_note: s.item_note,
        name: dish?.name ?? `已下架的菜（#${s.dish_id}）`,
        image_url: dish?.image_url ?? '',
        category: dish?.category ?? '',
      }
    }),
  )

  const totalCount = computed(() => snapshot.value.reduce((sum, s) => sum + s.quantity, 0))
  const lineCount = computed(() => snapshot.value.length)
  const isEmpty = computed(() => snapshot.value.length === 0)

  /** 有没有菜品已经在后台下架（提交前用来提示她） */
  const missingDishIds = computed(() =>
    snapshot.value.filter((s) => !dishMap.value[s.dish_id]).map((s) => s.dish_id),
  )

  const estimatedMinutes = computed(() =>
    snapshot.value.reduce((max, s) => {
      const d = dishMap.value[s.dish_id]
      return d ? Math.max(max, d.estimated_minutes) : max
    }, 0),
  )

  function persist(): void {
    const payload: PersistedCart = {
      lines: snapshot.value,
      note: note.value,
      dishRequest: dishRequest.value,
      expectedTime: expectedTime.value,
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      /* 隐私模式下可能写不进去，忽略 */
    }
  }

  watch([snapshot, note, dishRequest, expectedTime], persist, { deep: true })

  /** 菜单页加载后调用，补全展示信息并清理已下架的菜 */
  function attach(dishes: Dish[], pruneMissing = false): void {
    const map: Record<number, Dish> = { ...dishMap.value }
    for (const d of dishes) map[d.id] = d
    dishMap.value = map

    if (pruneMissing) {
      snapshot.value = snapshot.value.filter((s) => Boolean(map[s.dish_id]))
    } else {
      // 已经在购物车里、但现在已下架的菜，直接从购物车移除
      snapshot.value = snapshot.value.filter((s) => {
        const d = map[s.dish_id]
        return !d || d.is_available
      })
    }
  }

  function quantityOf(dishId: number): number {
    return snapshot.value.find((s) => s.dish_id === dishId)?.quantity ?? 0
  }

  function add(dish: Dish, quantity = 1): void {
    const found = snapshot.value.find((s) => s.dish_id === dish.id)
    if (found) {
      found.quantity = Math.min(99, found.quantity + quantity)
    } else {
      snapshot.value.push({ dish_id: dish.id, quantity: Math.min(99, quantity), item_note: '' })
    }
  }

  function setQuantity(dishId: number, quantity: number): void {
    if (quantity <= 0) {
      remove(dishId)
      return
    }
    const found = snapshot.value.find((s) => s.dish_id === dishId)
    if (found) found.quantity = Math.min(99, quantity)
  }

  function increase(dishId: number): void {
    setQuantity(dishId, quantityOf(dishId) + 1)
  }

  function decrease(dishId: number): void {
    setQuantity(dishId, quantityOf(dishId) - 1)
  }

  function remove(dishId: number): void {
    snapshot.value = snapshot.value.filter((s) => s.dish_id !== dishId)
  }

  function setItemNote(dishId: number, text: string): void {
    const found = snapshot.value.find((s) => s.dish_id === dishId)
    if (found) found.item_note = text.slice(0, 100)
  }

  function clear(): void {
    snapshot.value = []
    note.value = ''
    dishRequest.value = ''
    expectedTime.value = ''
  }

  /** 清空菜品但保留备注（下单成功后调用） */
  function clearDishes(): void {
    snapshot.value = []
  }

  function toOrderItems(): OrderItemInput[] {
    return snapshot.value.map((s) => ({
      dish_id: s.dish_id,
      quantity: s.quantity,
      item_note: s.item_note,
    }))
  }

  return {
    snapshot,
    lines,
    note,
    dishRequest,
    expectedTime,
    totalCount,
    lineCount,
    isEmpty,
    missingDishIds,
    estimatedMinutes,
    attach,
    quantityOf,
    add,
    setQuantity,
    increase,
    decrease,
    remove,
    setItemNote,
    clear,
    clearDishes,
    toOrderItems,
  }
})
