<template><div ref="chartRef" class="environment-chart"></div></template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use, type ECharts } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = withDefaults(defineProps<{
  data: Array<Record<string, string | number | null>>
  fields?: Array<{ key: string; name: string; color: string; unit?: string }>
  height?: number
}>(), {
  fields: () => [
    { key: 'temperature', name: '温度', color: '#315b45', unit: '°C' },
    { key: 'humidity', name: '湿度', color: '#82a953', unit: '%' },
  ],
  height: 280,
})
const chartRef = ref<HTMLDivElement>(); let chart: ECharts | undefined; let observer: ResizeObserver | undefined
function render() {
  if (!chartRef.value) return
  chart ||= init(chartRef.value)
  chart.setOption({
    animationDuration: 700,
    tooltip: { trigger: 'axis', backgroundColor: '#17251f', borderWidth: 0, textStyle: { color: '#eef3ed', fontSize: 11 } },
    legend: { top: 0, right: 0, icon: 'circle', itemWidth: 7, textStyle: { color: '#6f7c74', fontSize: 10 } },
    grid: { left: 42, right: 18, top: 42, bottom: 28 },
    xAxis: { type: 'category', boundaryGap: false, data: props.data.map(d => formatTime(String(d.time || ''))), axisLine: { lineStyle: { color: '#cdd3ca' } }, axisTick: { show: false }, axisLabel: { color: '#8b958e', fontSize: 9, hideOverlap: true } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#e2e6dd', type: 'dashed' } }, axisLabel: { color: '#8b958e', fontSize: 9 } },
    series: props.fields.map(field => ({
      name: field.name, type: 'line', data: props.data.map(d => d[field.key]), smooth: .3, symbol: 'none', lineStyle: { width: 2, color: field.color },
      areaStyle: props.fields.length <= 2 ? { color: `${field.color}1f` } : undefined,
    })),
  }, true)
}
function formatTime(value: string) { const d = new Date(value); return Number.isNaN(d.getTime()) ? '—' : `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}` }
onMounted(() => { render(); observer = new ResizeObserver(() => chart?.resize()); if (chartRef.value) observer.observe(chartRef.value) })
watch(() => [props.data, props.fields], render, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>

<style scoped>.environment-chart{width:100%;min-height:v-bind('`${height}px`')}</style>
