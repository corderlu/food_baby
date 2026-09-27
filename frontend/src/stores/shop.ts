/** 店铺信息 + 菜单缓存。顾客端多个页面共用，避免重复请求。 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '@/api/customer'
import type { Dish, MenuPayload, ShopSettings } from '@/types/api'
import { useCartStore } from './cart'

export const useShopStore = defineStore('shop', () => {
  const shop = ref<ShopSettings | null>(null)
  const recommends = ref<Dish[]>([])
  const menu = ref<MenuPayload | null>(null)
  const loading = ref(false)
  const loadedOnce = ref(false)
  const error = ref('')

  const dishes = computed<Dish[]>(() => menu.value?.dishes ?? [])
  const categories = computed<string[]>(() => menu.value?.categories ?? [])
  const grouped = computed(() => menu.value?.grouped ?? [])
  const shopName = computed(() => shop.value?.shop_name || '爱心小食堂')
  const businessOpen = computed(() => shop.value?.business_open !== false)
  const closedTip = computed(() => shop.value?.closed_tip || '主厨休息中')

  const recommendIds = computed(() => new Set(shop.value?.today_recommend_ids ?? []))

  function dishById(id: number): Dish | undefined {
    return dishes.value.find((d) => d.id === id)
  }

  function isRecommend(id: number): boolean {
    return recommendIds.value.has(id)
  }

  /** 拉店铺信息 + 菜单。silent=true 时用于后台轮询，不显示 loading。 */
  async function load(silent = false): Promise<void> {
    if (!silent) loading.value = true
    error.value = ''
    try {
      const [shopData, menuData] = await Promise.all([api.fetchShop(), api.fetchMenu()])
      shop.value = shopData.shop
      recommends.value = shopData.recommends
      menu.value = menuData

      // 让购物车补全菜名/图片，并自动剔除已下架的菜
      const cart = useCartStore()
      cart.attach(menuData.dishes)

      loadedOnce.value = true
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载失败'
      throw e
    } finally {
      if (!silent) loading.value = false
    }
  }

  return {
    shop,
    recommends,
    menu,
    loading,
    loadedOnce,
    error,
    dishes,
    categories,
    grouped,
    shopName,
    businessOpen,
    closedTip,
    recommendIds,
    dishById,
    isRecommend,
    load,
  }
})
