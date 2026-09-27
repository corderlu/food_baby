/** 管理端接口（需要 Bearer Token）。 */
import { http } from './http'
import type {
  AdminInfo,
  AdminOrderList,
  AdminOverview,
  Dish,
  DishInput,
  DishListResult,
  LoginResult,
  NewOrdersResult,
  Order,
  OrderStatus,
  SettingsInput,
  ShopSettings,
  StatusFilterOption,
  UploadResult,
} from '@/types/api'

/* ---- 鉴权 ---- */

export async function login(username: string, password: string): Promise<LoginResult> {
  const { data } = await http.post<LoginResult>('/admin/login', { username, password })
  return data
}

export async function fetchMe(): Promise<AdminInfo> {
  const { data } = await http.get<{ admin: AdminInfo }>('/admin/me')
  return data.admin
}

export async function changePassword(
  oldPassword: string,
  newPassword: string,
): Promise<LoginResult & { message: string }> {
  const { data } = await http.post<LoginResult & { message: string }>(
    '/admin/change-password',
    { old_password: oldPassword, new_password: newPassword },
  )
  return data
}

export async function fetchOverview(): Promise<AdminOverview> {
  const { data } = await http.get<AdminOverview>('/admin/overview')
  return data
}

/* ---- 订单 ---- */

export async function fetchOrderFilters(): Promise<StatusFilterOption[]> {
  const { data } = await http.get<{ options: StatusFilterOption[] }>(
    '/admin/orders/status-filter',
  )
  return data.options
}

export async function fetchAdminOrders(params: {
  status?: string
  limit?: number
  offset?: number
}): Promise<AdminOrderList> {
  const { data } = await http.get<AdminOrderList>('/admin/orders', { params })
  return data
}

export async function fetchNewOrders(sinceId: number): Promise<NewOrdersResult> {
  const { data } = await http.get<NewOrdersResult>('/admin/orders/new', {
    params: { since_id: sinceId },
  })
  return data
}

export async function fetchAdminOrder(orderNo: string): Promise<Order> {
  const { data } = await http.get<{ order: Order }>(
    `/admin/orders/${encodeURIComponent(orderNo)}`,
  )
  return data.order
}

export async function updateOrderStatus(
  orderNo: string,
  status: OrderStatus,
  cancelReason = '',
): Promise<{ order: Order; message: string }> {
  const { data } = await http.post<{ order: Order; message: string }>(
    `/admin/orders/${encodeURIComponent(orderNo)}/status`,
    { status, cancel_reason: cancelReason },
  )
  return data
}

export async function markOrdersSeen(orderIds?: number[]): Promise<number> {
  const { data } = await http.post<{ updated: number }>('/admin/orders/seen', orderIds ?? null)
  return data.updated
}

export async function triggerAutoCancel(): Promise<{ count: number; message: string }> {
  const { data } = await http.post<{ count: number; message: string }>(
    '/admin/orders/auto-cancel-stale',
  )
  return data
}

/* ---- 菜品 ---- */

export async function fetchDishes(params?: {
  category?: string
  keyword?: string
  only_available?: boolean
}): Promise<DishListResult> {
  const { data } = await http.get<DishListResult>('/admin/dishes', { params })
  return data
}

export async function fetchDishCategories(): Promise<string[]> {
  const { data } = await http.get<{ categories: string[] }>('/admin/dishes/categories')
  return data.categories
}

export async function createDish(payload: DishInput): Promise<{ dish: Dish; message: string }> {
  const { data } = await http.post<{ dish: Dish; message: string }>('/admin/dishes', payload)
  return data
}

export async function updateDish(
  id: number,
  payload: Partial<DishInput>,
): Promise<{ dish: Dish; message: string }> {
  const { data } = await http.patch<{ dish: Dish; message: string }>(
    `/admin/dishes/${id}`,
    payload,
  )
  return data
}

export async function toggleDish(
  id: number,
  isAvailable: boolean,
): Promise<{ dish: Dish; message: string }> {
  const { data } = await http.post<{ dish: Dish; message: string }>(
    `/admin/dishes/${id}/toggle`,
    { is_available: isAvailable },
  )
  return data
}

export async function deleteDish(id: number, force = false): Promise<{ message: string }> {
  const { data } = await http.delete<{ message: string }>(`/admin/dishes/${id}`, {
    params: force ? { force: true } : undefined,
  })
  return data
}

/**
 * 上传图片。用 XHR 而不是 axios，为了拿 onUploadProgress（手机网络下需要进度反馈）。
 */
export function uploadDishImage(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/admin/dishes/upload-image')
    xhr.setRequestHeader('Authorization', `Bearer ${localStorage.getItem('food_baby_token') || ''}`)
    // 手机大图上传慢，给足时间
    xhr.timeout = 60000 + Math.ceil(file.size / 1024 / 1024) * 15000

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      let body: unknown = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        body = null
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) {
        resolve(body as UploadResult)
      } else {
        const detail = (body as { detail?: string } | null)?.detail
        reject(new Error(detail || `上传失败（${xhr.status}）`))
      }
    }
    xhr.onerror = () => reject(new Error('上传失败，检查一下网络'))
    xhr.ontimeout = () => reject(new Error('上传超时了，图片可能太大'))
    xhr.send(form)
  })
}

/* ---- 店铺设置 ---- */

export async function fetchSettings(): Promise<ShopSettings> {
  const { data } = await http.get<{ settings: ShopSettings }>('/admin/settings')
  return data.settings
}

export async function updateSettings(
  payload: SettingsInput,
): Promise<{ settings: ShopSettings; message: string }> {
  const { data } = await http.patch<{ settings: ShopSettings; message: string }>(
    '/admin/settings',
    payload,
  )
  return data
}

export async function fetchRecommendCandidates(): Promise<Dish[]> {
  const { data } = await http.get<{ dishes: Dish[] }>('/admin/settings/recommend-candidates')
  return data.dishes
}
