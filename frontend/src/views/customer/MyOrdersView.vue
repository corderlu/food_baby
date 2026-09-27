<script setup lang="ts">
/**
 * 我的订单。
 *
 * 订单号存在本机 localStorage，所以这里做三件事：
 *   1. 批量查询这些订单的最新状态
 *   2. 给一个"用订单号找回"的入口（换了手机 / 清了数据时用）
 *   3. 每 30 秒静默刷新，让列表里的状态也是最新的
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import CustomerTabbar from '@/components/CustomerTabbar.vue'
import { useCustomerOrderStore } from '@/stores/customerOrders'
import * as api from '@/api/customer'
import { statusMeta } from '@/utils/order'
import { smartTime, expectedTimeText } from '@/utils/time'
import type { Order } from '@/types/api'

const orders = useCustomerOrderStore()
const router = useRouter()

const loading = ref(true)
const findOpen = ref(false)
const findInput = ref('')
const finding = ref(false)

let timer: number | null = null

const activeList = computed(() => orders.orders.filter((o) => o.active))
const finishedList = computed(() => orders.orders.filter((o) => !o.active))

async function refresh(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    await orders.loadHistoryOrders()
  } catch (e) {
    if (!silent) showToast(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await refresh()
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void refresh(true)
  }, 30000)
})

onBeforeUnmount(() => {
  if (timer !== null) window.clearInterval(timer)
})

function openOrder(order: Order): void {
  router.push(`/order/${order.order_no}`)
}

async function forget(order: Order): Promise<void> {
  try {
    await showConfirmDialog({
      title: '从列表移除',
      message: '只是从这台手机的列表里去掉，订单本身还在主厨那边',
      confirmButtonText: '移除',
      cancelButtonText: '取消',
    })
    orders.forget(order.order_no)
    await refresh(true)
  } catch {
    /* 取消 */
  }
}

/** 手动输订单号找回 */
async function findOrder(): Promise<void> {
  const no = findInput.value.trim().toUpperCase()
  if (!no) {
    showToast('请输入订单号')
    return
  }
  finding.value = true
  try {
    const order = await api.fetchOrder(no)
    orders.remember(order)
    findOpen.value = false
    findInput.value = ''
    showToast('找到啦')
    await refresh(true)
    router.push(`/order/${order.order_no}`)
  } catch (e) {
    showToast(e instanceof Error ? e.message : '没找到这个订单号')
  } finally {
    finding.value = false
  }
}
</script>

<template>
  <div class="page page--with-tabbar">
    <van-nav-bar title="我的订单">
      <template #right>
        <span class="nav-link" @click="findOpen = true">找回</span>
      </template>
    </van-nav-bar>

    <!-- 加载 -->
    <div v-if="loading" class="stack" style="padding: var(--sp-4)">
      <div v-for="i in 3" :key="i" class="skeleton" style="height: 92px; border-radius: var(--r-lg)" />
    </div>

    <!-- 空 -->
    <div v-else-if="!orders.orders.length" class="empty">
      <div class="empty__emoji">📭</div>
      <p>这台手机上还没有点过菜</p>
      <p class="t-sub">点过之后订单会记在这里，不用登录也能看到</p>
      <div class="empty__actions">
        <van-button round size="small" type="primary" @click="router.push('/')">去点菜</van-button>
        <van-button round size="small" plain @click="findOpen = true">用订单号找</van-button>
      </div>
    </div>

    <template v-else>
      <!-- 进行中 -->
      <section v-if="activeList.length">
        <div class="section-title">
          正在做
          <span class="section-title__extra">{{ activeList.length }} 单</span>
        </div>
        <div class="list">
          <article
            v-for="order in activeList"
            :key="order.order_no"
            class="ocard ocard--active"
            @click="openOrder(order)"
          >
            <div class="ocard__top">
              <span class="status-pill" :class="`status-pill--${order.status}`">
                {{ statusMeta(order.status).emoji }} {{ order.status_name }}
              </span>
              <span class="ocard__time">{{ smartTime(order.created_at) }}</span>
            </div>
            <div class="ocard__mid">
              <span class="ocard__no">{{ order.order_no }}</span>
              <span class="ocard__count">{{ order.total_items }} 份</span>
            </div>
            <p class="ocard__dishes ellipsis">
              {{ order.items.map((i) => `${i.dish_name}×${i.quantity}`).join('、') }}
            </p>
            <div class="ocard__foot">
              <span class="ocard__hint">{{ statusMeta(order.status).hint }}</span>
              <span class="ocard__arrow">›</span>
            </div>
          </article>
        </div>
      </section>

      <!-- 历史 -->
      <section v-if="finishedList.length">
        <div class="section-title">
          历史订单
          <span class="section-title__extra">{{ finishedList.length }} 单</span>
        </div>
        <div class="list">
          <article
            v-for="order in finishedList"
            :key="order.order_no"
            class="ocard"
            @click="openOrder(order)"
          >
            <div class="ocard__top">
              <span class="status-pill" :class="`status-pill--${order.status}`">
                {{ statusMeta(order.status).emoji }} {{ order.status_name }}
              </span>
              <span class="ocard__time">{{ smartTime(order.created_at) }}</span>
            </div>
            <div class="ocard__mid">
              <span class="ocard__no">{{ order.order_no }}</span>
              <span class="ocard__count">{{ order.total_items }} 份</span>
            </div>
            <p class="ocard__dishes ellipsis">
              {{ order.items.map((i) => `${i.dish_name}×${i.quantity}`).join('、') }}
            </p>
            <div v-if="order.expected_time" class="ocard__meta">
              期望 {{ expectedTimeText(order.expected_time) }} 用餐
            </div>
            <div class="ocard__foot">
              <span class="ocard__remove" @click.stop="forget(order)">从列表移除</span>
              <span class="ocard__arrow">›</span>
            </div>
          </article>
        </div>
      </section>

      <div class="heart-divider">♥ 一共点了 {{ orders.orders.length }} 单 ♥</div>
    </template>

    <!-- 找回弹窗 -->
    <van-popup v-model:show="findOpen" position="bottom" round>
      <div class="find">
        <h3 class="find__title">用订单号找回</h3>
        <p class="find__tip">订单号在成功页和主厨发你的消息里，形如 LOVE-20260927-001</p>
        <van-field
          v-model="findInput"
          placeholder="LOVE-20260927-001"
          class="find__field"
          @keyup.enter="findOrder"
        />
        <div class="find__actions">
          <van-button round plain block @click="findOpen = false">取消</van-button>
          <van-button round type="primary" block :loading="finding" @click="findOrder">
            找一下
          </van-button>
        </div>
      </div>
    </van-popup>

    <CustomerTabbar />
  </div>
</template>

<style scoped>
@import '@/styles/order.css';

.nav-link {
  color: var(--c-primary-strong);
  font-size: var(--fs-md);
  cursor: pointer;
}

.empty__actions {
  display: flex;
  gap: var(--sp-3);
  justify-content: center;
  margin-top: var(--sp-4);
}

.list {
  padding: 0 var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.ocard {
  padding: var(--sp-3) var(--sp-4);
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-sm);
  cursor: pointer;
  transition: transform var(--dur) var(--ease);
}

.ocard:active {
  transform: scale(0.99);
}

.ocard--active {
  border-color: var(--c-primary-300);
  box-shadow: var(--sh-md);
  background: linear-gradient(160deg, var(--c-primary-50), var(--c-bg-card) 60%);
}

.ocard__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}

.ocard__time {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.ocard__mid {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: var(--sp-2);
}

.ocard__no {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-sub);
  letter-spacing: 0.3px;
}

.ocard__count {
  font-size: var(--fs-sm);
  color: var(--c-primary-strong);
  font-weight: 600;
}

.ocard__dishes {
  margin: 4px 0 0;
  font-size: var(--fs-md);
  color: var(--c-text);
}

.ocard__meta {
  margin-top: 2px;
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.ocard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--sp-2);
  padding-top: var(--sp-2);
  border-top: 1px dashed var(--c-border);
}

.ocard__hint {
  font-size: var(--fs-xs);
  color: var(--c-primary-600);
}

.ocard__remove {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
  text-decoration: underline;
}

.ocard__arrow {
  font-size: 18px;
  color: var(--c-text-weak);
}

/* ---- 找回 ---- */
.find {
  padding: var(--sp-5) var(--sp-4) calc(var(--sp-5) + var(--safe-bottom));
}

.find__title {
  margin: 0;
  font-size: var(--fs-lg);
  text-align: center;
}

.find__tip {
  margin: var(--sp-2) 0 var(--sp-4);
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
  text-align: center;
}

.find__field {
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-bg-sunk);
}

.find__actions {
  display: flex;
  gap: var(--sp-3);
  margin-top: var(--sp-4);
}
</style>
