function unwrapItems(value) {
  if (Array.isArray(value)) return value
  return value && Array.isArray(value.items) ? value.items : []
}

function normalizeField(field) {
  const item = field || {}
  const source = String(item.data_source || item.source || '').toUpperCase()
  const calibration = String(item.calibration_status || '').toUpperCase()
  return Object.assign({}, item, {
    field_id: item.field_id || item.id || '',
    display_name: item.name || item.field_name || item.field_id || '未命名烟田',
    ready: String(item.status || '').toUpperCase() === 'READY',
    status_label: String(item.status || 'UNKNOWN').toUpperCase() === 'READY' ? '可巡检' : (item.status || '未知'),
    is_simulated: source === 'DEMO_IMPORT' || calibration === 'SIMULATED' || item.field_id === 'FIELD_A01',
    calibration_label: calibration === 'SIMULATED' ? '模拟校准 · 演示数据' : (item.calibration_status || '未校准'),
    background_url: item.background_url || item.base_map_url || item.image_url || '',
    boundary: Array.isArray(item.boundary) ? item.boundary : (item.boundary_geojson && item.boundary_geojson.coordinates) || [],
  })
}

module.exports = { unwrapItems, normalizeField }
