<script setup lang="ts">
/** 店铺设置：名称、公告、欢迎语、营业开关、今日推荐。 */
import { computed, onMounted, ref } from 'vue'
import { showToast } from 'vant'
import * as api from '@/api/admin'
import { errorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type { Dish, ShopSettings } from '@/types/api'

const auth = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const candidates = ref<Dish[]>([])
const pickerOpen = ref(false)

const form = ref<ShopSettings>({
  shop_name: '',
  announcement: '',
  welcome_text: '',
  business_open: true,
  closed_tip: '',
  today_recommend_ids: [],
  updated_at: null,
})

/** 保存前的副本，用来算"改了什么" */
let baseline = ''

const dirty = computed(() => JSON.stringify(form.value) !== baseline)

const recommendDishes = computed(() =>
  form.value.today_recommend_ids
    .map((id) => candidates.value.find((d) => d.id === id))
    .filter((d): d is Dish => Boolean(d)),
)

async function load(): Promise<void> {
  loading.value = true
  try {
    const [settings, dishes] = await Promise.all([
      api.fetchSettings(),
      api.fetchRecommendCandidates(),
    ])
    form.value = settings
    candidates.value = dishes
    baseline = JSON.stringify(settings)
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function save(): Promise<void> {
  if (saving.value) return
  if (!form.value.shop_name.trim()) {
    showToast('店名不能是空的')
    return
  }

  saving.value = true
  try {
    const result = await api.updateSettings({
      shop_name: form.value.shop_name.trim(),
      announcement: form.value.announcement,
      welcome_text: form.value.welcome_text,
      business_open: form.value.business_open,
      closed_tip: form.value.closed_tip,
      today_recommend_ids: form.value.today_recommend_ids,
    })
    form.value = result.settings
    baseline = JSON.stringify(result.settings)
    showToast(result.message || '已保存')
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    saving.value = false
  }
}

/** 营业开关：单独一个接口调用，点了立刻生效 */
async function toggleBusiness(value: boolean): Promise<void> {
  form.value.business_open = value
  try {
    const result = await api.updateSettings({ business_open: value })
    form.value = result.settings
    baseline = JSON.stringify(result.settings)
    showToast(value ? '已开始营业 ♥' : '已切到休息中')
  } catch (e) {
    form.value.business_open = !value
    showToast(errorMessage(e))
  }
}

function toggleRecommend(dish: Dish): void {
  const ids = new Set(form.value.today_recommend_ids)
  if (ids.has(dish.id)) ids.delete(dish.id)
  else ids.add(dish.id)
  form.value.today_recommend_ids = [...ids]
}

function isRecommended(id: number): boolean {
  return form.value.today_recommend_ids.includes(id)
}

function clearRecommends(): void {
  form.value.today_recommend_ids = []
}
</script>

<template>
  <div class="page page--with-tabbar" :class="{ 'page--with-actionbar': !loading }">
    <header class="ahead">
      <h1 class="ahead__title">店铺设置</h1>
      <p class="ahead__sub">改完保存，她那边的页面刷新就能看到</p>
    </header>

    <div v-if="loading" class="stack" style="padding: var(--sp-4)">
      <div v-for="i in 3" :key="i" class="skeleton" style="height: 130px; border-radius: var(--r-lg)" />
    </div>

    <template v-else>
      <!-- 营业开关：最常用，放最上面 -->
      <section class="biz" :class="{ 'biz--open': form.business_open }">
        <div class="biz__icon">{{ form.business_open ? '🔥' : '😴' }}</div>
        <div class="grow">
          <div class="biz__title">{{ form.business_open ? '营业中' : '休息中' }}</div>
          <div class="biz__sub">
            {{ form.business_open ? '她现在可以下单' : '她能看到菜单，但下不了单' }}
          </div>
        </div>
        <van-switch
          :model-value="form.business_open"
          size="24"
          @update:model-value="toggleBusiness"
        />
      </section>

      <!-- 基本信息 -->
      <section class="section-title">基本信息</section>
      <div class="card card__pad form">
        <van-field v-model="form.shop_name" label="店铺名称" maxlength="80" placeholder="爱心小食堂" />
        <van-field
          v-model="form.welcome_text"
          label="欢迎语"
          maxlength="200"
          placeholder="想吃什么就点什么，我全都做给你吃 ♥"
        />
        <van-field
          v-model="form.announcement"
          label="公告"
          maxlength="500"
          type="textarea"
          rows="2"
          autosize
          placeholder="今天也要好好吃饭呀 ♥"
        />
        <van-field
          v-model="form.closed_tip"
          label="休息提示"
          maxlength="200"
          type="textarea"
          rows="2"
          autosize
          placeholder="主厨休息中，先去逛逛菜单吧～"
        />
        <p class="form__hint">「休息提示」是她在你关掉营业时看到的话。</p>
      </div>

      <!-- 今日推荐 -->
      <section class="section-title">
        今日推荐
        <span class="section-title__extra">{{ recommendDishes.length }} 道</span>
      </section>

      <div class="card card__pad rec">
        <div v-if="recommendDishes.length" class="rec__picked">
          <div v-for="dish in recommendDishes" :key="dish.id" class="rec__chip">
            <img v-if="dish.image_url" :src="dish.image_url" :alt="dish.name" />
            <span class="ellipsis">{{ dish.name }}</span>
            <button class="rec__remove" aria-label="移除" @click="toggleRecommend(dish)">×</button>
          </div>
        </div>
        <p v-else class="rec__empty">还没选。选几道会显示在她首页最上面的「今日推荐」里。</p>

        <div class="rec__actions">
          <van-button round size="small" type="primary" plain @click="pickerOpen = true">
            选择菜品
          </van-button>
          <van-button v-if="recommendDishes.length" round size="small" plain @click="clearRecommends">
            清空
          </van-button>
        </div>
      </div>

      <!-- 账号提示 -->
      <div v-if="auth.usingDefaultPassword" class="warn">
        <span>⚠️</span>
        <span class="grow">你还在用初始密码，建议去「账号」页改掉</span>
      </div>

      <div class="heart-divider">♥</div>
    </template>

    <!-- 保存条：sticky 贴在底部导航上方，不会盖住导航 -->
    <div v-if="!loading" class="savebar">
      <span class="grow t-sub">{{ dirty ? '有未保存的修改' : '已是最新' }}</span>
      <van-button
        round
        type="primary"
        :disabled="!dirty"
        :loading="saving"
        class="savebtn"
        @click="save"
      >
        保存设置
      </van-button>
    </div>

    <!-- 推荐选择 -->
    <van-popup v-model:show="pickerOpen" position="bottom" round :style="{ maxHeight: '78dvh' }">
      <div class="picker">
        <header class="picker__head">
          <h3>选今日推荐</h3>
          <button class="picker__close" aria-label="关闭" @click="pickerOpen = false">×</button>
        </header>
        <p class="picker__tip">可以多选，选完点下面的「好了」</p>

        <div class="picker__list">
          <article
            v-for="dish in candidates"
            :key="dish.id"
            class="pitem"
            :class="{ 'pitem--on': isRecommended(dish.id) }"
            @click="toggleRecommend(dish)"
          >
            <div class="pitem__media">
              <img v-if="dish.image_url" :src="dish.image_url" :alt="dish.name" loading="lazy" />
              <div v-else class="pitem__fallback">♥</div>
            </div>
            <div class="grow">
              <div class="pitem__name">{{ dish.name }}</div>
              <div class="pitem__meta">{{ dish.category }} · ⏱{{ dish.estimated_minutes }}分</div>
            </div>
            <span class="pitem__check">{{ isRecommended(dish.id) ? '✓' : '' }}</span>
          </article>
        </div>

        <footer class="picker__foot">
          <van-button round type="primary" block @click="pickerOpen = false">
            好了（已选 {{ recommendDishes.length }} 道）
          </van-button>
        </footer>
      </div>
    </van-popup>
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

/* ---- 营业开关 ---- */
.biz {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin: var(--sp-4);
  padding: var(--sp-4);
  border-radius: var(--r-lg);
  background: var(--c-bg-sunk);
  border: 1px solid var(--c-border-strong);
  transition: background var(--dur) var(--ease);
}

.biz--open {
  background: linear-gradient(135deg, var(--c-primary-200), var(--c-primary-50));
  border-color: var(--c-primary-300);
}

.biz__icon {
  font-size: 26px;
}

.biz__title {
  font-size: var(--fs-lg);
  font-weight: 600;
}

.biz__sub {
  font-size: var(--fs-xs);
  color: var(--c-text-sub);
}

/* ---- 表单 ---- */
.form {
  margin: 0 var(--sp-4);
}

.form :deep(.van-field) {
  padding-left: 0;
  padding-right: 0;
  border-bottom: 1px solid var(--c-border);
}

.form :deep(.van-field:last-of-type) {
  border-bottom: none;
}

.form__hint {
  margin: var(--sp-2) 0 0;
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

/* ---- 推荐 ---- */
.rec {
  margin: 0 var(--sp-4);
}

.rec__picked {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}

.rec__chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px 4px 4px;
  border-radius: var(--r-pill);
  background: var(--c-primary-soft);
  font-size: var(--fs-sm);
  max-width: 100%;
}

.rec__chip img {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  object-fit: cover;
}

.rec__remove {
  border: none;
  background: transparent;
  color: var(--c-primary-600);
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
}

.rec__empty {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--c-text-weak);
  line-height: 1.6;
}

.rec__actions {
  display: flex;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}

/* ---- 警告 ---- */
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

/* ---- 保存条 ----
   这个页面底部还有 van-tabbar（fixed，高 --tabbar-h）。
   用 sticky 吸在 tabbar 上方，而不是 fixed 到底部：
   fixed 需要写死 tabbar 高度，iPhone 安全区一变就错位；
   sticky 让它在正常文档流里，滚到底部时自然停在 tabbar 上面，
   既不会盖住导航，也不会遮住最后一段内容。 */
.savebar {
  position: sticky;
  bottom: calc(var(--tabbar-h) + var(--safe-bottom));
  z-index: 19;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-top: var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
  background: rgba(255, 247, 250, 0.94);
  backdrop-filter: blur(12px);
  border-top: 1px solid var(--c-border);
}

.savebtn {
  min-width: 128px;
}

/* ---- 推荐选择弹层 ---- */
.picker {
  display: flex;
  flex-direction: column;
  max-height: 78dvh;
}

.picker__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--sp-4) 0;
}

.picker__head h3 {
  margin: 0;
  font-size: var(--fs-lg);
}

.picker__close {
  border: none;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  color: var(--c-text-sub);
  cursor: pointer;
}

.picker__tip {
  margin: var(--sp-1) var(--sp-4) var(--sp-2);
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.picker__list {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--sp-4);
}

.pitem {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) 0;
  border-bottom: 1px solid var(--c-border);
  cursor: pointer;
}

.pitem--on {
  background: linear-gradient(90deg, var(--c-primary-50), transparent);
}

.pitem__media {
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  border-radius: var(--r-sm);
  overflow: hidden;
  background: var(--c-primary-50);
}

.pitem__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.pitem__fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-primary-300);
}

.pitem__name {
  font-size: var(--fs-md);
  font-weight: 500;
}

.pitem__meta {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.pitem__check {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  border-radius: 50%;
  border: 1px solid var(--c-border-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
}

.pitem--on .pitem__check {
  background: var(--c-primary);
  border-color: transparent;
}

.picker__foot {
  padding: var(--sp-3) var(--sp-4) calc(var(--sp-3) + var(--safe-bottom));
  border-top: 1px solid var(--c-border);
}
</style>
