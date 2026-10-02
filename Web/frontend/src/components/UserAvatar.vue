<template>
  <span class="user-avatar" :class="presetClass" :style="avatarStyle" aria-hidden="true">
    <svg v-if="presetClass === 'leaf'" viewBox="0 0 48 48">
      <path d="M39 8C25 9 13 17 11 29c-1 6 3 11 9 11 12 0 19-13 19-32Z" />
      <path d="M10 41c5-10 12-17 22-23" class="stroke" />
    </svg>
    <svg v-else-if="presetClass === 'field'" viewBox="0 0 48 48">
      <path d="M7 15h34v24H7z" class="field-frame" />
      <path d="M8 25c10-7 22-7 32 0M8 34c10-7 22-7 32 0" class="stroke" />
      <path d="M24 15v24" class="stroke" />
    </svg>
    <svg v-else-if="presetClass === 'path'" viewBox="0 0 48 48">
      <circle cx="13" cy="35" r="5" />
      <circle cx="36" cy="12" r="5" />
      <path d="M16 31c4-7 9-4 12-10 2-4 1-7 4-8" class="stroke" />
    </svg>
    <span v-else>{{ initial }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  avatar?: string | null
  nickname?: string | null
  size?: number
}>(), { avatar: null, nickname: '用户', size: 40 })

const presetClass = computed(() => props.avatar?.startsWith('preset:') ? props.avatar.slice(7) : '')
const initial = computed(() => (props.nickname || '用').trim().slice(0, 1).toUpperCase())
const avatarStyle = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }))
</script>

<style scoped>
.user-avatar{display:inline-grid;place-items:center;flex:0 0 auto;border-radius:50%;overflow:hidden;background:#dce5d6;color:#315b45;font:600 14px var(--display)}
.user-avatar svg{width:62%;height:62%;overflow:visible}.user-avatar svg path,.user-avatar svg circle{fill:currentColor}.user-avatar svg .stroke{fill:none;stroke:currentColor;stroke-width:3;stroke-linecap:round}.user-avatar.leaf{background:#dce9ce;color:#315b45}.user-avatar.field{background:#e5ddc4;color:#6f5a2c}.user-avatar.path{background:#d5e1e2;color:#315b62}.user-avatar .field-frame{fill:none;stroke:currentColor;stroke-width:2}
</style>
