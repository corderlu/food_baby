<script setup lang="ts">
/**
 * 订单看板 —— 整个系统里最需要"不掉链子"的页面。
 *
 * 提醒机制（从可靠到辅助，逐层兜底）：
 *   1. 页面标题闪烁 —— 不需要任何权限，一定有效
 *   2. 提示音 —— 需要一次用户点击解锁（"开启提示音"按钮）
 *   3. 手机震动 —— 支持就震，不支持就算了
 * 新订单和"她改了单"用不同的声音区分，避免混在一起分不清。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import * as api from '@/api/admin'
import { errorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import {
  isUnlocked,
  isSupported,
  playMixed,
  playModified,
  playNewOrder,
  startTitleFlash,
  stopTitleFlash,
  unlock,
  vibrate,
} from '@/utils/sound'
import { nextActionIcon, nextActionLabel, statusMeta } from '@/utils/order'
import { elapsedText, expectedTimeText, smartTime } from '@/utils/time'
import type { Order, OrderStatus, StatusFilterOption } from '@/types/api'

const router = useRouter()
const auth = useAuthStore()

const SOUND_PREF_KEY = 'food_baby_sound_on'
const LAST_ID_KEY = 'food_baby_last_order_id'

const orders = ref<Order[]>([])
const filters = ref<StatusFilterOption[]>([])
const status = ref('all')
const loading = ref(true)
const refreshing = ref(false)

const soundOn = ref(localStorage.getItem(SOUND_PREF_KEY) === '1')
const soundReady = ref(isUnlocked())
const supported = isSupported()

const pendingCount = ref(0)
const busyOrderNo = ref('')

let lastMaxId = Number(localStorage.getItem(LAST_ID_KEY) || '0')
/** order_no -> revision，用来发现"她改了单" */
const knownRevision = ref<Record<string, number>>({})
let pollTimer: number | null = null
let stopFlash: number | null = null

const hasUnread = computed(() => orders.value.some((o) => o.is_new))

/* ------------------------------------------------------------------ 加载 */

async function loadList(showSpinner = false): Promise<void> {
  if (showSpinner) refreshing.value = true
  try {
    const data = await api.fetchAdminOrders({ status: status.value, limit: 100 })
    orders.value = data.orders
    pendingCount.value = data.pending_ids.length

    for (const o of data.orders) {
      knownRevision.value[o.order_no] = o.revision ?? 0
    }

    if (data.orders.length) {
      const maxId = Math.max(...data.orders.map((o) => o.id))
      if (maxId > lastMaxId) {
        lastMaxId = maxId
        localStorage.setItem(LAST_ID_KEY, String(maxId))
      }
    }
  } catch (e) {
    if (showSpinner) showToast(errorMessage(e))
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

/**
 * 5 秒轮询：既拉新订单，也检查已有订单的 revision 变化（改单）。
 */
async function poll(): Promise<void> {
  if (document.visibilityState !== 'visible') return
  try {
    const data = await api.fetchNewOrders(lastMaxId)
    let newCount = 0
    let modifiedCount = 0

    for (const incoming of data.orders) {
      const prevRev = knownRevision.value[incoming.order_no]
      const rev = incoming.revision ?? 0

      if (prevRev === undefined) {
        // 从没见过的订单号
        newCount += 1
      } else if (rev > prevRev && incoming.active) {
        // 她改了单（cooking 之后不可能改，双保险判断 active）
        modifiedCount += 1
      }
      knownRevision.value[incoming.order_no] = rev
    }

    if (data.max_id > lastMaxId) {
      lastMaxId = data.max_id
      localStorage.setItem(LAST_ID_KEY, String(lastMaxId))
    }

    if (newCount || modifiedCount) {
      playAlert(newCount, modifiedCount)
      await loadList()
    }
  } catch {
    /* 轮询失败静默，下一轮继续 */
  }
}

function playAlert(newCount: number, modifiedCount: number): void {
  if (newCount && modifiedCount) {
    startTitleFlash(`🔔 ${newCount} 新单 + ${modifiedCount} 改单！`)
    if (soundOn.value) playMixed()
  } else if (newCount) {
    startTitleFlash(`🔔 ${newCount} 个新订单！`)
    if (soundOn.value) playNewOrder()
  } else {
    startTitleFlash(`✏️ 她改了 ${modifiedCount} 单！`)
    if (soundOn.value) playModified()
  }

  vibrate(newCount ? [240, 90, 240] : [140, 70, 140])
  showToast({
    message: newCount ? `🔔 有 ${newCount} 个新订单！` : `✏️ 她改了 ${modifiedCount} 个订单`,
    duration: 2200,
  })

  if (stopFlash !== null) window.clearTimeout(stopFlash)
  stopFlash = window.setTimeout(() => stopTitleFlash(), 12000)
}

/* -------------------------------------------------------------- 提示音开关 */

async function toggleSound(): Promise<void> {
  if (!supported) {
    showToast('这个浏览器不支持播放声音')
    return
  }
  if (soundOn.value) {
    soundOn.value = false
    localStorage.setItem(SOUND_PREF_KEY, '0')
    stopTitleFlash()
    showToast('已关闭提示音')
    return
  }

  const ok = await unlock()
  soundReady.value = ok
  if (!ok) {
    showToast('浏览器不让播声音，检查一下静音开关')
    return
  }
  soundOn.value = true
  localStorage.setItem(SOUND_PREF_KEY, '1')
  playNewOrder()
  showToast('提示音已开启 ♥')
}

/* -------------------------------------------------------------- 订单操作 */

async function advance(order: Order): Promise<void> {
  const next = order.next_status
  if (!next) return
  busyOrderNo.value = order.order_no
  try {
    const result = await api.updateOrderStatus(order.order_no, next as OrderStatus)
    const idx = orders.value.findIndex((o) => o.order_no === order.order_no)
    if (idx >= 0) orders.value[idx] = result.order
    if (result.order.status === 'served' || result.order.status === 'cancelled') {
      knownRevision.value[order.order_no] = result.order.revision ?? 0
    }
    showToast(result.message)
    if (!hasUnread.value) stopTitleFlash()
    await loadList()
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    busyOrderNo.value = ''
  }
}

const cancelOpen = ref(false)
const cancelTarget = ref<Order | null>(null)
const cancelReason = ref('')

function openCancel(order: Order): void {
  cancelTarget.value = order
  cancelReason.value = ''
  cancelOpen.value = true
}

async function confirmCancel(): Promise<void> {
  const order = cancelTarget.value
  if (!order) return

  busyOrderNo.value = order.order_no
  try {
    const result = await api.updateOrderStatus(order.order_no, 'cancelled', cancelReason.value.trim())
    const idx = orders.value.findIndex((o) => o.order_no === order.order_no)
    if (idx >= 0) orders.value[idx] = result.order
    showToast(result.message)
    cancelOpen.value = false
    await loadList()
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    busyOrderNo.value = ''
  }
}

async function markAllSeen(): Promise<void> {
  try {
    await api.markOrdersSeen()
    stopTitleFlash()
    await loadList()
    showToast('已标记为看过')
  } catch (e) {
    showToast(errorMessage(e))
  }
}

async function runAutoCancel(): Promise<void> {
  try {
    const result = await api.triggerAutoCancel()
    showToast(result.message)
    await loadList()
  } catch (e) {
    showToast(errorMessage(e))
  }
}

async function copyOrderNo(order: Order): Promise<void> {
  const text = `订单 ${order.order_no} 已经${order.status_name}啦～`
  try {
    await navigator.clipboard.writeText(text)
    showToast('已复制，去发给她吧')
  } catch {
    showToast(text)
  }
}

/* -------------------------------------------------------------- 生命周期 */

onMounted(async () => {
  document.title = '订单看板 · 爱心小食堂'
  try {
    filters.value = await api.fetchOrderFilters()
  } catch {
    /* 用默认筛选也能跑 */
  }
  await loadList()
  pollTimer = window.setInterval(() => void poll(), 5000)

  // 切回页面时立刻对一次，别等下一个 5 秒
  document.addEventListener('visibilitychange', onVisibility)
})

function onVisibility(): void {
  if (document.visibilityState === 'visible') void poll()
}

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearInterval(pollTimer)
  if (stopFlash !== null) window.clearTimeout(stopFlash)
  document.removeEventListener('visibilitychange', onVisibility)
  stopTitleFlash()
})
</script>

<template>
  <div class="page page--with-tabbar">
    <!-- 顶栏 -->
    <header class="ahead">
      <div class="ahead__top">
        <div>
          <h1 class="ahead__title">订单看板</h1>
          <p class="ahead__sub">
            {{ auth.username || '主厨' }} · 每 5 秒自动检查
            <span v-if="pendingCount" class="ahead__pending">待接单 {{ pendingCount }}</span>
          </p>
        </div>
        <button class="ahead__logout" @click="auth.logout(); router.replace('/admin/login')">
          退出
        </button>
      </div>

      <!-- 提示音 -->
      <button class="sound" :class="{ 'sound--on': soundOn }" @click="toggleSound">
        <span class="sound__icon">{{ soundOn ? '🔔' : '🔕' }}</span>
        <span class="grow sound__text">
          <strong>{{ soundOn ? '提示音已开启' : '开启提示音' }}</strong>
          <small v-if="!soundOn">浏览器要求先点一下才能响</small>
          <small v-else-if="soundReady">新订单会叮咚提醒你</small>
        </span>
        <van-switch :model-value="soundOn" size="20" @click.stop="toggleSound" />
      </button>

      <!-- 筛选 -->
      <div class="filters">
        <button
          v-for="opt in filters"
          :key="opt.value"
          class="filters__item"
          :class="{ 'is-active': status === opt.value }"
          @click="status = opt.value; loadList()"
        >
          {{ opt.label }}
        </button>
      </div>

      <div class="ahead__tools">
        <span v-if="hasUnread" class="ahead__seen" @click="markAllSeen">全部标记为看过</span>
        <span class="ahead__tool" @click="runAutoCancel">清理超时单</span>
        <span class="ahead__tool" @click="loadList(true)">刷新</span>
      </div>
    </header>

    <!-- 加载 -->
    <div v-if="loading" class="stack" style="padding: var(--sp-4)">
      <div v-for="i in 3" :key="i" class="skeleton" style="height: 150px; border-radius: var(--r-lg)" />
    </div>

    <!-- 空 -->
    <div v-else-if="!orders.length" class="empty">
      <div class="empty__emoji">🍽️</div>
      <p>{{ status === 'all' ? '还没有任何订单' : '这个状态下没有订单' }}</p>
      <p class="t-sub">她下单之后这里会立刻响起来</p>
    </div>

    <!-- 订单列表 -->
    <div v-else class="olist" :class="{ 'is-refreshing': refreshing }">
      <article
        v-for="order in orders"
        :key="order.order_no"
        class="ocard"
        :class="{
          'ocard--new': order.is_new,
          'ocard--active': order.active,
          'ocard--done': !order.active,
        }"
      >
        <!-- 头部 -->
        <div class="ocard__head">
          <span class="status-pill" :class="`status-pill--${order.status}`">
            {{ statusMeta(order.status).emoji }} {{ order.status_name }}
          </span>
          <span v-if="order.is_new" class="ocard__badge">NEW</span>
          <span v-if="order.revision" class="ocard__rev">改过 {{ order.revision }} 次</span>
          <span class="grow" />
          <button class="ocard__copy" @click="copyOrderNo(order)">复制单号</button>
        </div>

        <!-- 单号 / 时间 -->
        <div class="ocard__no">{{ order.order_no }}</div>
        <div class="ocard__times">
          <span>下单 {{ smartTime(order.created_at) }}</span>
          <span v-if="order.expected_time" class="ocard__expect">
            期望 {{ expectedTimeText(order.expected_time) }}
          </span>
        </div>
        <div
          v-if="order.active && (order.elapsed_minutes ?? 0) >= 30"
          class="ocard__warn"
          :class="{ 'ocard__warn--long': (order.elapsed_minutes ?? 0) >= 90 }"
        >
          ⏰ {{ elapsedText(order.elapsed_minutes) }}，别忘了推进状态
        </div>

        <!-- 许愿 -->
        <div v-if="order.dish_request" class="ocard__wish">
          <span class="ocard__wish-label">她说想吃别的</span>
          <span class="ocard__wish-text">{{ order.dish_request }}</span>
        </div>

        <!-- 菜品 -->
        <ul class="ocard__items">
          <li v-for="item in order.items" :key="item.id">
            <span class="ocard__item-name">{{ item.dish_name }}</span>
            <span v-if="item.item_note" class="ocard__item-note">{{ item.item_note }}</span>
            <span class="ocard__item-qty">×{{ item.quantity }}</span>
          </li>
        </ul>

        <!-- 备注 -->
        <div v-if="order.customer_note" class="ocard__note">
          <span class="ocard__note-label">备注</span>
          {{ order.customer_note }}
        </div>

        <!-- 取消原因 -->
        <div v-if="order.status === 'cancelled'" class="ocard__cancel">
          取消原因：{{ order.cancel_reason || '未填写' }}
        </div>

        <!-- 底部信息 -->
        <div class="ocard__foot">
          <span class="ocard__total">共 {{ order.total_items }} 份</span>
          <span v-if="order.accepted_at" class="t-weak">接单 {{ smartTime(order.accepted_at) }}</span>
          <span v-if="order.completed_at" class="t-weak">
            完成 {{ smartTime(order.completed_at) }}
          </span>
        </div>

        <!-- 操作 -->
        <div v-if="order.active" class="ocard__actions">
          <van-button
            v-if="order.next_status"
            round
            type="primary"
            class="grow"
            :loading="busyOrderNo === order.order_no"
            @click="advance(order)"
          >
            {{ nextActionIcon(order.next_status) }} {{ nextActionLabel(order.next_status) }}
          </van-button>
          <van-button
            round
            plain
            class="ocard__cancelbtn"
            :disabled="busyOrderNo === order.order_no"
            @click="openCancel(order)"
          >
            取消
          </van-button>
        </div>
      </article>

      <div class="heart-divider">♥ 一共 {{ orders.length }} 单 ♥</div>
    </div>

    <!-- 取消订单 -->
    <van-popup v-model:show="cancelOpen" position="bottom" round>
      <div v-if="cancelTarget" class="cancel-sheet">
        <h3 class="cancel-sheet__title">取消 {{ cancelTarget.order_no }}？</h3>
        <p class="cancel-sheet__tip">
          取消后她会看到原因。不填的话默认写「主厨取消了这一单」。
        </p>
        <van-field
          v-model="cancelReason"
          placeholder="比如：家里没这个菜了 / 今天太晚啦"
          maxlength="200"
          type="textarea"
          rows="2"
          autosize
          class="cancel-sheet__field"
        />
        <div class="cancel-sheet__actions">
          <van-button round plain block @click="cancelOpen = false">不取消</van-button>
          <van-button
            round
            type="danger"
            block
            :loading="busyOrderNo === cancelTarget.order_no"
            @click="confirmCancel"
          >
            确定取消
          </van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<style scoped>
@import '@/styles/order.css';

/* ---- 顶栏 ---- */
.ahead {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: calc(var(--sp-4) + var(--safe-top)) var(--sp-4) var(--sp-4);
  background: linear-gradient(165deg, var(--c-primary-200), var(--c-bg) 92%);
  border-bottom-left-radius: var(--r-xl);
  border-bottom-right-radius: var(--r-xl);
}

.ahead__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
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
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.ahead__pending {
  padding: 1px 7px;
  border-radius: var(--r-pill);
  background: var(--c-danger);
  color: #fff;
  font-weight: 600;
}

.ahead__logout {
  flex: 0 0 auto;
  padding: 4px 10px;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, 0.7);
  color: var(--c-text-sub);
  font-size: var(--fs-xs);
  cursor: pointer;
}

/* ---- 提示音 ---- */
.sound {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  margin-top: var(--sp-3);
  padding: var(--sp-3);
  border: 1px dashed var(--c-border-strong);
  border-radius: var(--r-md);
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
  cursor: pointer;
}

.sound--on {
  border-style: solid;
  border-color: var(--c-primary-300);
  background: var(--c-bg-card);
}

.sound__icon {
  font-size: 22px;
}

.sound__text {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.sound__text strong {
  font-size: var(--fs-md);
}

.sound__text small {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

/* ---- 筛选 ---- */
.filters {
  display: flex;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
  overflow-x: auto;
  scrollbar-width: none;
  padding-bottom: 2px;
}

.filters::-webkit-scrollbar {
  display: none;
}

.filters__item {
  flex: 0 0 auto;
  padding: 4px 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-bg-card);
  color: var(--c-text-sub);
  font-size: var(--fs-sm);
  white-space: nowrap;
  cursor: pointer;
}

.filters__item.is-active {
  background: linear-gradient(135deg, var(--c-primary-400), var(--c-primary-600));
  border-color: transparent;
  color: #fff;
  font-weight: 600;
}

.ahead__tools {
  display: flex;
  gap: var(--sp-4);
  margin-top: var(--sp-3);
  font-size: var(--fs-xs);
}

.ahead__seen {
  color: var(--c-danger);
  font-weight: 600;
  cursor: pointer;
}

.ahead__tool {
  color: var(--c-primary-600);
  cursor: pointer;
}

/* ---- 列表 ---- */
.olist {
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  transition: opacity var(--dur) var(--ease);
}

.olist.is-refreshing {
  opacity: 0.75;
}

.ocard {
  padding: var(--sp-3) var(--sp-4);
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-sm);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* 新订单高亮：不刺眼但一眼能看到 */
.ocard--new {
  border-color: var(--c-primary-400);
  box-shadow: 0 0 0 3px var(--c-primary-100), var(--sh-md);
  animation: new-glow 1.8s var(--ease) infinite;
}

@keyframes new-glow {
  0%,
  100% {
    box-shadow: 0 0 0 3px var(--c-primary-100), var(--sh-md);
  }
  50% {
    box-shadow: 0 0 0 6px var(--c-primary-100), var(--sh-md);
  }
}

.ocard--active {
  background: linear-gradient(170deg, var(--c-primary-50), var(--c-bg-card) 45%);
}

.ocard--done {
  opacity: 0.86;
}

.ocard__head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.ocard__badge {
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: var(--c-danger);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.ocard__rev {
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: var(--c-accent-cream);
  color: #8a5a00;
  font-size: 10px;
  font-weight: 600;
}

.ocard__copy {
  border: none;
  background: transparent;
  color: var(--c-primary-600);
  font-size: var(--fs-xs);
  cursor: pointer;
  padding: 0;
}

.ocard__no {
  font-size: var(--fs-md);
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--c-text);
}

.ocard__times {
  display: flex;
  gap: var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.ocard__expect {
  color: var(--c-primary-600);
  font-weight: 600;
}

.ocard__warn {
  padding: 4px 9px;
  border-radius: var(--r-sm);
  background: #fff6e5;
  color: #a25b00;
  font-size: var(--fs-xs);
}

.ocard__warn--long {
  background: #ffeded;
  color: #b3261e;
  font-weight: 600;
}

/* ---- 许愿：单独突出 ---- */
.ocard__wish {
  display: flex;
  gap: var(--sp-2);
  align-items: baseline;
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-md);
  background: linear-gradient(135deg, var(--c-primary-100), var(--c-accent-cream));
  border: 1px solid var(--c-primary-200);
}

.ocard__wish-label {
  flex: 0 0 auto;
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--c-primary-700);
}

.ocard__wish-text {
  font-size: var(--fs-md);
  color: var(--c-primary-700);
  font-weight: 500;
  word-break: break-all;
}

/* ---- 菜品 ---- */
.ocard__items {
  list-style: none;
  margin: 2px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ocard__items li {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  font-size: var(--fs-md);
}

.ocard__item-name {
  flex: 0 1 auto;
}

.ocard__item-note {
  flex: 1;
  font-size: var(--fs-xs);
  color: var(--c-primary-600);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ocard__item-qty {
  margin-left: auto;
  font-weight: 600;
  color: var(--c-primary-strong);
}

.ocard__note {
  padding: 4px 9px;
  border-radius: var(--r-sm);
  background: var(--c-bg-sunk);
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
}

.ocard__note-label {
  font-weight: 600;
  color: var(--c-text);
}

.ocard__cancel {
  font-size: var(--fs-xs);
  color: var(--c-danger);
}

.ocard__foot {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding-top: var(--sp-2);
  border-top: 1px dashed var(--c-border);
  font-size: var(--fs-xs);
}

.ocard__total {
  font-weight: 600;
  color: var(--c-text);
}

.ocard__actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-2);
}

.ocard__cancelbtn {
  flex: 0 0 auto;
  min-width: 72px;
}

/* ---- 取消弹层 ---- */
.cancel-sheet {
  padding: var(--sp-5) var(--sp-4) calc(var(--sp-5) + var(--safe-bottom));
}

.cancel-sheet__title {
  margin: 0;
  font-size: var(--fs-lg);
  text-align: center;
}

.cancel-sheet__tip {
  margin: var(--sp-2) 0 var(--sp-4);
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
  text-align: center;
  line-height: 1.5;
}

.cancel-sheet__field {
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-bg-sunk);
}

.cancel-sheet__actions {
  display: flex;
  gap: var(--sp-3);
  margin-top: var(--sp-4);
}
</style>
