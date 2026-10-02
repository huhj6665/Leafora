import test from 'node:test'
import assert from 'node:assert/strict'
import { filterDiseaseGrids, filterDiseasePoints, summarizeDetections } from '../src/utils/inspection-evidence.ts'

const target = (disease, confidence) => ({ class: disease, confidence, bbox: [1, 2, 3, 4] })
const original = (id, data, results, status = 'completed') => ({ image_id: id, data_id: data,
  image_type: 'original', cloud_detection: { status, results } })
const grid = ids => ({ cell_id: 'G01', valid_sample_count: 90, risk_score: 95,
  risk_level: 'HIGH', images: ids.map(image_id => ({ image_id })) })

test('aggregate view remains unchanged; class view counts samples, not images/targets', () => {
  const images = [original('a', 's1', [target('Frogeye', .9), target('Frogeye', .7)]),
    original('b', 's1', [target('Frogeye', .8)]), original('c', 's2', [target('Mosaic', .95)]),
    original('d', 's3', []), { ...original('ann', 's1', [target('Frogeye', .9)]), image_type: 'annotated' }]
  const grids = [grid(['a', 'a', 'b', 'c', 'd', 'ann'])]
  assert.equal(filterDiseaseGrids(grids, images, ''), grids)
  const result = filterDiseaseGrids(grids, images, 'Frogeye')[0]
  assert.equal(result.valid_sample_count, 3)
  assert.equal(result.suspicious_count, 1)
  assert.equal(result.risk_score, 30)
  assert.equal(result.risk_level, 'ATTENTION')
  assert.equal(filterDiseaseGrids(grids, images, 'Mosaic')[0].risk_score, 31.7)
  assert.equal(grids[0].risk_score, 95)
})

test('failed, absent and partially processed samples are not treated as healthy', () => {
  const images = [original('a', 's1', []), original('b', 's2', [], 'failed'),
    original('c', 's3', [target('Frogeye', .9)]), original('d', 's3', [], 'pending')]
  const result = filterDiseaseGrids([grid(['a', 'b', 'c', 'd', 'missing'])], images, 'Wildfire')[0]
  assert.equal(result.valid_sample_count, 1)
  assert.equal(result.risk_level, 'INSUFFICIENT')
  assert.equal(filterDiseaseGrids([grid([])], images, 'Frogeye')[0].risk_level, 'INSUFFICIENT')
})

test('class scores honor the existing risk thresholds and confidence limits', () => {
  for (const [confidence, expected] of [[0, 'LOW'], [.15, 'ATTENTION'], [.35, 'REVIEW'], [.6, 'HIGH'], [2, 'HIGH']]) {
    const images = ['a', 'b', 'c'].map(id => original(id, id, [target('Frogeye', confidence)]))
    const result = filterDiseaseGrids([grid(['a', 'b', 'c'])], images, 'Frogeye')[0]
    assert.equal(result.risk_level, expected)
    assert.ok(result.risk_score <= 100)
  }
})

test('result summary preserves distinct classes, counts and confidence range', () => {
  assert.deepEqual(summarizeDetections([target('Frogeye', .9), target('Frogeye', .7), target('Mosaic', .8)]), [
    { class: 'Frogeye', count: 2, min: .7, max: .9 }, { class: 'Mosaic', count: 1, min: .8, max: .8 },
  ])
  assert.deepEqual(summarizeDetections([]), [])
})

test('class markers use actual sample positions and matching completed results only', () => {
  const images = [original('a', 's1', [target('Frogeye', .9), target('Mosaic', .7)]),
    original('b', 's2', [target('Frogeye', .8)], 'failed')]
  const points = [{x:10,y:20,confidence:.9,images:[{image_id:'a'}]},
    {x:30,y:40,confidence:.8,images:[{image_id:'b'}]}]
  assert.equal(filterDiseasePoints(points, images, ''), points)
  assert.deepEqual(filterDiseasePoints(points, images, 'Mosaic'), [{...points[0],confidence:.7}])
  assert.deepEqual(filterDiseasePoints(points, images, 'Wildfire'), [])
})
