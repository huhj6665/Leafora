import type { EventDetail, SpatialResult } from '../types/index.ts'
import { getToken } from './token.ts'

const MAX_ENTRIES = 3
const MAX_IMAGE_URLS_PER_ENTRY = 48
const TERMINAL_TTL_MS = 2 * 60 * 1000
const ACTIVE_TTL_MS = 3 * 1000
const TERMINAL_STATES = new Set(['COMPLETED', 'FAILED', 'CANCELLED'])

export interface InspectionDetailCacheSnapshot {
  event: EventDetail | null
  spatial: SpatialResult | null
  fieldImage: string
  imageUrls: Record<string, string>
}

interface CacheEntry extends InspectionDetailCacheSnapshot {
  key: string
  scope: string
  inspectionId: string
  fieldImageIdentity: string
  dataUpdatedAt: number
  touchedAt: number
  pins: number
}

const entries = new Map<string, CacheEntry>()
let activeScope = ''

function tokenScope(): string {
  const token = getToken()
  if (!token) return ''
  let hash = 2166136261
  for (let index = 0; index < token.length; index += 1) {
    hash ^= token.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

function revokeEntry(entry: CacheEntry) {
  if (entry.fieldImage) URL.revokeObjectURL(entry.fieldImage)
  Object.values(entry.imageUrls).forEach(URL.revokeObjectURL)
}

function trimImages(entry: CacheEntry) {
  if (entry.pins > 0) return
  const imageIds = Object.keys(entry.imageUrls)
  while (imageIds.length > MAX_IMAGE_URLS_PER_ENTRY) {
    const imageId = imageIds.shift()!
    URL.revokeObjectURL(entry.imageUrls[imageId])
    delete entry.imageUrls[imageId]
  }
}

export function clearInspectionDetailCache() {
  entries.forEach(revokeEntry)
  entries.clear()
  activeScope = tokenScope()
}

function syncScope(): string {
  const scope = tokenScope()
  if (!scope || (activeScope && activeScope !== scope)) clearInspectionDetailCache()
  activeScope = scope
  return scope
}

function ttl(entry: CacheEntry): number {
  return TERMINAL_STATES.has(entry.event?.status || '') ? TERMINAL_TTL_MS : ACTIVE_TTL_MS
}

function prune() {
  const now = Date.now()
  for (const [key, entry] of entries) {
    if (entry.pins === 0 && now - entry.dataUpdatedAt > ttl(entry)) {
      revokeEntry(entry)
      entries.delete(key)
    }
  }
  const removable = [...entries.values()]
    .filter(entry => entry.pins === 0)
    .sort((first, second) => first.touchedAt - second.touchedAt)
  while (entries.size > MAX_ENTRIES && removable.length) {
    const entry = removable.shift()!
    revokeEntry(entry)
    entries.delete(entry.key)
  }
}

function cacheKey(scope: string, inspectionId: string) {
  return `${scope}:${inspectionId}`
}

function ensureEntry(inspectionId: string): CacheEntry | null {
  const scope = syncScope()
  if (!scope) return null
  const key = cacheKey(scope, inspectionId)
  let entry = entries.get(key)
  if (!entry) {
    entry = {
      key, scope, inspectionId, event: null, spatial: null, fieldImage: '',
      fieldImageIdentity: '', imageUrls: {}, dataUpdatedAt: Date.now(),
      touchedAt: Date.now(), pins: 0,
    }
    entries.set(key, entry)
  }
  entry.touchedAt = Date.now()
  return entry
}

export function spatialSnapshotIdentity(spatial: SpatialResult): string {
  return JSON.stringify([
    spatial.field.field_id,
    spatial.field.version,
    spatial.field.pixel_boundary,
  ])
}

export function acquireInspectionDetailCache(inspectionId: string): InspectionDetailCacheSnapshot | null {
  prune()
  const entry = ensureEntry(inspectionId)
  if (!entry) return null
  entry.pins += 1
  const fresh = Date.now() - entry.dataUpdatedAt <= ttl(entry)
  if (!fresh) {
    return { event: null, spatial: null, fieldImage: '', imageUrls: { ...entry.imageUrls } }
  }
  return {
    event: entry.event,
    spatial: entry.spatial,
    fieldImage: entry.spatial && entry.fieldImageIdentity === spatialSnapshotIdentity(entry.spatial)
      ? entry.fieldImage : '',
    imageUrls: { ...entry.imageUrls },
  }
}

export function releaseInspectionDetailCache(inspectionId: string) {
  const scope = activeScope
  const entry = scope ? entries.get(cacheKey(scope, inspectionId)) : null
  if (entry) {
    entry.pins = Math.max(0, entry.pins - 1)
    trimImages(entry)
  }
  prune()
}

export function cacheInspectionEvent(inspectionId: string, value: EventDetail) {
  const entry = ensureEntry(inspectionId)
  if (!entry) return
  entry.event = value
  entry.dataUpdatedAt = entry.touchedAt = Date.now()
  prune()
}

export function cacheInspectionSpatial(inspectionId: string, value: SpatialResult) {
  const entry = ensureEntry(inspectionId)
  if (!entry) return
  const identity = spatialSnapshotIdentity(value)
  if (entry.fieldImage && (!value.field.base_map_url || entry.fieldImageIdentity !== identity)) {
    URL.revokeObjectURL(entry.fieldImage)
    entry.fieldImage = ''
    entry.fieldImageIdentity = ''
  }
  entry.spatial = value
  entry.dataUpdatedAt = entry.touchedAt = Date.now()
  prune()
}

export function cacheInspectionFieldImage(
  inspectionId: string, identity: string, objectUrl: string,
) {
  const entry = ensureEntry(inspectionId)
  if (!entry) {
    URL.revokeObjectURL(objectUrl)
    return
  }
  if (entry.fieldImage && entry.fieldImage !== objectUrl) URL.revokeObjectURL(entry.fieldImage)
  entry.fieldImage = objectUrl
  entry.fieldImageIdentity = identity
  entry.touchedAt = Date.now()
}

export function cacheInspectionImage(inspectionId: string, imageId: string, objectUrl: string) {
  const entry = ensureEntry(inspectionId)
  if (!entry) {
    URL.revokeObjectURL(objectUrl)
    return
  }
  const previous = entry.imageUrls[imageId]
  if (previous && previous !== objectUrl) URL.revokeObjectURL(previous)
  entry.imageUrls = { ...entry.imageUrls, [imageId]: objectUrl }
  entry.touchedAt = Date.now()
  trimImages(entry)
}

export function clearInspectionDetailCacheIfSignedOut() {
  if (!getToken()) clearInspectionDetailCache()
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', event => {
    if (event.key === 'tld_access_token') syncScope()
  })
}
