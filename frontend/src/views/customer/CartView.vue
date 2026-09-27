<script setup lang="ts">
/**
 * 购物车 / 下单页。
 *
 * 页面上会同时显示三个"可能拦住下单"的状态，并且在下单前就告诉她原因：
 *   1. 店铺休息中
 *   2. 已有未完成订单（同时只允许一单）
 *   3. 购物车里有菜已下架
 * 提前显示比提交后弹错误友好得多。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import CustomerTabbar from '@/components/CustomerTabbar.vue'
import { useCartStore } from '@/stores/cart'
import { useShopStore } from '@/stores/shop'
import { useCustomerOrderStore } from '@/stores/customerOrders'
import * as api from '@/api/customer'
import { currentHHMM } from '@/utils/time'

const cart = useCartStore()
const shop = useShopStore()
const orders = useCustomerOrderStore()
const router = useRouter()

const submitting = ref(false)
const showTimePicker = ref(false)

/** van-picker 需要 [['18','19',...],['00','05',...]] 这种二维结构 */
const hourOptions = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const minuteOptions = Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, '0'))
const timeColumns = [
  hourOptions.map((h) => ({ text: `${h} 时`, value: h })),
  minuteOptions.map((m) => ({ text: `${m} 分`, value: m })),
]

const activeOrder = computed(() => orders.activeOrder)
const blocked = computed(() => !shop.businessOpen || Boolean(activeOrder))
const missing = computed(() => cart.missingDishIds)

const blockReason = computed(() => {
  if (!shop.businessOpen) return shop.closedTip
  if (activeOrder.value) {
    return `还有一单没做完（${activeOrder.value.order_no} · ${activeOrder.value.status_name}）`
  }
  return ''
})

onMounted(async () => {
  await shop.load()
  try {
    await orders.refreshActive()
  } catch {
    /* 忽略：没有进行中订单 */
  }
  if (!cart.expectedTime) cart.expectedTime = currentHHMM(40)
})

function onTimeConfirm(payload: { selectedOptions: Array<{ value: string }> }): void {
  const [h, m] = payload.selectedOptions.map((o) => o.value)
  cart.expectedTime = `${h}:${m}`
  showTimePicker.value = false
}

async function clearAll(): Promise<void> {
  try {
    await showConfirmDialog({
      title: '清空购物车',
      message: '把选的菜都去掉吗？',
      confirmButtonText: '清空',
      cancelButtonText: '再想想',
    })
    cart.clear()
    showToast('已清空')
  } catch {
    /* 取消 */
  }
}

async function removeLine(dishId: number, name: string): Promise<void> {
  try {
    await showConfirmDialog({
      title: '去掉这道菜',
      message: `不要「${name}」了吗？`,
      confirmButtonText: '去掉',
      cancelButtonText: '留着',
    })
    cart.remove(dishId)
  } catch {
    /* 取消 */
  }
}

async function submit(): Promise<void> {
  if (submitting.value) return

  if (cart.isEmpty) {
    showToast('购物车是空的')
    return
  }
  if (!shop.businessOpen) {
    showToast(shop.closedTip)
    return
  }
  if (activeOrder.value) {
    showToast('还有一单没做完呢')
    return
  }
  if (missing.value.length) {
    showToast('有菜已经下架了，请去掉后再下单')
    return
  }
  if (cart.note.length > 200) {
    showToast('备注最多 200 字')
    return
  }

  submitting.value = true
  try {
    const result = await api.createOrder({
      items: cart.toOrderItems(),
      customer_note: cart.note,
      dish_request: cart.dishRequest,
      expected_time: cart.expectedTime,
    })

    orders.remember(result.order)
    orders.markSeen(result.order)
    cart.clearDishes()
    cart.note = ''
    cart.dishRequest = ''

    showToast({ message: '下单成功，等主厨接单～', duration: 1400 })
    router.replace(`/order-success/${result.order.order_no}`)
  } catch (e) {
    showToast(e instanceof Error ? e.message : '下单失败')
  } finally {
    submitting.value = false
  }
}

function goActive(): void {
  if (activeOrder.value) router.push(`/order/${activeOrder.value.order_no}`)
}
</script>

<template>
  <div class="page page--with-tabbar page--with-actionbar">
    <van-nav-bar title="购物车" left-arrow @click-left="router.back()">
      <template #right>
        <span v-if="!cart.isEmpty" class="nav-clear" @click="clearAll">清空</span>
      </template>
    </van-nav-bar>

    <!-- 阻拦提示 -->
    <div v-if="blocked" class="block" :class="{ 'block--order': Boolean(activeOrder) }">
      <span class="block__emoji">{{ activeOrder ? '🍳' : '😴' }}</span>
      <div class="grow">
        <strong>{{ blockReason }}</strong>
        <p class="t-sub">{{ activeOrder ? '可以先看看这一单做到哪一步了' : '可以先挑好菜，开火后就能下单' }}</p>
      </div>
      <van-button v-if="activeOrder" size="small" round type="primary" @click="goActive">
        看订单
      </van-button>
    </div>

    <!-- 空购物车 -->
    <div v-if="cart.isEmpty" class="empty">
      <div class="empty__emoji">🛒</div>
      <p>购物车还是空的</p>
      <van-button round size="small" type="primary" @click="router.push('/')">
        去挑几道菜
      </van-button>
    </div>

    <template v-else>
      <!-- 菜品清单 -->
      <section class="section-title">
        已选菜品
        <span class="section-title__extra">{{ cart.totalCount }} 份</span>
      </section>

      <div class="lines">
        <article
          v-for="line in cart.lines"
          :key="line.dish_id"
          class="line"
          :class="{ 'line--missing': missing.includes(line.dish_id) }"
        >
          <div class="line__media">
            <img v-if="line.image_url" :src="line.image_url" :alt="line.name" loading="lazy" />
            <div v-else class="line__fallback">♥</div>
          </div>

          <div class="line__body">
            <div class="row row--between">
              <h3 class="line__name ellipsis">{{ line.name }}</h3>
              <button class="line__del" aria-label="删除" @click="removeLine(line.dish_id, line.name)">
                ×
              </button>
            </div>

            <p v-if="missing.includes(line.dish_id)" class="line__warn">这道菜已下架，请去掉后再下单</p>

            <van-field
              :model-value="line.item_note"
              placeholder="这道菜的要求（可不填）"
              maxlength="100"
              class="line__note"
              @update:model-value="(v: string) => cart.setItemNote(line.dish_id, v)"
            />

            <div class="line__foot">
              <span class="line__cat">{{ line.category }}</span>
              <van-stepper
                :model-value="line.quantity"
                min="0"
                max="99"
                integer
                button-size="24"
                @plus="cart.increase(line.dish_id)"
                @minus="cart.decrease(line.dish_id)"
              />
            </div>
          </div>
        </article>
      </div>

      <!-- 订单信息 -->
      <section class="section-title">
        订单信息
        <span class="section-title__extra">选填</span>
      </section>

      <div class="card card__pad form">
        <van-field
          v-model="cart.note"
          label="备注"
          placeholder="少辣、不要葱、多放肉…"
          maxlength="200"
          show-word-limit
          type="textarea"
          rows="2"
          autosize
        />

        <van-field
          v-model="cart.dishRequest"
          label="我想吃别的"
          placeholder="菜单里没有的，比如：想吃糖醋排骨"
          maxlength="200"
          show-word-limit
          type="textarea"
          rows="2"
          autosize
        />

        <van-field
          :model-value="cart.expectedTime"
          label="期望用餐时间"
          placeholder="比如 18:30"
          readonly
          is-link
          @click="showTimePicker = true"
        />

        <p class="form__hint">
          「我想吃别的」会单独告诉主厨，就算菜单里没有他也能看到 ♥
        </p>
      </div>

      <div class="heart-divider">♥</div>
    </template>

    <!-- 底部提交：叠在底部导航之上，不遮挡 tab -->
    <div v-if="!cart.isEmpty" class="actionbar actionbar--above-tabbar">
      <div class="grow">
        <div class="submit__count">共 {{ cart.totalCount }} 份</div>
        <div class="submit__sub">约需 {{ cart.estimatedMinutes }} 分钟</div>
      </div>
      <van-button
        round
        type="primary"
        class="submit__btn"
        :loading="submitting"
        :disabled="blocked || missing.length > 0"
        @click="submit"
      >
        {{ blocked ? (shop.businessOpen ? '有单在做' : '休息中') : '提交订单' }}
      </van-button>
    </div>

    <!-- 时间选择 -->
    <van-popup v-model:show="showTimePicker" position="bottom" round>
      <van-picker
        title="期望用餐时间"
        :columns="timeColumns"
        @confirm="onTimeConfirm"
        @cancel="showTimePicker = false"
      />
    </van-popup>

    <CustomerTabbar />
  </div>
</template>

<style scoped>
.nav-clear {
  color: var(--c-primary-strong);
  font-size: var(--fs-md);
  cursor: pointer;
}

/* ---- 阻拦提示 ---- */
.block {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin: var(--sp-3) var(--sp-4) 0;
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--r-lg);
  background: var(--c-bg-sunk);
  border: 1px dashed var(--c-border-strong);
}

.block--order {
  background: linear-gradient(135deg, var(--c-primary-500), var(--c-primary-300));
  border: none;
  color: #fff;
}

.block--order .t-sub {
  color: rgba(255, 255, 255, 0.85);
}

.block p {
  margin: 0;
}

.block__emoji {
  font-size: 24px;
}

/* ---- 明细 ---- */
.lines {
  padding: 0 var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.line {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-sm);
}

.line--missing {
  border-color: var(--c-danger);
  background: #fff5f5;
}

.line__media {
  width: 74px;
  height: 74px;
  flex: 0 0 74px;
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--c-primary-50);
}

.line__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.line__fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  color: var(--c-primary-300);
}

.line__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.line__name {
  margin: 0;
  font-size: var(--fs-lg);
  font-weight: 600;
}

.line__del {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  border: none;
  border-radius: 50%;
  background: var(--c-bg-sunk);
  color: var(--c-text-sub);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.line__warn {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--c-danger);
}

.line__note {
  padding: 0;
  background: transparent;
  font-size: var(--fs-sm);
}

.line__note :deep(.van-field__control) {
  background: var(--c-bg-sunk);
  border-radius: var(--r-sm);
  padding: 5px 9px;
  font-size: var(--fs-sm);
}

.line__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.line__cat {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

/* ---- 表单 ---- */
.form {
  margin: 0 var(--sp-4);
}

.form :deep(.van-field) {
  padding-left: 0;
  padding-right: 0;
}

.form__hint {
  margin: var(--sp-2) 0 0;
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
  line-height: 1.5;
}

/* ---- 提交条 ---- */
.submit__count {
  font-size: var(--fs-lg);
  font-weight: 600;
}

.submit__sub {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.submit__btn {
  min-width: 128px;
  flex: 0 0 auto;
}
</style>
