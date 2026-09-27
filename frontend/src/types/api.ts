/** 后端返回的数据结构（与 backend/app/serializers.py 一一对应）。 */

export type OrderStatus =
  | 'pending'
  | 'accepted'
  | 'preparing'
  | 'cooking'
  | 'served'
  | 'cancelled'

export interface Dish {
  id: number
  name: string
  description: string
  image_url: string
  thumb_url: string
  category: string
  tags: string[]
  spicy_level: number
  spicy_name: string
  estimated_minutes: number
  is_available: boolean
  sort_order: number
  created_at: string | null
  updated_at: string | null
}

export interface ShopSettings {
  shop_name: string
  announcement: string
  welcome_text: string
  business_open: boolean
  closed_tip: string
  today_recommend_ids: number[]
  updated_at: string | null
}

export interface ShopPayload {
  shop: ShopSettings
  recommends: Dish[]
}

export interface MenuGroup {
  category: string
  dishes: Dish[]
}

export interface MenuPayload {
  categories: string[]
  grouped: MenuGroup[]
  dishes: Dish[]
  total: number
}

export interface OrderItem {
  id: number
  dish_id: number | null
  dish_name: string
  dish_category: string
  dish_image_url: string
  quantity: number
  item_note: string
}

export interface Order {
  id: number
  order_no: string
  status: OrderStatus
  status_name: string
  total_items: number
  customer_note: string
  dish_request: string
  expected_time: string
  created_at: string | null
  updated_at: string | null
  accepted_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  cancel_reason: string
  editable: boolean
  active: boolean
  next_status: OrderStatus | null
  next_status_name: string | null
  items: OrderItem[]
  /** 管理端才有 */
  is_new?: boolean
  revision?: number
  elapsed_minutes?: number | null
}

export interface AdminInfo {
  id: number
  username: string
  created_at: string | null
  last_login_at: string | null
  using_default_password: boolean
}

export interface LoginResult {
  access_token: string
  token_type: string
  expires_at: string
  admin: AdminInfo
}

export interface AdminOrderList {
  orders: Order[]
  total: number
  pending_ids: number[]
  active_order_no: string | null
}

export interface NewOrdersResult {
  orders: Order[]
  max_id: number
  has_new: boolean
}

export interface DishListResult {
  dishes: Dish[]
  total: number
  categories: string[]
  available_count: number
}

export interface AdminOverview {
  admin: AdminInfo
  shop: ShopSettings
  active_order: null
  pending_count: number
  cooking_count: number
  available_dish_count: number
  total_orders: number
  active_order_no: string | null
}

export interface UploadResult {
  image_url: string
  thumb_url: string
  width?: number
  height?: number
  bytes?: number
}

export interface StatusFilterOption {
  value: string
  label: string
}

/* ---- 请求体 ---- */

export interface OrderItemInput {
  dish_id: number
  quantity: number
  item_note?: string
}

export interface OrderCreateInput {
  items: OrderItemInput[]
  customer_note?: string
  dish_request?: string
  expected_time?: string
}

export interface OrderModifyInput {
  add?: OrderItemInput[]
  remove?: OrderItemInput[]
  customer_note?: string
  dish_request?: string
  expected_time?: string
}

export interface DishInput {
  name: string
  description?: string
  image_url?: string
  category?: string
  tags?: string[]
  spicy_level?: number
  estimated_minutes?: number
  is_available?: boolean
  sort_order?: number
}

export interface SettingsInput {
  shop_name?: string
  announcement?: string
  welcome_text?: string
  business_open?: boolean
  closed_tip?: string
  today_recommend_ids?: number[]
}

export interface CartLine {
  dish_id: number
  name: string
  image_url: string
  category: string
  quantity: number
  item_note: string
}

export interface OrderStatusMeta {
  flow: OrderStatus[]
  names: Record<string, string>
  cancelled: OrderStatus
}
