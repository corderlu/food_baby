<script setup lang="ts">
/**
 * 菜品卡片。
 * 图片懒加载 + 加载失败兜底（不显示破图，改成一个爱心占位）。
 */
import { computed, ref } from 'vue'
import type { Dish } from '@/types/api'
import SpicyLevel from './SpicyLevel.vue'

const props = defineProps<{
  dish: Dish
  quantity?: number
  isRecommend?: boolean
}>()

const emit = defineEmits<{
  (e: 'add', dish: Dish): void
  (e: 'open', dish: Dish): void
  (e: 'increase', dish: Dish): void
  (e: 'decrease', dish: Dish): void
}>()

const failed = ref(false)
const loaded = ref(false)

const imageSrc = computed(() => (failed.value ? '' : props.dish.image_url))
const count = computed(() => props.quantity ?? 0)

function onError(): void {
  failed.value = true
}
</script>

<template>
  <article class="dish" :class="{ 'dish--picked': count > 0 }" @click="emit('open', dish)">
    <div class="dish__media">
      <img
        v-if="imageSrc"
        :src="imageSrc"
        :alt="dish.name"
        class="dish__img"
        :class="{ 'dish__img--ready': loaded }"
        loading="lazy"
        decoding="async"
        @load="loaded = true"
        @error="onError"
      />
      <div v-else class="dish__img dish__img--fallback">♥</div>

      <span v-if="isRecommend" class="dish__ribbon">今日推荐</span>
      <span v-if="count > 0" class="dish__count">{{ count }}</span>
    </div>

    <div class="dish__body">
      <h3 class="dish__name ellipsis">{{ dish.name }}</h3>
      <p v-if="dish.description" class="dish__desc clamp-2">{{ dish.description }}</p>

      <div class="dish__meta">
        <SpicyLevel :level="dish.spicy_level" />
        <span v-if="dish.estimated_minutes" class="dish__time">⏱ {{ dish.estimated_minutes }}分</span>
      </div>

      <div v-if="dish.tags.length" class="dish__tags">
        <span v-for="tag in dish.tags.slice(0, 3)" :key="tag" class="dish__tag">{{ tag }}</span>
      </div>

      <div class="dish__foot">
        <span class="dish__category">{{ dish.category }}</span>

        <div class="dish__stepper" @click.stop>
          <template v-if="count > 0">
            <button class="dish__step dish__step--minus" aria-label="减少" @click="emit('decrease', dish)">
              −
            </button>
            <span class="dish__step-num">{{ count }}</span>
          </template>
          <button class="dish__step dish__step--plus" aria-label="加入购物车" @click="emit('add', dish)">
            +
          </button>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.dish {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--c-bg-card);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--sh-sm);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease),
    border-color var(--dur) var(--ease);
  cursor: pointer;
}

.dish:active {
  transform: scale(0.988);
}

.dish--picked {
  border-color: var(--c-primary-300);
  box-shadow: var(--sh-md);
}

/* ---- 图片 ---- */
.dish__media {
  position: relative;
  width: 96px;
  height: 96px;
  flex: 0 0 96px;
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--c-primary-50);
}

.dish__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity 320ms var(--ease);
}

.dish__img--ready {
  opacity: 1;
}

.dish__img--fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 34px;
  color: var(--c-primary-300);
  opacity: 1;
}

.dish__ribbon {
  position: absolute;
  top: 0;
  left: 0;
  padding: 2px 7px;
  font-size: 10px;
  color: #fff;
  background: linear-gradient(135deg, var(--c-primary-500), var(--c-primary-300));
  border-bottom-right-radius: var(--r-sm);
  letter-spacing: 0.5px;
}

.dish__count {
  position: absolute;
  right: 5px;
  bottom: 5px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: var(--fs-sm);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--sh-sm);
}

/* ---- 文字 ---- */
.dish__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.dish__name {
  margin: 0;
  font-size: var(--fs-lg);
  font-weight: 600;
  line-height: 1.3;
}

.dish__desc {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--c-text-sub);
  line-height: 1.45;
}

.dish__meta {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.dish__time {
  white-space: nowrap;
}

.dish__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.dish__tag {
  padding: 1px 7px;
  border-radius: var(--r-pill);
  background: var(--c-primary-soft);
  color: var(--c-primary-strong);
  font-size: 10px;
  line-height: 1.6;
}

/* ---- 底部 ---- */
.dish__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 4px;
}

.dish__category {
  font-size: var(--fs-xs);
  color: var(--c-text-weak);
}

.dish__stepper {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.dish__step {
  width: 27px;
  height: 27px;
  border-radius: 50%;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition: transform 140ms var(--ease), background var(--dur) var(--ease);
  padding: 0;
}

.dish__step:active {
  transform: scale(0.86);
}

.dish__step--plus {
  background: linear-gradient(135deg, var(--c-primary-400), var(--c-primary-600));
  color: #fff;
  box-shadow: var(--sh-primary);
}

.dish__step--minus {
  background: var(--c-primary-soft);
  color: var(--c-primary-strong);
}

.dish__step-num {
  min-width: 16px;
  text-align: center;
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--c-primary-strong);
}
</style>
