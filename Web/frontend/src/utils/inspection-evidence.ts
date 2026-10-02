import type { DetectionResultItem, EventDetail, SpatialResult } from '../types/index'

export const diseaseClasses = ['Frogeye', 'Mosaic', 'Budworm damage', 'Wildfire'] as const
export const diseaseNames: Record<string, string> = {
  Frogeye: '蛙眼叶斑病', Mosaic: '花叶病', 'Budworm damage': '烟青虫危害', Wildfire: '野火病',
}
export function diseaseName(value: string) { return diseaseNames[value] || value }

export function summarizeDetections(results: DetectionResultItem[]) {
  const groups = new Map<string, { class: string; count: number; min: number; max: number }>()
  for (const result of results) {
    const confidence = Math.max(0, Math.min(1, result.confidence))
    const group = groups.get(result.class) || { class: result.class, count: 0, min: 1, max: 0 }
    group.count++
    group.min = Math.min(group.min, confidence)
    group.max = Math.max(group.max, confidence)
    groups.set(result.class, group)
  }
  return [...groups.values()]
}

// Class views use cloud results only. No API changes, synthetic locations or
// extra requests: the existing grid image IDs already encode sample membership.
export function filterDiseaseGrids(grids: SpatialResult['risk_grids'], images: EventDetail['images'], disease: string) {
  if (!disease) return grids
  const originals = new Map(images.filter(image => image.image_type === 'original').map(image => [image.image_id, image]))
  return grids.map(grid => {
    const samples = new Map<string, EventDetail['images']>()
    for (const item of grid.images) {
      const image = originals.get(item.image_id)
      if (!image) continue
      const sample = samples.get(image.data_id) || []
      if (!sample.some(existing => existing.image_id === image.image_id)) sample.push(image)
      samples.set(image.data_id, sample)
    }
    const confidences = [...samples.values()]
      .filter(sample => sample.every(image => image.cloud_detection?.status === 'completed'))
      .map(sample => Math.max(0, ...sample.flatMap(image => (image.cloud_detection?.results || [])
        .filter(result => result.class === disease).map(result => Math.max(0, Math.min(1, result.confidence))))))
    const valid = confidences.length
    const score = valid ? Math.round(1000 * confidences.reduce((sum, value) => sum + value, 0) / valid) / 10 : 0
    return { ...grid, valid_sample_count: valid, suspicious_count: confidences.filter(value => value > 0).length,
      risk_score: score, risk_level: valid < 3 ? 'INSUFFICIENT' : score < 15 ? 'LOW' : score < 35 ? 'ATTENTION' : score < 60 ? 'REVIEW' : 'HIGH' }
  })
}

export function filterDiseasePoints(points: SpatialResult['disease_points'], images: EventDetail['images'], disease: string) {
  if (!disease) return points
  const originals = new Map(images.filter(image => image.image_type === 'original').map(image => [image.image_id, image]))
  return points.flatMap(point => {
    const results = (point.images || []).flatMap(item => {
      const image = originals.get(item.image_id)
      return image?.cloud_detection?.status === 'completed' ? image.cloud_detection.results : []
    }).filter(result => result.class === disease)
    return results.length ? [{ ...point, confidence: Math.max(...results.map(result => result.confidence)) }] : []
  })
}
