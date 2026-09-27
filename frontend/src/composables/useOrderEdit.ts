/**
 * 顾客改单逻辑。
 *
 * 后端接受的是「增量」语义（add / remove），所以这里维护"目标数量"，
 * 提交时和目标对比，算出真正要加多少、减多少。
 * 放在 composable 里而不是组件里，是因为这块状态机最容易被改坏，
 * 单独一个文件便于测试和复用。
 */
import { computed, ref, type Ref } from 'vue'
import { showToast } from 'vant'
import * as api from '@/api/customer'
import { useShopStore } from '@/stores/shop'
import type { Dish, Order, OrderItemInput } from '@/types/api'

export interface EditLine {
  dish_id: number
  name: string
  original: number
  target: number
}

export function useOrderEdit(order: Ref<Order | null>, onSaved?: () => void) {
  const shop = useShopStore()

  const visible = ref(false)
  const saving = ref(false)
  const note = ref('')
  const dishRequest = ref('')
  const lines = ref<EditLine[]>([])
  const addedQty = ref<Record<number, number>>({})

  /** 菜单里可以加的菜（排除已经在订单里的） */
  const addableDishes = computed<Dish[]>(() => {
    const inOrder = new Set(lines.value.map((l) => l.dish_id))
    return shop.dishes.filter((d) => d.is_available && !inOrder.has(d.id))
  })

  function open(): void {
    const o = order.value
    if (!o) return
    note.value = o.customer_note || ''
    dishRequest.value = o.dish_request || ''
    lines.value = o.items
      .filter((i) => i.dish_id !== null)
      .map((i) => ({
        dish_id: i.dish_id as number,
        name: i.dish_name,
        original: i.quantity,
        target: i.quantity,
      }))
    addedQty.value = {}
    visible.value = true
  }

  function close(): void {
    visible.value = false
  }

  function findLine(dishId: number): EditLine | undefined {
    return lines.value.find((l) => l.dish_id === dishId)
  }

  function increase(dishId: number): void {
    const line = findLine(dishId)
    if (line) line.target = Math.min(99, line.target + 1)
  }

  function decrease(dishId: number): void {
    const line = findLine(dishId)
    if (line) line.target = Math.max(0, line.target - 1)
  }

  function addQty(dishId: number): number {
    return addedQty.value[dishId] ?? 0
  }

  function addDish(dishId: number): void {
    addedQty.value = { ...addedQty.value, [dishId]: Math.min(99, addQty(dishId) + 1) }
  }

  function removeAdded(dishId: number): void {
    const next = Math.max(0, addQty(dishId) - 1)
    const copy = { ...addedQty.value }
    if (next === 0) delete copy[dishId]
    else copy[dishId] = next
    addedQty.value = copy
  }

  /** 目标数量变成 0 的菜会被移除，所以最终的菜品总数不能为 0 */
  const finalCount = computed(() => {
    const kept = lines.value.reduce((sum, l) => sum + l.target, 0)
    const added = Object.values(addedQty.value).reduce((a, b) => a + b, 0)
    return kept + added
  })

  const dirty = computed(() => {
    const o = order.value
    if (!o) return false
    if (note.value !== (o.customer_note || '')) return true
    if (dishRequest.value !== (o.dish_request || '')) return true
    if (lines.value.some((l) => l.target !== l.original)) return true
    if (Object.keys(addedQty.value).length > 0) return true
    return false
  })

  const summary = computed(() => {
    if (!dirty.value) return '还没改什么'
    const parts: string[] = []
    const clearedCount = lines.value.filter((l) => l.target === 0).length
    if (clearedCount) parts.push(`去掉 ${clearedCount} 道`)

    const increased = lines.value.filter((l) => l.target > l.original)
    const inc = increased.reduce((s, l) => s + (l.target - l.original), 0)
    const addTotal = Object.values(addedQty.value).reduce((a, b) => a + b, 0)
    if (inc + addTotal > 0) parts.push(`增加 ${inc + addTotal} 份`)

    const dec = lines.value
      .filter((l) => l.target > 0 && l.target < l.original)
      .reduce((s, l) => s + (l.original - l.target), 0)
    if (dec > 0) parts.push(`减少 ${dec} 份`)

    if (!parts.length) parts.push('修改备注/许愿')
    return `共 ${finalCount.value} 份 · ${parts.join('、')}`
  })

  async function save(): Promise<void> {
    const o = order.value
    if (!o || saving.value) return

    if (finalCount.value <= 0) {
      showToast('菜不能全去掉，想取消请用「取消订单」')
      return
    }

    const add: OrderItemInput[] = []
    const remove: OrderItemInput[] = []

    for (const line of lines.value) {
      if (line.target > line.original) {
        add.push({ dish_id: line.dish_id, quantity: line.target - line.original })
      } else if (line.target < line.original) {
        remove.push({ dish_id: line.dish_id, quantity: line.original - line.target })
      }
    }
    for (const [id, qty] of Object.entries(addedQty.value)) {
      if (qty > 0) add.push({ dish_id: Number(id), quantity: qty })
    }

    saving.value = true
    try {
      const result = await api.modifyOrder(o.order_no, {
        add,
        remove,
        customer_note: note.value,
        dish_request: dishRequest.value,
      })
      order.value = result.order
      showToast(result.message || '改好啦')
      visible.value = false
      onSaved?.()
    } catch (e) {
      showToast(e instanceof Error ? e.message : '改单失败')
    } finally {
      saving.value = false
    }
  }

  return {
    visible,
    saving,
    note,
    dishRequest,
    lines,
    addedQty,
    addableDishes,
    finalCount,
    dirty,
    summary,
    open,
    close,
    increase,
    decrease,
    addQty,
    addDish,
    removeAdded,
    save,
  }
}
