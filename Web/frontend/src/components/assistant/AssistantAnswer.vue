<template>
  <div class="answer-body" v-html="html" @click="handleClick" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Evidence } from '@/api/assistant'

const props = defineProps<{ text: string; evidence: Evidence[] }>()
const emit = defineEmits<{ cite: [id: string] }>()
const html = computed(() => {
  const parsed = marked.parse(props.text, { async: false, breaks: true }) as string
  const safe = DOMPurify.sanitize(parsed, {
    ALLOWED_TAGS: ['p','br','strong','em','del','h1','h2','h3','h4','ul','ol','li','table','thead','tbody','tr','th','td','blockquote','pre','code','hr','a'],
    ALLOWED_ATTR: [],
  })
  // Only registered citations become interactive; model-generated links stay text.
  const container = document.createElement('div')
  container.innerHTML = safe
  for (const link of Array.from(container.querySelectorAll('a'))) link.replaceWith(document.createTextNode(link.textContent || ''))
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)
  for (const node of nodes) {
    if (node.parentElement?.closest('pre, code')) continue
    const parts = node.data.split(/(\[E\d+\])/g)
    if (parts.length === 1) continue
    const fragment = document.createDocumentFragment()
    for (const part of parts) {
      const id = part.slice(1, -1)
      const evidence = props.evidence.find(e => e.id === id)
      if (evidence && /^\[E\d+\]$/.test(part)) {
        const button = document.createElement('button')
        button.className = 'citation'
        button.dataset.citation = id
        button.title = evidence.title
        button.textContent = id.slice(1)
        fragment.append(button)
      } else fragment.append(document.createTextNode(part))
    }
    node.replaceWith(fragment)
  }
  return container.innerHTML
})
function handleClick(event: MouseEvent) {
  const button = (event.target as HTMLElement).closest<HTMLElement>('[data-citation]')
  if (button?.dataset.citation) emit('cite', button.dataset.citation)
}
</script>

<style scoped>
.answer-body{font-size:14px;line-height:1.9;overflow-wrap:anywhere;color:var(--ink-2)}
.answer-body :deep(p){margin:0 0 12px}.answer-body :deep(p:last-child){margin-bottom:0}
.answer-body :deep(h1),.answer-body :deep(h2),.answer-body :deep(h3){font-size:16px;line-height:1.5;margin:22px 0 10px;color:var(--ink)}
.answer-body :deep(ul),.answer-body :deep(ol){padding-left:22px;margin:12px 0}
.answer-body :deep(li){margin:5px 0}.answer-body :deep(table){display:block;overflow-x:auto;border-collapse:collapse;max-width:100%;font-size:13px;margin:16px 0}
.answer-body :deep(th),.answer-body :deep(td){border:1px solid var(--line);padding:8px 12px;text-align:left;min-width:80px}
.answer-body :deep(th){background:#eff3e9;font-weight:600}.answer-body :deep(pre){overflow:auto;padding:14px;background:#eef1e9;border-radius:8px;font-size:12px}
.answer-body :deep(code){font-family:var(--mono);font-size:.9em}.answer-body :deep(blockquote){border-left:3px solid #b6c8ac;margin:12px 0;padding-left:14px;color:#6a786d}
.answer-body :deep(.citation){display:inline-grid;place-items:center;border:0;border-radius:4px;background:#e3ecd9;color:#315b45;font-size:10px;min-width:19px;height:19px;vertical-align:middle;margin:0 3px;cursor:pointer}
</style>
