<script setup lang="ts">
/** 管理端外壳：保证进入后台前登录态已恢复，并挂上底部导航。 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AdminTabbar from '@/components/AdminTabbar.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const checking = ref(true)

onMounted(async () => {
  await auth.init()
  if (!auth.isLoggedIn) {
    await router.replace({ name: 'admin-login', query: { redirect: router.currentRoute.value.fullPath } })
  }
  checking.value = false
})
</script>

<template>
  <div class="admin-shell">
    <div v-if="checking" class="admin-loading">
      <van-loading type="spinner" color="var(--c-primary)" size="26px" vertical>
        正在确认身份…
      </van-loading>
    </div>

    <router-view v-else v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>

    <AdminTabbar v-if="!checking" />
  </div>
</template>

<style scoped>
.admin-shell {
  min-height: 100dvh;
}

.admin-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60dvh;
}
</style>
