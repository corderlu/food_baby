<script setup lang="ts">
/** 主厨登录页。 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/http'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('admin')
const password = ref('')
const submitting = ref(false)
const showPassword = ref(false)

const expired = computed(() => route.query.expired === '1')

onMounted(() => {
  // 已登录（token 有效）就直接进后台
  void auth.init().then(() => {
    if (auth.isLoggedIn) {
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/admin/orders'
      void router.replace(redirect)
    }
  })
})

async function submit(): Promise<void> {
  if (submitting.value) return
  if (!username.value.trim() || !password.value) {
    showToast('用户名和密码都要填哦')
    return
  }

  submitting.value = true
  try {
    await auth.login(username.value, password.value)
    showToast('欢迎回来，主厨 ♥')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/admin/orders'
    await router.replace(redirect)
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page login">
    <div class="login__brand">
      <div class="login__logo">♥</div>
      <h1 class="login__title">爱心小食堂</h1>
      <p class="login__sub">主厨后台</p>
    </div>

    <div v-if="expired" class="login__expired">登录已过期，重新登录一下</div>

    <div class="card card__pad login__form">
      <van-field
        v-model="username"
        label="用户名"
        placeholder="请输入用户名"
        autocomplete="username"
        clearable
      />
      <van-field
        v-model="password"
        :type="showPassword ? 'text' : 'password'"
        label="密码"
        placeholder="请输入密码"
        autocomplete="current-password"
        :right-icon="showPassword ? 'eye-o' : 'closed-eye'"
        @click-right-icon="showPassword = !showPassword"
        @keyup.enter="submit"
      />

      <van-button
        round
        type="primary"
        block
        class="login__submit"
        :loading="submitting"
        @click="submit"
      >
        登录
      </van-button>

      <p class="login__hint">
        初始账号 <code>admin</code> / <code>admin123</code>，登录后请到「账号安全」改掉
      </p>
    </div>

    <div class="login__foot">
      <span @click="router.push('/')">← 回到点菜页</span>
    </div>
  </div>
</template>

<style scoped>
.login {
  padding: calc(var(--sp-8) + var(--safe-top)) var(--sp-4) var(--sp-6);
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: linear-gradient(170deg, var(--c-primary-200), var(--c-bg) 55%);
}

.login__brand {
  text-align: center;
  margin-bottom: var(--sp-6);
}

.login__logo {
  width: 66px;
  height: 66px;
  margin: 0 auto var(--sp-3);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: #fff;
  background: linear-gradient(140deg, var(--c-primary-400), var(--c-primary-600));
  box-shadow: var(--sh-primary);
  animation: heart-beat 2.4s var(--ease) infinite;
}

.login__title {
  margin: 0;
  font-size: var(--fs-2xl);
  font-weight: 700;
  color: var(--c-primary-700);
}

.login__sub {
  margin: 4px 0 0;
  font-size: var(--fs-md);
  color: var(--c-text-sub);
}

.login__expired {
  margin-bottom: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-md);
  background: #fff4e5;
  color: #a25b00;
  font-size: var(--fs-sm);
  text-align: center;
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.login__form :deep(.van-field) {
  padding-left: 0;
  padding-right: 0;
  border-bottom: 1px solid var(--c-border);
}

.login__submit {
  margin-top: var(--sp-4);
}

.login__hint {
  margin: var(--sp-3) 0 0;
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
  text-align: center;
  line-height: 1.6;
}

.login__hint code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--c-bg-sunk);
  color: var(--c-primary-700);
}

.login__foot {
  margin-top: auto;
  text-align: center;
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
}

.login__foot span {
  cursor: pointer;
}
</style>
