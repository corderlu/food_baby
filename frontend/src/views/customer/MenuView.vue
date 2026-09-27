<script setup lang="ts">
/**
 * 顾客端首页：店铺信息 + 今日推荐 + 分类菜单。
 *
 * 两个实现要点：
 * 1. 分类 tab 和滚动位置双向联动。用 IntersectionObserver 而不是 scrollTop 计算，
 *    手机上更稳（惯性滚动时 scrollTop 事件会丢）。
 * 2. 页面每 60 秒静默刷新一次菜单与营业状态，
 *    这样你在后台改了菜或切换营业状态，她不用手动刷新也能看到。
 */
import { computed, onActivated, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import DishCard from '@/components/DishCard.vue'
import CustomerTabbar from '@/components/CustomerTabbar.vue'
import SpicyLevel from '@/components/SpicyLevel.vue'
import { useShopStore } from '@/stores/shop'
import { useCartStore } from '@/stores/cart'
import { useCustomerOrderStore } from '@/stores/customerOrders'
import { todayText } from '@/utils/time'
import type { Dish } from '@/types/api'

const shop = useShopStore()
const cart = useCartStore()
const orders = useCustomerOrderStore()
const router = useRouter()

const activeCategory = ref('')
const announcementClosed = ref(false)
const detailDish = ref<Dish | null>(null)
const detailNote = ref('')
const loading = ref(true)
const failed = ref(false)

let pollTimer: number | null = null
let observer: IntersectionObserver | null = null

/* ------------------------------------------------------------------ 数据 */

async function load(silent = false): Promise<void> {
  try {
    await shop.load(silent)
    failed.value = false
    if (!activeCategory.value && shop.categories.length) {
      activeCategory.value = shop.categories[0]
    }
  } catch {
    failed.value = true
  } finally {
    if (!silent) loading.value = false
  }
}

/** 类目锚点：进入视口就把 tab 切过去 */
function setupObserver(): void {
  if (typeof IntersectionObserver === 'undefined') return
  observer?.disconnect()
  observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      const cat = visible?.target.getAttribute('data-category')
      if (cat) activeCategory.value = cat
    },
    { rootMargin: '-120px 0px -60% 0px', threshold: [0.1, 0.5, 1] },
  )
  document.querySelectorAll('[data-category]').forEach((el) => observer?.observe(el))
}

function scrollToCategory(cat: string): void {
  activeCategory.value = cat
  const el = document.querySelector(`[data-category="${cat}"]`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/* ------------------------------------------------------------ 交互行为 */

function addToCart(dish: Dish): void {
  cart.add(dish, 1)
  showToast({ message: `已加 ${dish.name}`, duration: 900 })
  if ('vibrate' in navigator) {
    try {
      navigator.vibrate(12)
    } catch {
      /* 忽略 */
    }
  }
}

function decrease(dish: Dish): void {
  cart.decrease(dish.id)
}

function openDetail(dish: Dish): void {
  detailDish.value = dish
  detailNote.value = cart.snapshot.find((s) => s.dish_id === dish.id)?.item_note ?? ''
}

function confirmDetail(): void {
  const dish = detailDish.value
  if (!dish) return
  if (cart.quantityOf(dish.id) === 0) cart.add(dish, 1)
  cart.setItemNote(dish.id, detailNote.value)
  showToast({ message: '记下啦～', duration: 900 })
  detailDish.value = null
}

function goCart(): void {
  router.push('/cart')
}

function goActiveOrder(): void {
  if (orders.activeOrder) router.push(`/order/${orders.activeOrder.order_no}`)
}

/* ------------------------------------------------------------- 生命周期 */

onMounted(async () => {
  await load()
  // 等 DOM 渲染出来再挂观察器
  requestAnimationFrame(() => setTimeout(setupObserver, 120))

  try {
    await orders.refreshActive()
  } catch {
    /* 没有进行中的订单是正常情况 */
  }

  pollTimer = window.setInterval(() => {
    // 详情弹窗开着时不要重排列表，避免被"顶掉"
    if (document.visibilityState === 'visible' && !detailDish.value) void load(true)
  }, 60000)
})

onActivated(() => {
  setupObserver()
})

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearInterval(pollTimer)
  observer?.disconnect()
})

const visibleGroups = computed(() => shop.grouped.filter((g) => g.dishes.length > 0))
</script>

<template>
  <div class="page page--with-tabbar">
    <!-- ---------------- 店铺头部 ---------------- -->
    <header class="hero">
      <div class="hero__top">
        <div class="hero__title">
          <span class="hero__heart">♥</span>
          <h1>{{ shop.shopName }}</h1>
        </div>
        <span class="hero__status" :class="shop.businessOpen ? 'is-open' : 'is-closed'">
          <i class="hero__dot" />
          {{ shop.businessOpen ? '营业中' : '休息中' }}
        </span>
      </div>

      <p class="hero__welcome">{{ shop.shop?.welcome_text || '想吃什么就点什么 ♥' }}</p>
      <p class="hero__date">{{ todayText() }}</p>
    </header>

    <!-- ---------------- 公告 ---------------- -->
    <div v-if="shop.shop?.announcement && !announcementClosed" class="notice">
      <van-notice-bar
        :text="shop.shop.announcement"
        left-icon="volume-o"
        background="var(--c-primary-soft)"
        color="var(--c-primary-700)"
        :scrollable="shop.shop.announcement.length > 18"
      />
      <button class="notice__close" aria-label="关闭公告" @click="announcementClosed = true">×</button>
    </div>

    <!-- ---------------- 休息提示 ---------------- -->
    <div v-if="!shop.businessOpen" class="closed-tip">
      <span class="closed-tip__emoji">😴</span>
      <div>
        <strong>{{ shop.closedTip }}</strong>
        <p class="t-sub">菜单还能看，等主厨开火就能下单啦</p>
      </div>
    </div>

    <!-- ---------------- 进行中的订单 ---------------- -->
    <button v-if="orders.activeOrder" class="active-order" @click="goActiveOrder">
      <span class="active-order__emoji">🍳</span>
      <span class="grow">
        <span class="active-order__title">
          你有一单正在做 · {{ orders.activeOrder.status_name }}
        </span>
        <span class="active-order__no">{{ orders.activeOrder.order_no }}</span>
      </span>
      <span class="active-order__arrow">›</span>
    </button>

    <!-- ---------------- 骨架 ---------------- -->
    <div v-if="loading" class="skeleton-list">
      <div v-for="i in 4" :key="i" class="skeleton-row">
        <div class="skeleton skeleton-row__img" />
        <div class="grow stack">
          <div class="skeleton" style="height: 16px; width: 45%" />
          <div class="skeleton" style="height: 12px; width: 80%" />
          <div class="skeleton" style="height: 12px; width: 30%" />
        </div>
      </div>
    </div>

    <!-- ---------------- 加载失败 ---------------- -->
    <div v-else-if="failed" class="empty">
      <div class="empty__emoji">🥲</div>
      <p>菜单没加载出来</p>
      <van-button round size="small" type="primary" @click="load()">再试一次</van-button>
    </div>

    <template v-else>
      <!-- ---------------- 今日推荐 ---------------- -->
      <section v-if="shop.recommends.length" class="recommend">
        <div class="section-title">
          今日推荐
          <span class="section-title__extra">主厨特别想做的</span>
        </div>
        <div class="recommend__scroll">
          <article
            v-for="dish in shop.recommends"
            :key="dish.id"
            class="rcard"
            @click="openDetail(dish)"
          >
            <div class="rcard__media">
              <img v-if="dish.image_url" :src="dish.image_url" :alt="dish.name" loading="lazy" />
              <div v-else class="rcard__fallback">♥</div>
            </div>
            <h4 class="rcard__name ellipsis">{{ dish.name }}</h4>
            <div class="rcard__meta">
              <SpicyLevel :level="dish.spicy_level" />
              <span>⏱{{ dish.estimated_minutes }}分</span>
            </div>
            <button class="rcard__add" @click.stop="addToCart(dish)">加入</button>
          </article>
        </div>
      </section>

      <!-- ---------------- 分类 tab ---------------- -->
      <van-sticky :offset-top="0">
        <div class="catbar">
          <button
            v-for="cat in shop.categories"
            :key="cat"
            class="catbar__item"
            :class="{ 'is-active': activeCategory === cat }"
            @click="scrollToCategory(cat)"
          >
            {{ cat }}
          </button>
        </div>
      </van-sticky>

      <!-- ---------------- 分类菜单 ---------------- -->
      <section
        v-for="group in visibleGroups"
        :key="group.category"
        :data-category="group.category"
        class="cat-group"
      >
        <div class="section-title">{{ group.category }}</div>
        <div class="stack cat-group__list">
          <DishCard
            v-for="dish in group.dishes"
            :key="dish.id"
            :dish="dish"
            :quantity="cart.quantityOf(dish.id)"
            :is-recommend="shop.isRecommend(dish.id)"
            @add="addToCart"
            @decrease="decrease"
            @open="openDetail"
          />
        </div>
      </section>

      <div v-if="!visibleGroups.length" class="empty">
        <div class="empty__emoji">🍽️</div>
        <p>菜单还是空的，让主厨先添几道菜吧</p>
      </div>

      <div class="heart-divider">♥ 今天也要好好吃饭呀 ♥</div>
    </template>

    <!-- ---------------- 底部购物车条 ---------------- -->
    <transition name="slide-up">
      <div v-if="cart.totalCount > 0" class="actionbar actionbar--above-tabbar">
        <button class="cartbtn" @click="goCart">
          <span class="cartbtn__icon">🛒</span>
          <span class="cartbtn__badge">{{ cart.totalCount }}</span>
        </button>
        <div class="grow cartbar__info" @click="goCart">
          <span class="cartbar__count">已选 {{ cart.totalCount }} 份</span>
          <span class="cartbar__sub">约需 {{ cart.estimatedMinutes }} 分钟</span>
        </div>
        <van-button round type="primary" size="normal" class="cartbar__go" @click="goCart">
          去下单
        </van-button>
      </div>
    </transition>

    <!-- ---------------- 菜品详情 ---------------- -->
    <van-popup
      :show="Boolean(detailDish)"
      position="bottom"
      round
      :style="{ maxWidth: 'var(--page-max)', left: '50%', transform: 'translateX(-50%)' }"
      @update:show="(v: boolean) => !v && (detailDish = null)"
    >
      <div v-if="detailDish" class="detail">
        <div class="detail__media">
          <img v-if="detailDish.image_url" :src="detailDish.image_url" :alt="detailDish.name" />
          <div v-else class="detail__fallback">♥</div>
        </div>

        <div class="detail__body">
          <h3 class="detail__name">{{ detailDish.name }}</h3>
          <p v-if="detailDish.description" class="detail__desc">{{ detailDish.description }}</p>

          <div class="row" style="gap: var(--sp-3); flex-wrap: wrap">
            <SpicyLevel :level="detailDish.spicy_level" show-text />
            <span class="t-sub">⏱ 约 {{ detailDish.estimated_minutes }} 分钟</span>
            <span class="t-sub">{{ detailDish.category }}</span>
          </div>

          <div v-if="detailDish.tags.length" class="dish-tags">
            <span v-for="tag in detailDish.tags" :key="tag" class="dish-tag">{{ tag }}</span>
          </div>

          <van-field
            v-model="detailNote"
            label="这道菜的要求"
            placeholder="少放盐 / 多加辣 / 不要香菜…"
            maxlength="100"
            show-word-limit
            rows="1"
            autosize
            type="textarea"
            class="detail__field"
          />

          <div class="detail__foot">
            <van-stepper
              :model-value="cart.quantityOf(detailDish.id)"
              min="0"
              max="99"
              integer
              @plus="cart.increase(detailDish.id)"
              @minus="cart.decrease(detailDish.id)"
            />
            <van-button round type="primary" class="grow" @click="confirmDetail">
              {{ cart.quantityOf(detailDish.id) > 0 ? '确定' : '加入购物车' }}
            </van-button>
          </div>
        </div>

        <button class="detail__close" aria-label="关闭" @click="detailDish = null">×</button>
      </div>
    </van-popup>

    <CustomerTabbar />
  </div>
</template>

<style scoped>
/* ---------------- Hero ---------------- */
.hero {
  padding: calc(var(--sp-5) + var(--safe-top)) var(--sp-4) var(--sp-4);
  background: linear-gradient(
    165deg,
    var(--c-primary-200) 0%,
    var(--c-primary-100) 45%,
    var(--c-bg) 100%
  );
  border-bottom-left-radius: var(--r-xl);
  border-bottom-right-radius: var(--r-xl);
}

.hero__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}

.hero__title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-width: 0;
}

.hero__heart {
  color: var(--c-primary-600);
  font-size: 20px;
  animation: heart-beat 2.4s var(--ease) infinite;
}

.hero__title h1 {
  margin: 0;
  font-size: var(--fs-2xl);
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--c-primary-700);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hero__status {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 11px;
  border-radius: var(--r-pill);
  font-size: var(--fs-sm);
  font-weight: 600;
  background: #fff;
  box-shadow: var(--sh-sm);
}

.hero__status.is-open {
  color: var(--c-success);
}

.hero__status.is-closed {
  color: var(--c-text-sub);
}

.hero__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.hero__status.is-open .hero__dot {
  box-shadow: 0 0 0 3px rgba(75, 191, 135, 0.18);
}

.hero__welcome {
  margin: var(--sp-3) 0 0;
  font-size: var(--fs-md);
  color: var(--c-primary-700);
  opacity: 0.85;
}

.hero__date {
  margin: 2px 0 0;
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
}

/* ---------------- 公告 ---------------- */
.notice {
  position: relative;
  margin: var(--sp-4) var(--sp-4) 0;
  border-radius: var(--r-md);
  overflow: hidden;
}

.notice :deep(.van-notice-bar) {
  border-radius: var(--r-md);
  padding-right: 30px;
}

.notice__close {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--c-primary-600);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

/* ---------------- 休息提示 ---------------- */
.closed-tip {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin: var(--sp-4) var(--sp-4) 0;
  padding: var(--sp-3) var(--sp-4);
  background: var(--c-bg-sunk);
  border: 1px dashed var(--c-border-strong);
  border-radius: var(--r-md);
  font-size: var(--fs-md);
}

.closed-tip p {
  margin: 0;
}

.closed-tip__emoji {
  font-size: 26px;
}

/* ---------------- 进行中订单 ---------------- */
.active-order {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: calc(100% - var(--sp-4) * 2);
  margin: var(--sp-4) var(--sp-4) 0;
  padding: var(--sp-3) var(--sp-4);
  text-align: left;
  border: none;
  border-radius: var(--r-lg);
  background: linear-gradient(135deg, var(--c-primary-500), var(--c-primary-300));
  color: #fff;
  box-shadow: var(--sh-primary);
  cursor: pointer;
}

.active-order__emoji {
  font-size: 22px;
}

.active-order__title {
  display: block;
  font-size: var(--fs-md);
  font-weight: 600;
}

.active-order__no {
  display: block;
  font-size: var(--fs-xs);
  opacity: 0.85;
}

.active-order__arrow {
  font-size: 22px;
  opacity: 0.8;
}

/* ---------------- 骨架 ---------------- */
.skeleton-list {
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.skeleton-row {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
}

.skeleton-row__img {
  width: 96px;
  height: 96px;
  flex: 0 0 96px;
  border-radius: var(--r-md);
}

/* ---------------- 今日推荐 ---------------- */
.recommend__scroll {
  display: flex;
  gap: var(--sp-3);
  padding: 0 var(--sp-4) var(--sp-2);
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}

.recommend__scroll::-webkit-scrollbar {
  display: none;
}

.rcard {
  position: relative;
  flex: 0 0 132px;
  padding: var(--sp-2);
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  box-shadow: var(--sh-sm);
  cursor: pointer;
}

.rcard__media {
  width: 100%;
  height: 88px;
  border-radius: var(--r-sm);
  overflow: hidden;
  background: var(--c-primary-50);
}

.rcard__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.rcard__fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  color: var(--c-primary-300);
}

.rcard__name {
  margin: 6px 0 2px;
  font-size: var(--fs-md);
  font-weight: 600;
}

.rcard__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.rcard__add {
  position: absolute;
  right: 6px;
  top: 6px;
  padding: 2px 8px;
  border: none;
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: var(--fs-xs);
  box-shadow: var(--sh-sm);
  cursor: pointer;
}

.rcard__add:active {
  transform: scale(0.92);
}

/* ---------------- 分类条 ---------------- */
.catbar {
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  overflow-x: auto;
  scrollbar-width: none;
  background: rgba(255, 247, 250, 0.94);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--c-border);
}

.catbar::-webkit-scrollbar {
  display: none;
}

.catbar__item {
  flex: 0 0 auto;
  padding: 5px 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-bg-card);
  color: var(--c-text-sub);
  font-size: var(--fs-md);
  white-space: nowrap;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.catbar__item.is-active {
  background: linear-gradient(135deg, var(--c-primary-400), var(--c-primary-600));
  border-color: transparent;
  color: #fff;
  font-weight: 600;
  box-shadow: var(--sh-primary);
}

/* ---------------- 分类分组 ---------------- */
.cat-group {
  scroll-margin-top: 52px;
}

.cat-group__list {
  padding: 0 var(--sp-4);
}

/* ---------------- 购物车条 ---------------- */
.cartbtn {
  position: relative;
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  border: none;
  border-radius: 50%;
  background: var(--c-primary-soft);
  font-size: 20px;
  cursor: pointer;
}

.cartbtn__badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: var(--r-pill);
  background: var(--c-primary-600);
  color: #fff;
  font-size: 10px;
  line-height: 18px;
  font-weight: 600;
}

.cartbar__info {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  cursor: pointer;
}

.cartbar__count {
  font-size: var(--fs-md);
  font-weight: 600;
}

.cartbar__sub {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.cartbar__go {
  flex: 0 0 auto;
  min-width: 96px;
}

/* ---------------- 详情弹窗 ---------------- */
.detail {
  position: relative;
  padding-bottom: var(--safe-bottom);
  max-height: 86dvh;
  overflow-y: auto;
}

.detail__media {
  width: 100%;
  height: 210px;
  background: var(--c-primary-50);
}

.detail__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.detail__fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 64px;
  color: var(--c-primary-300);
}

.detail__body {
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.detail__name {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 700;
}

.detail__desc {
  margin: 0;
  font-size: var(--fs-md);
  color: var(--c-text-sub);
}

.dish-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.dish-tag {
  padding: 2px 9px;
  border-radius: var(--r-pill);
  background: var(--c-primary-soft);
  color: var(--c-primary-strong);
  font-size: var(--fs-xs);
}

.detail__field {
  border-radius: var(--r-md);
  border: 1px solid var(--c-border);
  background: var(--c-bg-sunk);
}

.detail__foot {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-top: var(--sp-2);
}

.detail__close {
  position: absolute;
  right: 10px;
  top: 10px;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  font-size: 19px;
  line-height: 1;
  cursor: pointer;
}
</style>
