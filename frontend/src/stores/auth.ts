/** 管理端登录态（JWT 存 localStorage）。 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '@/api/admin'
import { ApiError, getToken, setToken } from '@/api/http'
import type { AdminInfo } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const admin = ref<AdminInfo | null>(null)
  const initialized = ref(false)
  const loading = ref(false)

  const isLoggedIn = computed(() => Boolean(getToken() && admin.value))
  const username = computed(() => admin.value?.username ?? '')
  const usingDefaultPassword = computed(() => admin.value?.using_default_password ?? false)

  /** 冷启动时验证本地 token 是否还有效 */
  async function init(): Promise<void> {
    if (initialized.value) return
    loading.value = true
    try {
      if (!getToken()) {
        admin.value = null
        return
      }
      admin.value = await api.fetchMe()
    } catch (e) {
      // token 失效 / 后端重启换了密钥
      if (e instanceof ApiError && (e.status === 401 || e.status === 0)) {
        setToken('')
        admin.value = null
      }
    } finally {
      loading.value = false
      initialized.value = true
    }
  }

  async function login(user: string, password: string): Promise<void> {
    loading.value = true
    try {
      const result = await api.login(user.trim(), password)
      setToken(result.access_token)
      admin.value = result.admin
      initialized.value = true
    } finally {
      loading.value = false
    }
  }

  function logout(): void {
    setToken('')
    admin.value = null
  }

  async function changePassword(oldPassword: string, newPassword: string): Promise<string> {
    const result = await api.changePassword(oldPassword, newPassword)
    // 改密码后端会下发新 token（旧 token 作废）
    setToken(result.access_token)
    admin.value = result.admin
    return result.message
  }

  function clearLocal(): void {
    setToken('')
    admin.value = null
    initialized.value = false
  }

  return {
    admin,
    initialized,
    loading,
    isLoggedIn,
    username,
    usingDefaultPassword,
    init,
    login,
    logout,
    changePassword,
    clearLocal,
  }
})
