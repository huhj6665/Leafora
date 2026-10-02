import assert from 'node:assert/strict'
import test from 'node:test'

const storage = new Map()
const revoked = []
globalThis.localStorage = {
  getItem: key => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
}
globalThis.window = { addEventListener() {} }
URL.revokeObjectURL = value => revoked.push(value)

const cache = await import('../src/utils/inspection-detail-cache.ts')

function eventDetail(status) {
  return { status }
}

function spatial(baseMapUrl = '/api/fields/FIELD_A01/base-map') {
  return {
    field: {
      field_id: 'FIELD_A01', version: 2, base_map_url: baseMapUrl,
      pixel_boundary: [[0, 0], [10, 0], [10, 10], [0, 10]],
    },
  }
}

test('detail cache is bounded, account-scoped and releases blob URLs', () => {
  let now = 1_000
  const originalNow = Date.now
  Date.now = () => now
  try {
    storage.set('tld_access_token', 'account-a-token')
    assert.equal(cache.acquireInspectionDetailCache('inspection-1')?.event, null)
    cache.cacheInspectionEvent('inspection-1', eventDetail('COMPLETED'))
    const map = spatial()
    cache.cacheInspectionSpatial('inspection-1', map)
    cache.cacheInspectionFieldImage('inspection-1', cache.spatialSnapshotIdentity(map), 'blob:map-a')
    for (let index = 0; index < 50; index += 1) {
      cache.cacheInspectionImage('inspection-1', `image-${index}`, `blob:image-${index}`)
    }
    cache.releaseInspectionDetailCache('inspection-1')

    const warm = cache.acquireInspectionDetailCache('inspection-1')
    assert.equal(warm?.fieldImage, 'blob:map-a')
    assert.equal(Object.keys(warm?.imageUrls || {}).length, 48)
    assert.deepEqual(revoked.slice(0, 2), ['blob:image-0', 'blob:image-1'])
    cache.releaseInspectionDetailCache('inspection-1')

    storage.set('tld_access_token', 'account-b-token')
    const isolated = cache.acquireInspectionDetailCache('inspection-1')
    assert.equal(isolated?.event, null)
    assert.equal(Object.keys(isolated?.imageUrls || {}).length, 0)
    assert.ok(revoked.includes('blob:map-a'))
    cache.releaseInspectionDetailCache('inspection-1')

    cache.cacheInspectionEvent('inspection-live', eventDetail('RUNNING'))
    cache.cacheInspectionImage('inspection-live', 'live-image', 'blob:live-image')
    now += 4_000
    const expired = cache.acquireInspectionDetailCache('inspection-live')
    assert.equal(expired?.event, null)
    assert.ok(revoked.includes('blob:live-image'))
    cache.releaseInspectionDetailCache('inspection-live')

    storage.delete('tld_access_token')
    cache.clearInspectionDetailCacheIfSignedOut()
  } finally {
    Date.now = originalNow
    cache.clearInspectionDetailCache()
  }
})
