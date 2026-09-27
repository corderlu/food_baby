<script setup lang="ts">
/**
 * 菜品管理。
 *
 * 图片这块做了两手准备：
 *   - 拍照/选图上传：服务端 Pillow 自动压缩到长边 1200 并生成 400 的缩略图，
 *     手机原图动辄 5MB，压完通常 100~300KB，她加载菜单快很多。
 *   - 一键生成占位图：不想拍照时，按菜名生成一张粉色爱心图，立刻有图可看。
 * 上传或生成后都会立刻显示预览，保存时才写库。
 */
import { computed, onMounted, ref } from 'vue'
import { showConfirmDialog, showToast } from 'vant'
import * as api from '@/api/admin'
import { errorMessage } from '@/api/http'
import SpicyLevel from '@/components/SpicyLevel.vue'
import type { Dish, DishInput } from '@/types/api'

const dishes = ref<Dish[]>([])
const categories = ref<string[]>([])
const loading = ref(true)
const keyword = ref('')
const categoryFilter = ref('')

/* ---------------- 编辑弹窗状态 ---------------- */
const editorOpen = ref(false)
const editing = ref<Dish | null>(null)
const saving = ref(false)
const uploading = ref(false)
const uploadPercent = ref(0)
const showCategoryPicker = ref(false)

const form = ref<DishInput>({
  name: '',
  description: '',
  image_url: '',
  category: '热菜',
  tags: [],
  spicy_level: 0,
  estimated_minutes: 20,
  is_available: true,
  sort_order: 0,
})

const tagsText = ref('')
const isNew = computed(() => editing.value === null)

const PRESET_CATEGORIES = ['主食', '热菜', '凉菜', '汤', '甜品', '饮料']
const categoryOptions = computed(() => {
  const merged = [...PRESET_CATEGORIES]
  for (const c of categories.value) if (!merged.includes(c)) merged.push(c)
  return merged
})

const filtered = computed(() =>
  dishes.value.filter((d) => {
    if (categoryFilter.value && d.category !== categoryFilter.value) return false
    if (keyword.value && !d.name.includes(keyword.value.trim())) return false
    return true
  }),
)

/* ------------------------------------------------------------------ 数据 */

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await api.fetchDishes()
    dishes.value = data.dishes
    categories.value = data.categories
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    loading.value = false
  }
}

onMounted(load)

/* ------------------------------------------------------------------ 编辑 */

function openCreate(): void {
  editing.value = null
  form.value = {
    name: '',
    description: '',
    image_url: '',
    category: categoryFilter.value || '热菜',
    tags: [],
    spicy_level: 0,
    estimated_minutes: 20,
    is_available: true,
    sort_order: (dishes.value.length + 1) * 10,
  }
  tagsText.value = ''
  editorOpen.value = true
}

function openEdit(dish: Dish): void {
  editing.value = dish
  form.value = {
    name: dish.name,
    description: dish.description,
    image_url: dish.image_url,
    category: dish.category,
    tags: [...dish.tags],
    spicy_level: dish.spicy_level,
    estimated_minutes: dish.estimated_minutes,
    is_available: dish.is_available,
    sort_order: dish.sort_order,
  }
  tagsText.value = dish.tags.join(',')
  editorOpen.value = true
}

function commitTags(): void {
  form.value.tags = tagsText.value
    .replace(/，/g, ',')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 8)
}

async function save(): Promise<void> {
  if (saving.value) return
  if (!form.value.name.trim()) {
    showToast('菜名要填哦')
    return
  }

  commitTags()
  saving.value = true
  try {
    const payload = { ...form.value, name: form.value.name.trim() }
    if (isNew.value) {
      const result = await api.createDish(payload)
      dishes.value = [result.dish, ...dishes.value]
      showToast(result.message)
    } else if (editing.value) {
      const result = await api.updateDish(editing.value.id, payload)
      const idx = dishes.value.findIndex((d) => d.id === result.dish.id)
      if (idx >= 0) dishes.value[idx] = result.dish
      showToast(result.message)
    }
    editorOpen.value = false
    await load()
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    saving.value = false
  }
}

function onCategoryConfirm(payload: { selectedOptions: Array<{ value: string }> }): void {
  const picked = payload.selectedOptions?.[0]?.value
  if (picked) form.value.category = picked
  showCategoryPicker.value = false
}

/* ------------------------------------------------------------------ 图片 */

/** Vant Uploader 的 after-read 回调 */
async function onAfterRead(items: unknown): Promise<void> {
  const list = Array.isArray(items) ? items : [items]
  const first = list[0] as { file?: File } | undefined
  const file = first?.file
  if (!file) return

  if (!file.type.startsWith('image/')) {
    showToast('只能传图片哦')
    return
  }

  uploading.value = true
  uploadPercent.value = 0
  try {
    const result = await api.uploadDishImage(file, (p) => (uploadPercent.value = p))
    form.value.image_url = result.image_url
    showToast('图片已压缩上传')
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    uploading.value = false
    uploadPercent.value = 0
  }
}

async function generatePlaceholder(): Promise<void> {
  const name = form.value.name.trim()
  if (!name) {
    showToast('先填菜名，占位图上要写名字')
    return
  }
  uploading.value = true
  try {
    // 复用后端的占位图接口
    const res = await fetch('/api/admin/dishes/placeholder', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${localStorage.getItem('food_baby_token') || ''}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({ name, subtitle: form.value.category || '' }),
    })
    const data = (await res.json()) as { image_url?: string; detail?: string }
    if (!res.ok || !data.image_url) throw new Error(data.detail || '生成失败')
    form.value.image_url = data.image_url
    showToast('已生成占位图')
  } catch (e) {
    showToast(errorMessage(e))
  } finally {
    uploading.value = false
  }
}

function clearImage(): void {
  form.value.image_url = ''
}

/* ------------------------------------------------------------------ 列表操作 */

async function toggle(dish: Dish): Promise<void> {
  const next = !dish.is_available
  try {
    const result = await api.toggleDish(dish.id, next)
    const idx = dishes.value.findIndex((d) => d.id === result.dish.id)
    if (idx >= 0) dishes.value[idx] = result.dish
    showToast(result.message)
  } catch (e) {
    showToast(errorMessage(e))
  }
}

async function remove(dish: Dish): Promise<void> {
  try {
    await showConfirmDialog({
      title: `删除「${dish.name}」？`,
      message: '删掉之后菜单里就没有了，历史订单不受影响。',
      confirmButtonText: '删除',
      cancelButtonText: '留着',
    })
  } catch {
    return
  }

  try {
    await api.deleteDish(dish.id)
    dishes.value = dishes.value.filter((d) => d.id !== dish.id)
    showToast('已删除')
  } catch (e) {
    const msg = errorMessage(e)
    // 后端会告诉我们这道菜出现在历史订单里，需要二次确认
    if (msg.includes('历史订单')) {
      try {
        await showConfirmDialog({
          title: '确认强制删除',
          message: msg,
          confirmButtonText: '确认删除',
          cancelButtonText: '算了',
        })
        await api.deleteDish(dish.id, true)
        dishes.value = dishes.value.filter((d) => d.id !== dish.id)
        showToast('已删除，历史订单仍显示旧菜名')
      } catch {
        /* 取消 */
      }
    } else {
      showToast(msg)
    }
  }
}
</script>

<template>
  <div class="page page--with-tabbar">
    <header class="ahead ahead--compact">
      <div class="ahead__top">
        <div>
          <h1 class="ahead__title">菜品管理</h1>
          <p class="ahead__sub">
            共 {{ dishes.length }} 道 · 上架 {{ dishes.filter((d) => d.is_available).length }} 道
          </p>
        </div>
        <van-button round size="small" type="primary" @click="openCreate">＋ 新增</van-button>
      </div>

      <van-search
        v-model="keyword"
        placeholder="搜菜名"
        shape="round"
        background="transparent"
        class="ahead__search"
      />

      <div class="filters">
        <button
          class="filters__item"
          :class="{ 'is-active': categoryFilter === '' }"
          @click="categoryFilter = ''"
        >
          全部
        </button>
        <button
          v-for="cat in categoryOptions"
          :key="cat"
          class="filters__item"
          :class="{ 'is-active': categoryFilter === cat }"
          @click="categoryFilter = cat"
        >
          {{ cat }}
        </button>
      </div>
    </header>

    <!-- 加载 -->
    <div v-if="loading" class="stack" style="padding: var(--sp-4)">
      <div v-for="i in 4" :key="i" class="skeleton" style="height: 96px; border-radius: var(--r-lg)" />
    </div>

    <!-- 空 -->
    <div v-else-if="!filtered.length" class="empty">
      <div class="empty__emoji">🍳</div>
      <p>{{ dishes.length ? '没有符合条件的菜' : '还没有菜品' }}</p>
      <van-button round size="small" type="primary" @click="openCreate">加第一道菜</van-button>
    </div>

    <!-- 列表 -->
    <div v-else class="dlist">
      <article
        v-for="dish in filtered"
        :key="dish.id"
        class="drow"
        :class="{ 'drow--off': !dish.is_available }"
      >
        <div class="drow__media" @click="openEdit(dish)">
          <img v-if="dish.image_url" :src="dish.image_url" :alt="dish.name" loading="lazy" />
          <div v-else class="drow__fallback">♥</div>
          <span v-if="!dish.is_available" class="drow__off">已下架</span>
        </div>

        <div class="drow__body" @click="openEdit(dish)">
          <div class="row row--between">
            <h3 class="drow__name ellipsis">{{ dish.name }}</h3>
            <SpicyLevel :level="dish.spicy_level" />
          </div>
          <p v-if="dish.description" class="drow__desc ellipsis">{{ dish.description }}</p>
          <div class="drow__meta">
            <span class="drow__cat">{{ dish.category }}</span>
            <span>⏱{{ dish.estimated_minutes }}分</span>
            <span>排序 {{ dish.sort_order }}</span>
          </div>
          <div v-if="dish.tags.length" class="drow__tags">
            <span v-for="tag in dish.tags.slice(0, 4)" :key="tag" class="drow__tag">{{ tag }}</span>
          </div>
        </div>

        <div class="drow__ops">
          <van-switch
            :model-value="dish.is_available"
            size="20"
            @update:model-value="() => toggle(dish)"
          />
          <button class="drow__del" aria-label="删除" @click="remove(dish)">🗑</button>
        </div>
      </article>
    </div>

    <!-- ---------------- 编辑弹层 ---------------- -->
    <van-popup
      v-model:show="editorOpen"
      position="bottom"
      round
      :close-on-click-overlay="false"
      :style="{ maxWidth: 'var(--page-max)', left: '50%', transform: 'translateX(-50%)' }"
    >
      <div class="editor">
        <header class="editor__head">
          <h3>{{ isNew ? '新增菜品' : '编辑菜品' }}</h3>
          <button class="editor__close" aria-label="关闭" @click="editorOpen = false">×</button>
        </header>

        <div class="editor__body">
          <!-- 图片 -->
          <div class="editor__image">
            <div class="editor__preview">
              <img v-if="form.image_url" :src="form.image_url" alt="预览" />
              <div v-else class="editor__preview-empty">还没有图片</div>
              <div v-if="uploading" class="editor__uploading">
                <van-loading color="#fff" size="20px" />
                <span v-if="uploadPercent">{{ uploadPercent }}%</span>
                <span v-else>处理中…</span>
              </div>
            </div>

            <div class="editor__image-ops">
              <van-uploader
                :after-read="onAfterRead"
                :max-count="1"
                accept="image/*"
                :preview-image="false"
                :disabled="uploading"
              >
                <van-button round size="small" type="primary" plain :disabled="uploading">
                  📷 选图 / 拍照
                </van-button>
              </van-uploader>
              <van-button
                round
                size="small"
                plain
                :disabled="uploading"
                @click="generatePlaceholder"
              >
                ✨ 生成占位图
              </van-button>
              <van-button
                v-if="form.image_url"
                round
                size="small"
                plain
                type="danger"
                @click="clearImage"
              >
                清除
              </van-button>
            </div>
            <p class="editor__image-tip">
              手机原图会自动压缩到长边 1200 并生成缩略图，她加载菜单更快
            </p>
          </div>

          <!-- 表单 -->
          <van-field v-model="form.name" label="菜名" placeholder="必填，比如：番茄炒蛋" maxlength="80" />
          <van-field
            v-model="form.description"
            label="描述"
            placeholder="一句话让她想吃，比如：汤汁记得拌饭"
            maxlength="500"
            type="textarea"
            rows="2"
            autosize
          />

          <van-field
            :model-value="form.category"
            label="分类"
            readonly
            is-link
            placeholder="选择分类"
            @click="showCategoryPicker = true"
          />

          <van-field
            v-model="tagsText"
            label="标签"
            placeholder="逗号分隔，如：下饭,拿手菜"
            maxlength="120"
            @blur="commitTags"
          />

          <van-field label="辣度">
            <template #input>
              <van-radio-group v-model="form.spicy_level" direction="horizontal">
                <van-radio :name="0">不辣</van-radio>
                <van-radio :name="1">微辣</van-radio>
                <van-radio :name="2">中辣</van-radio>
                <van-radio :name="3">特辣</van-radio>
              </van-radio-group>
            </template>
          </van-field>

          <van-field label="预计制作">
            <template #input>
              <van-stepper v-model="form.estimated_minutes" min="0" max="600" step="5" />
              <span class="editor__unit">分钟</span>
            </template>
          </van-field>

          <van-field label="排序值">
            <template #input>
              <van-stepper v-model="form.sort_order" min="0" max="9999" step="5" />
              <span class="editor__unit">数字小的在前</span>
            </template>
          </van-field>

          <van-field label="是否上架">
            <template #input>
              <van-switch v-model="form.is_available" size="22" />
              <span class="editor__unit">{{ form.is_available ? '她能看到' : '她看不到' }}</span>
            </template>
          </van-field>
        </div>

        <footer class="editor__foot">
          <van-button round plain block @click="editorOpen = false">取消</van-button>
          <van-button round type="primary" block :loading="saving" @click="save">保存</van-button>
        </footer>
      </div>
    </van-popup>

    <!-- 分类选择 -->
    <van-popup v-model:show="showCategoryPicker" position="bottom" round>
      <van-picker
        title="选择分类"
        :columns="categoryOptions.map((c) => ({ text: c, value: c }))"
        @confirm="onCategoryConfirm"
        @cancel="showCategoryPicker = false"
      />
    </van-popup>
  </div>
</template>

<style scoped>
/* ---- 顶栏 ---- */
.ahead {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: calc(var(--sp-4) + var(--safe-top)) var(--sp-4) var(--sp-3);
  background: linear-gradient(165deg, var(--c-primary-200), var(--c-bg) 92%);
  border-bottom-left-radius: var(--r-xl);
  border-bottom-right-radius: var(--r-xl);
}

.ahead__top {
  display: flex;
  align-items: center;
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
}

.ahead__search {
  padding: var(--sp-2) 0 0;
}

.ahead__search :deep(.van-search__content) {
  background: var(--c-bg-card);
}

.filters {
  display: flex;
  gap: var(--sp-2);
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

/* ---- 列表 ---- */
.dlist {
  padding: var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.drow {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-sm);
}

.drow--off {
  opacity: 0.62;
}

.drow__media {
  position: relative;
  width: 78px;
  height: 78px;
  flex: 0 0 78px;
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--c-primary-50);
  cursor: pointer;
}

.drow__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.drow__fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  color: var(--c-primary-300);
}

.drow__off {
  position: absolute;
  left: 0;
  bottom: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 10px;
  text-align: center;
  padding: 1px 0;
}

.drow__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  cursor: pointer;
}

.drow__name {
  margin: 0;
  font-size: var(--fs-lg);
  font-weight: 600;
}

.drow__desc {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
}

.drow__meta {
  display: flex;
  gap: var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.drow__cat {
  color: var(--c-primary-600);
  font-weight: 600;
}

.drow__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.drow__tag {
  padding: 1px 7px;
  border-radius: var(--r-pill);
  background: var(--c-primary-soft);
  color: var(--c-primary-strong);
  font-size: 10px;
}

.drow__ops {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}

.drow__del {
  border: none;
  background: transparent;
  font-size: 17px;
  cursor: pointer;
  padding: 0;
}

/* ---- 编辑弹层 ---- */
.editor {
  display: flex;
  flex-direction: column;
  max-height: 90dvh;
}

.editor__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  border-bottom: 1px solid var(--c-border);
}

.editor__head h3 {
  margin: 0;
  font-size: var(--fs-lg);
}

.editor__close {
  border: none;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  color: var(--c-text-sub);
  cursor: pointer;
}

.editor__body {
  flex: 1;
  overflow-y: auto;
  padding-bottom: var(--sp-3);
}

.editor__image {
  padding: var(--sp-4) var(--sp-4) var(--sp-2);
}

.editor__preview {
  position: relative;
  width: 100%;
  height: 172px;
  border-radius: var(--r-lg);
  overflow: hidden;
  background: var(--c-bg-sunk);
  border: 1px dashed var(--c-border-strong);
}

.editor__preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.editor__preview-empty {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-weak);
  font-size: var(--fs-sm);
}

.editor__uploading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  background: rgba(67, 49, 58, 0.55);
  color: #fff;
  font-size: var(--fs-sm);
}

.editor__image-ops {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}

.editor__image-tip {
  margin: var(--sp-2) 0 0;
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
  line-height: 1.5;
}

.editor__body :deep(.van-field) {
  padding-left: var(--sp-4);
  padding-right: var(--sp-4);
}

.editor__unit {
  margin-left: var(--sp-2);
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.editor__foot {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4) calc(var(--sp-3) + var(--safe-bottom));
  border-top: 1px solid var(--c-border);
  background: var(--c-bg-card);
}
</style>
