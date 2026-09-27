<script setup lang="ts">
/** 下单成功页。落地即显示订单号和"主厨已收到"，给一个明确的完成感。 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as api from '@/api/customer'
import { useCustomerOrderStore } from '@/stores/customerOrders'
import { expectedTimeText, smartTime } from '@/utils/time'
import type { Order } from '@/types/api'

const route = useRoute()
const router = useRouter()
const orderStore = useCustomerOrderStore()

const orderNo = computed(() => String(route.params.orderNo || ''))
const order = ref<Order | null>(null)

onMounted(async () => {
  try {
    order.value = await api.fetchOrder(orderNo.value)
    orderStore.remember(order.value)
    orderStore.markSeen(order.value)
  } catch {
    /* 详情拉不到也不影响这个页面的主要作用 */
  }
})
</script>

<template>
  <div class="page success">
    <div class="success__burst">
      <span class="success__heart success__heart--1">♥</span>
      <span class="success__heart success__heart--2">♥</span>
      <span class="success__heart success__heart--3">♥</span>
      <div class="success__circle">🍳</div>
    </div>

    <h1 class="success__title">下单成功啦！</h1>
    <p class="success__sub">主厨已经收到你的菜单，马上开火 ♥</p>

    <div class="card card__pad success__card">
      <div class="success__row">
        <span class="success__label">订单号</span>
        <span class="success__value">{{ orderNo }}</span>
      </div>
      <div v-if="order" class="success__row">
        <span class="success__label">共</span>
        <span class="success__value">{{ order.total_items }} 份菜</span>
      </div>
      <div v-if="order?.expected_time" class="success__row">
        <span class="success__label">期望用餐</span>
        <span class="success__value">{{ expectedTimeText(order.expected_time) }}</span>
      </div>
      <div v-if="order" class="success__row">
        <span class="success__label">下单时间</span>
        <span class="success__value">{{ smartTime(order.created_at) }}</span>
      </div>
      <div v-if="order?.dish_request" class="success__wish">
        <div class="success__wish-label">你说想吃别的</div>
        <div class="success__wish-value">{{ order.dish_request }}</div>
        <div class="success__wish-tip">这个会单独告诉主厨，让他想办法 ♥</div>
      </div>
    </div>

    <div class="success__actions">
      <van-button round type="primary" block @click="router.replace(`/order/${orderNo}`)">
        看看做到哪一步了
      </van-button>
      <van-button round plain block @click="router.replace('/')">回去接着逛菜单</van-button>
    </div>

    <p class="success__foot">♥ 这单的状态会每 10 秒自动更新 ♥</p>
  </div>
</template>

<style scoped>
.success {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: calc(var(--sp-8) + var(--safe-top)) var(--sp-4) var(--sp-6);
  text-align: center;
}

.success__burst {
  position: relative;
  width: 130px;
  height: 130px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.success__circle {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 44px;
  background: linear-gradient(140deg, var(--c-primary-300), var(--c-primary-100));
  box-shadow: var(--sh-primary);
  animation: pop 520ms var(--ease) both;
}

@keyframes pop {
  0% {
    transform: scale(0.4);
    opacity: 0;
  }
  70% {
    transform: scale(1.06);
    opacity: 1;
  }
  100% {
    transform: scale(1);
  }
}

.success__heart {
  position: absolute;
  color: var(--c-primary-400);
  animation: float-up 2.4s var(--ease) infinite;
}

.success__heart--1 {
  left: 6px;
  top: 18px;
  font-size: 18px;
  animation-delay: 0s;
}

.success__heart--2 {
  right: 10px;
  top: 34px;
  font-size: 22px;
  animation-delay: 0.5s;
}

.success__heart--3 {
  right: 34px;
  bottom: 4px;
  font-size: 14px;
  animation-delay: 1s;
}

@keyframes float-up {
  0% {
    transform: translateY(6px);
    opacity: 0;
  }
  40% {
    opacity: 1;
  }
  100% {
    transform: translateY(-16px);
    opacity: 0;
  }
}

.success__title {
  margin: var(--sp-4) 0 0;
  font-size: var(--fs-2xl);
  font-weight: 700;
  color: var(--c-primary-700);
}

.success__sub {
  margin: var(--sp-2) 0 var(--sp-5);
  font-size: var(--fs-md);
  color: var(--c-text-sub);
}

.success__card {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  text-align: left;
}

.success__row {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  font-size: var(--fs-md);
}

.success__label {
  flex: 0 0 68px;
  color: var(--c-text-sub);
  font-size: var(--fs-sm);
}

.success__value {
  flex: 1;
  font-weight: 500;
  word-break: break-all;
}

.success__wish {
  margin-top: var(--sp-2);
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: var(--c-primary-50);
}

.success__wish-label {
  font-size: var(--fs-xs);
  color: var(--c-primary-600);
  font-weight: 600;
}

.success__wish-value {
  margin-top: 2px;
  font-size: var(--fs-md);
  color: var(--c-primary-700);
}

.success__wish-tip {
  margin-top: 4px;
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.success__actions {
  width: 100%;
  margin-top: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.success__foot {
  margin-top: var(--sp-5);
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}
</style>
