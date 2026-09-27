<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

// 冷启动时恢复登录态（只对管理端有意义，顾客端零成本）
onMounted(async () => {
  if (router.currentRoute.value.path.startsWith('/admin') && auth.admin === null) {
    await auth.init()
  }
})
</script>

<template>
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>
