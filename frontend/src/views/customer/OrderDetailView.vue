<script setup lang="ts">
/**
 * 订单详情 / 状态页。
 *
 * 每 10 秒轮询一次状态（按需求文档）。
 * 另外她可以在这里改单：备菜中之前，加减菜都能操作，一旦进入烹饪中就锁死。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import * as api from '@/api/customer'
import { useOrderEdit } from '@/composables/useOrderEdit'
import { useCustomerOrderStore } from '@/stores/customerOrders'
import { useShopStore } from '@/stores/shop'
import { statusMeta, FLOW, flowIndex } from '@/utils/order'
import { elapsedText, fullTime, smartTime, expectedTimeText } from '@/utils/time'
import type { Order } from '@/types/api'

const route = useRoute()
const router = useRouter()
const orderStore = useCustomerOrderStore()
const shop = useShopStore()

const orderNo = computed(() => String(route.params.orderNo || ''))
const order = ref<Order | null>(null)
const loading = ref(true)
const notFound = ref(false)
const statusChangedHint = ref(false)
const cancelling = ref(false)

let timer: number | null = null

const meta = computed(() => statusMeta(order.value?.status ?? 'pending'))
const steps = computed(() => {
  const current = order.value?.status ?? 'pending'
  const idx = flowIndex(current)
  return FLOW.map((s, i) => ({
    status: s,
    label: statusMeta(s).label,
    emoji: statusMeta(s).emoji,
    done: current === 'served' ? true : i < idx,
    current: i === idx && current !== 'served',
  }))
})

const canEdit = computed(() => order.value?.editable === true)
const isCancelled = computed(() => order.value?.status === 'cancelled')

/** 详情页里"约几点能吃上"：出餐完成显示实际时间，否则给个预估 */
const etaText = computed(() => {
  const o = order.value
  if (!o) return ''
  if (o.status === 'served') return o.completed_at ? `已完成 · ${fullTime(o.completed_at)}` : '已完成'
  if (o.status === 'cancelled') return '已取消'
  if (o.expected_time) return `期望 ${expectedTimeText(o.expected_time)} 用餐`
  return ''
})

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    const fresh = await api.fetchOrder(orderNo.value)
    if (order.value && fresh.status !== order.value.status) {
      statusChangedHint.value = true
      window.setTimeout(() => (statusChangedHint.value = false), 3200)
    }
    order.value = fresh
    orderStore.remember(fresh)
    orderStore.markSeen(fresh)
    notFound.value = false
  } catch {
    if (!order.value) notFound.value = true
  } finally {
    if (!silent) loading.value = false
  }
}

onMounted(async () => {
  await load()
  // 静默拉一次菜单，改单弹窗里要有菜可选
  void shop.load(true).catch(() => undefined)

  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void load(true)
  }, 10000)
})

onBeforeUnmount(() => {
  if (timer !== null) window.clearInterval(timer)
})

/* ------------------------------------------------------------ 改单 / 取消 */

const edit = useOrderEdit(order, () => void load(true))

async function onCancel(): Promise<void> {
  try {
    await showConfirmDialog({
      title: '取消订单',
      message: '确定不要这一单了吗？主厨还没开始做哦',
      confirmButtonText: '确定取消',
      cancelButtonText: '再想想',
    })
  } catch {
    return
  }

  cancelling.value = true
  try {
    const result = await api.cancelOrder(orderNo.value)
    order.value = result.order
    orderStore.markSeen(result.order)
    showToast(result.message || '已取消')
  } catch (e) {
    showToast(e instanceof Error ? e.message : '取消失败')
  } finally {
    cancelling.value = false
  }
}

/* ------------------------------------------------------------ 找回订单 */

function goMine(): void {
  router.push('/my-orders')
}
</script>

<template>
  <div class="page">
    <van-nav-bar title="订单详情" left-arrow @click-left="router.back()" />

    <!-- 加载中 -->
    <div v-if="loading" class="stack" style="padding: var(--sp-4)">
      <div class="skeleton" style="height: 120px; border-radius: var(--r-lg)" />
      <div class="skeleton" style="height: 90px; border-radius: var(--r-lg)" />
      <div class="skeleton" style="height: 160px; border-radius: var(--r-lg)" />
    </div>

    <!-- 找不到 -->
    <div v-else-if="notFound" class="empty">
      <div class="empty__emoji">🔍</div>
      <p>没找到这个订单</p>
      <p class="t-sub">订单号：{{ orderNo }}</p>
      <van-button round size="small" type="primary" @click="goMine">看看我的订单</van-button>
    </div>

    <template v-else-if="order">
      <!-- 状态卡 -->
      <section class="status-card" :class="`status-card--${order.status}`">
        <div class="status-card__top">
          <span class="status-card__emoji">{{ meta.emoji }}</span>
          <div class="grow">
            <h2 class="status-card__title">{{ order.status_name }}</h2>
            <p class="status-card__hint">{{ meta.hint }}</p>
          </div>
          <transition name="fade">
            <span v-if="statusChangedHint" class="status-card__flash">有更新</span>
          </transition>
        </div>

        <div v-if="etaText" class="status-card__eta">{{ etaText }}</div>
      </section>

      <!-- 进度条 -->
      <div v-if="!isCancelled" class="card steps-card">
        <div class="steps">
          <div
            v-for="step in steps"
            :key="step.status"
            class="steps__item"
            :class="{ 'is-done': step.done, 'is-current': step.current }"
          >
            <span class="steps__dot">{{ step.done ? '✓' : step.emoji }}</span>
            <span class="steps__label">{{ step.label }}</span>
          </div>
        </div>
      </div>

      <!-- 取消信息 -->
      <div v-else class="cancelled-box">
        <strong>这单取消了</strong>
        <p style="margin: 4px 0 0">
          {{ order.cancel_reason || '没有填写原因' }}
        </p>
        <p class="t-weak" style="margin: 4px 0 0">{{ fullTime(order.cancelled_at) }}</p>
      </div>

      <!-- 菜品清单 -->
      <section class="section-title">
        菜品清单
        <span class="section-title__extra">{{ order.total_items }} 份</span>
      </section>

      <div class="card items">
        <div v-for="item in order.items" :key="item.id" class="items__row">
          <div class="items__media">
            <img v-if="item.dish_image_url" :src="item.dish_image_url" :alt="item.dish_name" loading="lazy" />
            <div v-else class="items__fallback">♥</div>
          </div>
          <div class="grow">
            <div class="row row--between">
              <span class="items__name">{{ item.dish_name }}</span>
              <span class="items__qty">×{{ item.quantity }}</span>
            </div>
            <p v-if="item.item_note" class="items__note">备注：{{ item.item_note }}</p>
          </div>
        </div>
      </div>

      <!-- 订单信息 -->
      <section class="section-title">订单信息</section>
      <div class="card card__pad info">
        <div class="info__row">
          <span class="info__label">订单号</span>
          <span class="info__value">{{ order.order_no }}</span>
        </div>
        <div class="info__row">
          <span class="info__label">下单时间</span>
          <span class="info__value">{{ smartTime(order.created_at) }}</span>
        </div>
        <div v-if="order.expected_time" class="info__row">
          <span class="info__label">期望用餐</span>
          <span class="info__value">{{ expectedTimeText(order.expected_time) }}</span>
        </div>
        <div v-if="order.customer_note" class="info__row info__row--block">
          <span class="info__label">备注</span>
          <span class="info__value">{{ order.customer_note }}</span>
        </div>
        <div v-if="order.dish_request" class="info__row info__row--block wish">
          <span class="info__label">我想吃别的</span>
          <span class="info__value">{{ order.dish_request }}</span>
        </div>
        <div v-if="order.elapsed_minutes !== null && order.elapsed_minutes !== undefined" class="info__row">
          <span class="info__label">已过时间</span>
          <span class="info__value t-sub">{{ elapsedText(order.elapsed_minutes) }}</span>
        </div>
      </div>

      <!-- 改单提示 -->
      <div v-if="canEdit" class="edit-hint">
        <span>💡</span>
        <span>还能改哦：想加菜、减菜或改备注都可以，主厨下锅之后就锁定啦</span>
      </div>

      <div class="heart-divider">♥</div>

      <!-- 操作 -->
      <div v-if="canEdit" class="actions">
        <van-button round plain type="primary" block @click="edit.open()">修改这一单</van-button>
        <van-button round plain block :loading="cancelling" @click="onCancel">取消订单</van-button>
      </div>
    </template>

    <!-- 改单弹窗 -->
    <van-popup
      v-model:show="edit.visible.value"
      position="bottom"
      round
      :close-on-click-overlay="false"
      :style="{ maxWidth: 'var(--page-max)', left: '50%', transform: 'translateX(-50%)' }"
    >
      <div class="edit">
        <header class="edit__head">
          <h3>修改这一单</h3>
          <button class="edit__close" aria-label="关闭" @click="edit.close()">×</button>
        </header>

        <div class="edit__body">
          <van-field
            v-model="edit.note.value"
            label="备注"
            placeholder="少辣、不要葱…"
            maxlength="200"
            show-word-limit
            type="textarea"
            rows="2"
            autosize
          />
          <van-field
            v-model="edit.dishRequest.value"
            label="我想吃别的"
            placeholder="菜单里没有的"
            maxlength="200"
            type="textarea"
            rows="2"
            autosize
          />

          <div class="edit__section">
            <div class="edit__section-title">当前菜品（点 + / − 修改）</div>

            <div v-for="line in edit.lines.value" :key="line.dish_id" class="eline">
              <div class="grow">
                <div class="eline__name">{{ line.name }}</div>
                <div class="eline__now">原本 {{ line.original }} 份</div>
              </div>
              <van-stepper
                :model-value="line.target"
                min="0"
                max="99"
                integer
                button-size="24"
                @plus="edit.increase(line.dish_id)"
                @minus="edit.decrease(line.dish_id)"
              />
            </div>
          </div>

          <div v-if="edit.addableDishes.value.length" class="edit__section">
            <div class="edit__section-title">再加点别的</div>
            <div v-for="dish in edit.addableDishes.value" :key="dish.id" class="eline">
              <div class="grow">
                <div class="eline__name">{{ dish.name }}</div>
                <div class="eline__now">{{ dish.category }} · ⏱{{ dish.estimated_minutes }}分</div>
              </div>
              <van-stepper
                :model-value="edit.addQty(dish.id)"
                min="0"
                max="99"
                integer
                button-size="24"
                @plus="edit.addDish(dish.id)"
                @minus="edit.removeAdded(dish.id)"
              />
            </div>
          </div>

          <div v-else class="t-sub t-center" style="padding: var(--sp-3)">
            菜单里暂时没有别的菜可以加了
          </div>
        </div>

        <footer class="edit__foot">
          <span class="grow t-sub">{{ edit.summary.value }}</span>
          <van-button round plain size="small" @click="edit.close()">取消</van-button>
          <van-button
            round
            type="primary"
            size="small"
            :loading="edit.saving.value"
            :disabled="!edit.dirty.value"
            @click="edit.save()"
          >
            保存修改
          </van-button>
        </footer>
      </div>
    </van-popup>
  </div>
</template>

<style scoped>
@import '@/styles/order.css';

/* ---- 状态卡 ---- */
.status-card {
  margin: var(--sp-4);
  padding: var(--sp-4);
  border-radius: var(--r-xl);
  background: linear-gradient(140deg, var(--c-primary-300), var(--c-primary-100));
  box-shadow: var(--sh-md);
}

.status-card--served {
  background: linear-gradient(140deg, #b9ecd3, #e6f8ef);
}

.status-card--cancelled {
  background: linear-gradient(140deg, #e4dde1, #f4eff2);
}

.status-card--cooking {
  background: linear-gradient(140deg, #ffc9b8, #ffe4dc);
}

.status-card__top {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.status-card__emoji {
  font-size: 32px;
}

.status-card__title {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--c-primary-700);
}

.status-card--served .status-card__title {
  color: #1f7a55;
}

.status-card--cancelled .status-card__title {
  color: #6b5c64;
}

.status-card--cooking .status-card__title {
  color: #a8412c;
}

.status-card__hint {
  margin: 2px 0 0;
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
}

.status-card__flash {
  padding: 2px 8px;
  border-radius: var(--r-pill);
  background: var(--c-danger);
  color: #fff;
  font-size: var(--fs-xs);
  font-weight: 600;
}

.status-card__eta {
  margin-top: var(--sp-3);
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
}

/* ---- 进度 ---- */
.steps-card {
  margin: 0 var(--sp-4);
}

/* ---- 明细 ---- */
.items {
  margin: 0 var(--sp-4);
}

.items__row {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-3);
  border-bottom: 1px solid var(--c-border);
}

.items__row:last-child {
  border-bottom: none;
}

.items__media {
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  border-radius: var(--r-sm);
  overflow: hidden;
  background: var(--c-primary-50);
}

.items__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.items__fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-primary-300);
}

.items__name {
  font-size: var(--fs-md);
  font-weight: 500;
}

.items__qty {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--c-primary-strong);
}

.items__note {
  margin: 2px 0 0;
  font-size: var(--fs-xs);
  color: var(--c-text-sub);
}

/* ---- 信息 ---- */
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
  font-size: var(--fs-md);
}

.info__row--block {
  flex-direction: column;
  gap: 2px;
}

.info__label {
  flex: 0 0 72px;
  color: var(--c-text-sub);
  font-size: var(--fs-sm);
}

.info__value {
  flex: 1;
  word-break: break-all;
}

.wish .info__label {
  color: var(--c-primary-600);
  font-weight: 600;
}

.wish .info__value {
  color: var(--c-primary-700);
}

/* ---- 改单提示 / 操作 ---- */
.edit-hint {
  display: flex;
  gap: var(--sp-2);
  margin: var(--sp-4);
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: var(--c-primary-50);
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
  line-height: 1.5;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  padding: 0 var(--sp-4);
}

/* ---- 改单弹窗 ---- */
.edit {
  display: flex;
  flex-direction: column;
  max-height: 88dvh;
}

.edit__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  border-bottom: 1px solid var(--c-border);
}

.edit__head h3 {
  margin: 0;
  font-size: var(--fs-lg);
}

.edit__close {
  border: none;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  color: var(--c-text-sub);
  cursor: pointer;
}

.edit__body {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-2) var(--sp-4) var(--sp-4);
}

.edit__section {
  margin-top: var(--sp-4);
}

.edit__section-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-sub);
  margin-bottom: var(--sp-2);
}

.eline {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) 0;
  border-bottom: 1px dashed var(--c-border);
}

.eline:last-child {
  border-bottom: none;
}

.eline__name {
  font-size: var(--fs-md);
}

.eline__now {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.edit__foot {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4) calc(var(--sp-3) + var(--safe-bottom));
  border-top: 1px solid var(--c-border);
  background: var(--c-bg-card);
}
</style>
