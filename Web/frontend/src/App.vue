<template>
  <router-view />
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const HOME_THEME_CLASS = 'route-home'

const stopThemeWatch = watch(
  () => route.name,
  (routeName) => {
    document.documentElement.classList.toggle(HOME_THEME_CLASS, routeName === 'home')
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  stopThemeWatch()
  document.documentElement.classList.remove(HOME_THEME_CLASS)
})
</script>
