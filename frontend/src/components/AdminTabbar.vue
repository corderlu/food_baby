<script setup lang="ts">
/** 管理端底部导航。 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const TABS = [
  { name: 'admin-orders', path: '/admin/orders', icon: 'orders-o', label: '订单' },
  { name: 'admin-dishes', path: '/admin/dishes', icon: 'shop-o', label: '菜品' },
  { name: 'admin-settings', path: '/admin/settings', icon: 'setting-o', label: '店铺' },
  { name: 'admin-account', path: '/admin/account', icon: 'manager-o', label: '账号' },
]

const current = computed({
  get: () => {
    const hit = TABS.find((t) => route.path.startsWith(t.path))
    return hit?.name ?? 'admin-orders'
  },
  set: (name: string) => {
    const hit = TABS.find((t) => t.name === name)
    if (hit) void router.push(hit.path)
  },
})
</script>

<template>
  <van-tabbar v-model="current" fixed placeholder active-color="var(--c-primary-strong)">
    <van-tabbar-item v-for="tab in TABS" :key="tab.name" :name="tab.name" :icon="tab.icon">
      {{ tab.label }}
    </van-tabbar-item>
  </van-tabbar>
</template>
