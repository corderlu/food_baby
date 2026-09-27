/** 顾客端接口（无需登录）。 */
import { http } from './http'
import type {
  MenuPayload,
  Order,
  OrderCreateInput,
  OrderModifyInput,
  OrderStatusMeta,
  ShopPayload,
} from '@/types/api'

export async function fetchShop(): Promise<ShopPayload> {
  const { data } = await http.get<ShopPayload>('/shop')
  return data
}

export async function fetchMenu(): Promise<MenuPayload> {
  const { data } = await http.get<MenuPayload>('/menu')
  return data
}

export async function fetchStatuses(): Promise<OrderStatusMeta> {
  const { data } = await http.get<OrderStatusMeta>('/orders/statuses')
  return data
}

export async function fetchActiveOrder(): Promise<Order | null> {
  const { data } = await http.get<{ order: Order | null }>('/orders/active')
  return data.order
}

export async function createOrder(
  payload: OrderCreateInput,
): Promise<{ order: Order; message?: string }> {
  const { data } = await http.post<{ order: Order; message?: string }>('/orders', payload)
  return data
}

export async function fetchOrder(orderNo: string): Promise<Order> {
  const { data } = await http.get<{ order: Order }>(`/orders/${encodeURIComponent(orderNo)}`)
  return data.order
}

export async function queryOrders(orderNos: string[]): Promise<Order[]> {
  if (!orderNos.length) return []
  const { data } = await http.post<{ orders: Order[] }>('/orders/query', {
    order_nos: orderNos,
  })
  return data.orders
}

export async function modifyOrder(
  orderNo: string,
  payload: OrderModifyInput,
): Promise<{ order: Order; message?: string }> {
  const { data } = await http.patch<{ order: Order; message?: string }>(
    `/orders/${encodeURIComponent(orderNo)}`,
    payload,
  )
  return data
}

export async function cancelOrder(orderNo: string): Promise<{ order: Order; message?: string }> {
  const { data } = await http.post<{ order: Order; message?: string }>(
    `/orders/${encodeURIComponent(orderNo)}/cancel`,
  )
  return data
}

export function uploadUrl(url: string): string {
  return url || ''
}
