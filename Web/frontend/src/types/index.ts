// 与后端统一响应结构对应：{ code, message, data }
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface TokenData {
  access_token: string
  token_type: string
  user_id: number
}

export interface IdentityItem {
  identity_type: string
  identifier: string
  created_at?: string | null
}

export interface UserProfile {
  user_id: number
  nickname: string
  avatar?: string | null
  status: number
  email?: string | null
  email_verified: boolean
  has_phone_password: boolean
  created_at?: string | null
  identities: IdentityItem[]
}

export interface EmailStatus {
  has_email: boolean
  verified: boolean
  email?: string | null
}

export interface DeviceItem {
  id: number
  device_id: string
  device_name: string
  status: number
  bind_time?: string | null
  operating_status: 'RUNNING' | 'SHUTDOWN' | 'ERROR' | 'DISABLED'
  communication_status: 'ONLINE' | 'OFFLINE'
  last_seen_at?: string | null
  cpu_temperature?: number | null
  cpu_usage?: number | null
  memory_usage?: number | null
  storage_usage?: number | null
  network_status?: 'online' | 'offline' | 'degraded' | null
  inspection_count: number
  sync_status: 'IDLE' | 'PENDING' | 'SYNCING' | 'SYNCED' | string
  pending_sync_count: number
  standard_state?: 'READY' | 'BUSY' | 'SYNCING' | 'OFFLINE' | 'ERROR' | 'DISABLED' | 'ONLINE_NOT_READY'
  gps_fix?: string | null
  rtk_status?: string | null
  camera_status?: string | null
  inference_status?: string | null
  current_inspection_id?: string | null
  current_inspection_name?: string | null
  current_inspection_status?: string | null
}

export interface FieldItem {
  field_id: string
  name: string
  description?: string | null
  status: 'READY' | 'DISABLED'
  data_source: string
  calibration_status: string
  coordinate_system: string
  base_map_url?: string | null
  pixel_boundary: number[][]
  geo_boundary: { type: 'Polygon'; coordinates: number[][][] }
  control_points: Array<{ pixel: number[]; wgs84: number[] }>
  transform_params: Record<string, number | string | Record<string, string>>
  version: number
  inspection_count: number
  last_inspection_at?: string | null
}

export interface LiveData {
  device_id: string
  inspection_id?: string
  field_id?: string
  task_status?: string
  raw: Record<string, any> | null
  display: Record<string, any> | null
  received_at?: string | null
  age_ms?: number | null
  link_state: 'LIVE' | 'DELAYED' | 'DISCONNECTED' | 'NO_DATA'
  device_state: string
}

export interface SpatialResult {
  inspection_id: string
  field: FieldItem
  track: Array<{ x: number; y: number; lng: number; lat: number; sequence?: number }>
  risk_grids: Array<{ cell_id: string; seed: number[]; polygon: number[][]; polygon_percent: number[][]; x: number; y: number; width: number; height: number; x_pct: number; y_pct: number; width_pct: number; height_pct: number; sample_count: number; valid_sample_count: number; suspicious_count: number; risk_score: number; risk_level: string; images: Array<{ image_id: string; url: string }> }>
  disease_points: Array<{ x: number; y: number; confidence: number; images?: Array<{ image_id: string; url: string }> }>
  risk_formula: string
  risk_thresholds: Record<string, string>
}

export interface InspectionEventItem {
  inspection_id: string
  device_id: string
  field_id?: string | null
  field_version?: number | null
  field_name?: string | null
  run_mode?: string | null
  data_provenance?: string | null
  name: string
  location_name?: string | null
  status: 'CREATED' | 'START_REQUESTED' | 'STARTING' | 'RUNNING' | 'RUNNING_OFFLINE' | 'ENDING' | 'SYNCING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  sync_status: string
  pending_sync_count: number
  started_at?: string | null
  ended_at?: string | null
  created_at?: string | null
  failure_reason?: string | null
  sample_count: number
  image_count: number
  target_count: number
}

export interface EventDetail extends InspectionEventItem {
  track: { lng: number; lat: number; time?: string; data_id: string }[]
  environment: { time: string; temperature: number | null; humidity: number | null; co2: number | null; light: number | null; valid?: boolean }[]
  environment_summary: { temperature: number | null; humidity: number | null; co2: number | null; light: number | null; sampled_at?: string | null; valid_count: number }
  images: Array<{
    image_id: string; data_id: string; captured_at: string; image_type: string; url: string
    cloud_detection?: CloudDetection | null
  }>
  device_status?: { cpu_usage: number; memory_usage: number; temperature: number; storage_usage?: number | null; network_status?: string | null } | null
  risk: { score: number; level: 'LOW' | 'MEDIUM' | 'HIGH'; target_count: number; avg_confidence: number; disclaimer: string }
}

export interface AnalysisOverview {
  metrics: { events: number; active_events: number; samples: number; week_samples: number; devices: number; targets: number }
  environment_trends: { time: string; temperature: number | null; humidity: number | null; co2: number | null; light: number | null }[]
  recent_events: Array<{ inspection_id: string; name: string; status: string; device_id: string; started_at?: string | null }>
}

export interface MapData {
  tracks: Array<{ inspection_id: string; points: Array<{ lng: number; lat: number; data_id: string }> }>
  disease_points: Array<{ lng: number; lat: number; data_id: string; count: number; score: number; level: string; classes: string[] }>
  regions: Array<{ level: string; score: number; polygon: number[][]; point_count: number }>
  sampling: string
  region_method: string
}

export interface HealthInfo {
  status: string
  database: string
  environment: string
  sms_configured: boolean
}

// ---- 巡检数据 / 图片 / 云端检测 ----

export interface InspectionListItem {
  id: number
  device_id: string
  data_id: string
  schema_version: string
  captured_at?: string | null
  received_at?: string | null
}

export interface DetectionResultItem {
  class: string
  confidence: number
  bbox: number[]
}

export interface CloudDetection {
  status: string
  model_name?: string | null
  model_version?: string | null
  weights_identifier?: string | null
  processed_at?: string | null
  has_target?: boolean | null
  results: DetectionResultItem[]
  error_message?: string | null
}

export interface InspectionImage {
  image_id: string
  image_type: string
  upload_status: string
  content_type?: string | null
  size_bytes?: number
  url: string
  cloud_detection?: CloudDetection | null
}

export interface InspectionFull {
  schema_version: string
  device_id: string
  data_id: string
  timestamp?: string | null
  location: Record<string, unknown> | null
  environment: Record<string, unknown> | null
  detection: { has_target: boolean; results: DetectionResultItem[] }
  device_status: Record<string, unknown> | null
  images: InspectionImage[]
  cloud_detection: CloudDetection | null
}

export interface InspectionListData {
  total: number
  page: number
  page_size: number
  items: InspectionListItem[]
}

export interface UploadImageResult {
  image_id: string
  image_type: string
  upload_status: string
  cloud_detection: CloudDetection
}

export interface ReprocessResult {
  image_id: string
  cloud_detection: CloudDetection
}
