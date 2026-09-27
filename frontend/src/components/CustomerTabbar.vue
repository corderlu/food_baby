<script setup lang="ts">
/** 顾客端底部导航：点菜 / 我的订单 / 购物车 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCartStore } from '@/stores/cart'

const route = useRoute()
const router = useRouter()
const cart = useCartStore()

const current = computed({
  get: () => {
    if (route.path.startsWith('/my-orders')) return 'orders'
    if (route.path.startsWith('/cart')) return 'cart'
    return 'menu'
  },
  set: (v: string) => {
    const map: Record<string, string> = {
      menu: '/',
      orders: '/my-orders',
      cart: '/cart',
    }
    router.push(map[v] || '/')
  },
})

const badge = computed(() => (cart.totalCount > 0 ? cart.totalCount : ''))
</script>

<template>
  <van-tabbar v-model="current" :border="true" active-color="var(--c-primary-strong)" fixed placeholder>
    <van-tabbar-item name="menu" icon="shop-o">点菜</van-tabbar-item>
    <van-tabbar-item name="orders" icon="orders-o">我的订单</van-tabbar-item>
    <van-tabbar-item name="cart" icon="shopping-cart-o" :badge="badge">购物车</van-tabbar-item>
  </van-tabbar>
</template>
