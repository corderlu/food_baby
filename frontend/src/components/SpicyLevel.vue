<script setup lang="ts">
/** 辣度显示：0 不辣时不渲染，1-3 显示对应数量的辣椒。 */
const props = defineProps<{
  level: number
  showText?: boolean
}>()

const ICONS = ['', '🌶️', '🌶️🌶️', '🌶️🌶️🌶️']
</script>

<template>
  <span v-if="props.level > 0" class="spicy" :class="`spicy--${props.level}`">
    <span class="spicy__icons">{{ ICONS[props.level] || '🌶️' }}</span>
    <span v-if="props.showText" class="spicy__text">
      {{ ['不辣', '微辣', '中辣', '特辣'][props.level] }}
    </span>
  </span>
</template>

<style scoped>
.spicy {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: var(--fs-xs);
  line-height: 1;
}

.spicy__icons {
  letter-spacing: -1px;
}

.spicy__text {
  color: var(--c-text-sub);
  margin-left: 2px;
}

.spicy--3 .spicy__icons {
  filter: saturate(1.3);
}
</style>
