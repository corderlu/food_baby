<script setup lang="ts">
/** 账号安全：改密码 + 退出登录 + 一些系统自检信息。 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/http'
import { isSupported, isUnlocked } from '@/utils/sound'
import { fullTime } from '@/utils/time'

const auth = useAuthStore()
const router = useRouter()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)

const health = ref<Record<string, unknown> | null>(null)

const canSubmit = computed(
  () => Boolean(oldPassword.value && newPassword.value && confirmPassword.value),
)

const newPasswordIssue = computed(() => {
  if (!newPassword.value) return ''
  if (newPassword.value.length < 6) return '新密码至少 6 位'
  if (newPassword.value === oldPassword.value) return '新密码不能和原密码一样'
  return ''
})

const confirmIssue = computed(() => {
  if (!confirmPassword.value) return ''
  if (confirmPassword.value !== newPassword.value) return '两次输入的新密码不一样'
  return ''
})

onMounted(async () => {
  try {
    const res = await fetch('/api/health')
    health.value = (await res.json()) as Record<string, unknown>
  } catch {
    health.value = null
  }
})

async function submit(): Promise<void> {
  if (submitting.value) return
  if (newPasswordIssue.value) {
    showToast(newPasswordIssue.value)
    return
  }
  if (confirmIssue.value) {
    showToast(confirmIssue.value)
    return
  }

  submitting.value = true
  try {
    const message = await auth.changePassword(oldPassword.value, newPassword.value)
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    showToast(message || '密码已更新')
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function logout(): Promise<void> {
  try {
    await showConfirmDialog({
      title: '退出登录',
      message: '退出后需要重新输入密码才能进后台。',
      confirmButtonText: '退出',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  auth.logout()
  await router.replace('/admin/login')
}
</script>

<template>
  <div class="page page--with-tabbar">
    <header class="ahead">
      <h1 class="ahead__title">账号安全</h1>
      <p class="ahead__sub">
        {{ auth.username }}
        <span v-if="auth.admin?.last_login_at"> · 上次登录 {{ fullTime(auth.admin.last_login_at) }}</span>
      </p>
    </header>

    <div v-if="auth.usingDefaultPassword" class="warn">
      <span>⚠️</span>
      <span class="grow">你还在用初始密码 admin123，建议现在就改掉</span>
    </div>

    <!-- 改密码 -->
    <section class="section-title">修改密码</section>
    <div class="card card__pad form">
      <van-field
        v-model="oldPassword"
        type="password"
        label="原密码"
        placeholder="当前密码"
        autocomplete="current-password"
      />
      <van-field
        v-model="newPassword"
        type="password"
        label="新密码"
        placeholder="至少 6 位"
        autocomplete="new-password"
        :error-message="newPasswordIssue"
      />
      <van-field
        v-model="confirmPassword"
        type="password"
        label="确认新密码"
        placeholder="再输一次"
        autocomplete="new-password"
        :error-message="confirmIssue"
        @keyup.enter="submit"
      />

      <van-button
        round
        type="primary"
        block
        class="form__submit"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submit"
      >
        保存新密码
      </van-button>
      <p class="form__hint">改完之后其他设备上的登录会失效，需要重新登录。</p>
    </div>

    <!-- 系统自检 -->
    <section class="section-title">运行状态</section>
    <div class="card card__pad info">
      <div class="info__row">
        <span class="info__label">后端接口</span>
        <span class="info__value" :class="health?.ok ? 'is-ok' : 'is-bad'">
          {{ health ? (health.ok ? '正常' : '异常') : '读不到' }}
        </span>
      </div>
      <div class="info__row">
        <span class="info__label">服务器时间</span>
        <span class="info__value">{{ health?.server_time || '—' }}</span>
      </div>
      <div class="info__row">
        <span class="info__label">中文字体</span>
        <span class="info__value" :class="health?.cjk_font ? 'is-ok' : 'is-bad'">
          {{ health?.cjk_font ? '已安装（占位图文字正常）' : '缺失（占位图中文会变方块）' }}
        </span>
      </div>
      <div class="info__row">
        <span class="info__label">提示音</span>
        <span class="info__value">
          {{ isSupported() ? (isUnlocked() ? '可用' : '需要先点一次开启') : '此浏览器不支持' }}
        </span>
      </div>
      <div class="info__row">
        <span class="info__label">上传目录</span>
        <span class="info__value t-weak">{{ health?.upload_dir || '—' }}</span>
      </div>
    </div>

    <div class="heart-divider">♥</div>

    <div class="actions">
      <van-button round plain block @click="router.push('/')">去顾客端看看</van-button>
      <van-button round plain block type="danger" @click="logout">退出登录</van-button>
    </div>
  </div>
</template>

<style scoped>
.ahead {
  padding: calc(var(--sp-4) + var(--safe-top)) var(--sp-4) var(--sp-4);
  background: linear-gradient(165deg, var(--c-primary-200), var(--c-bg) 92%);
  border-bottom-left-radius: var(--r-xl);
  border-bottom-right-radius: var(--r-xl);
}

.ahead__title {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--c-primary-700);
}

.ahead__sub {
  margin: 2px 0 0;
  font-size: var(--fs-xs);
  color: var(--c-text-sub);
}

.warn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: var(--sp-4);
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: #fff6e5;
  color: #a25b00;
  font-size: var(--fs-sm);
}

.form {
  margin: 0 var(--sp-4);
}

.form :deep(.van-field) {
  padding-left: 0;
  padding-right: 0;
  border-bottom: 1px solid var(--c-border);
}

.form__submit {
  margin-top: var(--sp-4);
}

.form__hint {
  margin: var(--sp-3) 0 0;
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.info {
  margin: 0 var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.info__row {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  font-size: var(--fs-sm);
}

.info__label {
  flex: 0 0 84px;
  color: var(--c-text-sub);
}

.info__value {
  flex: 1;
  word-break: break-all;
}

.is-ok {
  color: var(--c-success);
  font-weight: 600;
}

.is-bad {
  color: var(--c-danger);
  font-weight: 600;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: 0 var(--sp-4);
}
</style>
