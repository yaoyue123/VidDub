import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor: unwrap data, normalize errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail || error.message || '网络错误'
    console.error('[API Error]', message)
    return Promise.reject(error)
  },
)

export default api

// ── Phase 5: API namespaces (D5-01..D5-07) ──

// DubApi: Phase 4 配音任务相关
export interface DubCreateRequest {
  youtube_url: string
}
export interface DubCreateResponse {
  video_id: number
  status: string
  task_id: number
}
export interface DubStatusResponse {
  id: number
  youtube_url: string
  title: string
  status: string
  progress_pct: number
  current_step: string
  error_msg: string | null
  final_url: string | null
  srt_url: string | null
  created_at: string
  updated_at: string
}

export const dubApi = {
  /** 创建配音任务 (POST /api/dub) */
  create(body: DubCreateRequest) {
    return api.post<DubCreateResponse>('/dub', body)
  },
  /** 查询配音任务状态 */
  get(id: number) {
    return api.get<DubStatusResponse>(`/dub/${id}`)
  },
  /** 下载最终视频 (返回 URL，浏览器直接访问) */
  downloadUrl(id: number): string {
    return `/api/dub/${id}/download`
  },
  /** 字幕 URL */
  subtitleUrl(id: number): string {
    return `/api/dub/${id}/subtitle`
  },
  /** 断点续跑 */
  resume(id: number) {
    return api.post(`/dub/${id}/resume`)
  },
  /** 预览 URL — dubbing/final/original */
  previewUrl(id: number, kind: 'dubbing' | 'final' | 'original'): string {
    return `/api/dub/${id}/preview/${kind}`
  },
  /** 获取 SRT 文本 */
  fetchSubtitle(id: number) {
    return api.get<string>(`/dub/${id}/subtitle`, {
      responseType: 'text',
      transformResponse: (data) => data, // 防止 axios 解析为 JSON
    })
  },
}

// ConfigApi: Phase 5 增加 testSiliconFlow + 单 key 更新
export interface ConfigItem {
  id?: number
  key: string
  value: string
  description: string | null
}
export interface ConfigTestResult {
  ok: boolean
  latency_ms: number
  error: string | null
}

export const configApi = {
  list() {
    return api.get<ConfigItem[]>('/config')
  },
  updateMany(body: { configs: { key: string; value: string }[] }) {
    return api.put<ConfigItem[]>('/config', body)
  },
  /** 按 key 单独更新 (PUT /api/config/{key}) */
  updateOne(key: string, value: string) {
    return api.put<ConfigItem>(`/config/${encodeURIComponent(key)}`, { value })
  },
  /** 测试 SiliconFlow API Key 连通性 (POST /api/config/test-siliconflow) */
  testSiliconFlow() {
    return api.post<ConfigTestResult>('/config/test-siliconflow', {})
  },
}

// SubtitlesApi: Phase 5 增加 retranslate
export interface RetranslateResult {
  segment_index: number
  original_text: string
  translated_text: string
  updated_files: string[]
}

export const subtitlesApi = {
  list(videoId: number) {
    return api.get(`/subtitles/${videoId}`)
  },
  save(videoId: number, body: { content: string; language: string; source?: string }) {
    return api.post(`/subtitles/${videoId}`, body)
  },
  /** 重新翻译单段中文 (POST /api/subtitles/{video_id}/retranslate?segment_index=N) */
  retranslate(videoId: number, segmentIndex: number) {
    return api.post<RetranslateResult>(
      `/subtitles/${videoId}/retranslate`,
      null,
      { params: { segment_index: segmentIndex } },
    )
  },
}

// StatsApi: Phase 5 增加 dashboard
export interface DashboardRecentTask {
  video_id: number
  title: string
  status: string
  current_step: string
  progress_pct: number
  error_msg: string | null
  created_at: string
  final_url: string | null
}
export interface DashboardData {
  today_count: number
  success_rate: number
  avg_duration_sec: number | null
  api_calls_estimate: number
  recent_tasks: DashboardRecentTask[]
  failed_tasks: DashboardRecentTask[]
}

export const statsApi = {
  overview() {
    return api.get('/stats')
  },
  dashboard() {
    return api.get<DashboardData>('/stats/dashboard')
  },
}

// ── Phase 6: PlatformApi 平台登录 ──
export type PlatformName = 'douyin' | 'bilibili' | 'kuaishou' | 'tencent' | 'xiaohongshu'

export interface PlatformQrStartResponse {
  platform: string
  qr_image_base64: string
  expires_at: number
  message?: string | null
}

export interface PlatformLoginStatusResponse {
  platform: string
  status: string // waiting / scanned / success / expired / failed / timeout / logged_in / not_logged_in / logged_out
  user_info?: Record<string, unknown> | null
  message?: string | null
  cookies?: Record<string, unknown> | null
}

export interface PlatformCheckResponse {
  platform: string
  logged_in: boolean
  expired: boolean
  user_info?: Record<string, unknown> | null
}

export interface PlatformStateItem {
  platform: string
  display_name: string
  logged_in: boolean
  user_info?: Record<string, unknown> | null
}

export interface PlatformAllStateResponse {
  platforms: PlatformStateItem[]
}

export const platformApi = {
  /** POST /api/platform/{platform}/login/start — 启动扫码登录 */
  start(platform: PlatformName) {
    return api.post<PlatformQrStartResponse>(`/platform/${platform}/login/start`)
  },
  /** GET /api/platform/{platform}/login/poll — 轮询登录状态 */
  poll(platform: PlatformName) {
    return api.get<PlatformLoginStatusResponse>(`/platform/${platform}/login/poll`)
  },
  /** GET /api/platform/{platform}/login/status — 查询本地 storage_state */
  status(platform: PlatformName) {
    return api.get<PlatformLoginStatusResponse>(`/platform/${platform}/login/status`)
  },
  /** GET /api/platform/{platform}/check — 主动检测登录态过期 */
  check(platform: PlatformName) {
    return api.get<PlatformCheckResponse>(`/platform/${platform}/check`)
  },
  /** POST /api/platform/{platform}/logout — 登出 */
  logout(platform: PlatformName) {
    return api.post<{ platform: string; success: boolean; message?: string }>(`/platform/${platform}/logout`)
  },
  /** GET /api/platform/state — 所有平台登录态总览 */
  allState() {
    return api.get<PlatformAllStateResponse>('/platform/state')
  },
}

// ── Phase 7: PublishApi 平台自动发布 ──
export type PublishPlatformName = 'douyin' | 'bilibili' | 'kuaishou' | 'tencent' | 'xiaohongshu'

export interface PublishManualBody {
  title?: string
  description?: string
  tags?: string[]
  cover_path?: string
  category_id?: string
  copyright_type?: 'original' | 'repost'
  source_url?: string
}

export interface PublishTriggerResponse {
  record_id: number
  video_id: number
  platform: string
  status: string
  platform_url?: string | null
  error?: string | null
  needs_relogin: boolean
}

export interface AutoPublishResponse {
  video_id: number
  results: Record<string, PublishTriggerResponse>
}

export interface PublishRecordOut {
  id: number
  video_id: number
  platform: string
  status: string
  platform_video_url?: string | null
  title_used?: string | null
  tags_used?: string | null
  cover_path?: string | null
  category_used?: string | null
  copyright_used?: string | null
  error_msg?: string | null
  retry_count: number
  needs_relogin: boolean
  started_at?: string | null
  completed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface PublishRecordsResponse {
  items: PublishRecordOut[]
  total: number
}

export const publishApi = {
  /** POST /api/publish/{video_id}/{platform} — 手动触发单平台发布 */
  trigger(videoId: number, platform: PublishPlatformName, body?: PublishManualBody) {
    return api.post<PublishTriggerResponse>(`/publish/${videoId}/${platform}`, body || null)
  },
  /** POST /api/publish/{video_id}/auto — 自动发布到所有已启用平台 */
  autoPublish(videoId: number) {
    return api.post<AutoPublishResponse>(`/publish/${videoId}/auto`)
  },
  /** GET /api/publish/records — 发布记录列表 (filter) */
  listRecords(filters: {
    video_id?: number
    platform?: PublishPlatformName
    status?: string
    limit?: number
    offset?: number
  } = {}) {
    return api.get<PublishRecordsResponse>('/publish/records', { params: filters })
  },
  /** GET /api/publish/records/{record_id} — 单条记录 */
  getRecord(recordId: number) {
    return api.get<PublishRecordOut>(`/publish/records/${recordId}`)
  },
  /** POST /api/publish/records/{record_id}/retry — 重试 */
  retryRecord(recordId: number) {
    return api.post<PublishTriggerResponse>(`/publish/records/${recordId}/retry`)
  },
}

// ── Phase 8: TitleApi AI 智能标题与标签 ──
export interface TitleGenerateResponse {
  video_id: number
  titles: string[]
  tags: string[]
  summary_zh: string
  cached: boolean
}

export interface TitleSaveBody {
  title_chosen?: string | null
  tags_chosen?: string[] | null
}

export interface TitleSavedState {
  video_id: number
  ai_title_candidates: string[]
  ai_tags_candidates: string[]
  title_chosen: string | null
  tags_chosen: string[]
}

export const titleApi = {
  /** POST /api/title/{video_id}/generate — 触发生成 5 标题 + 8 标签 */
  generate(videoId: number) {
    return api.post<TitleGenerateResponse>(`/title/${videoId}/generate`)
  },
  /** GET /api/title/{video_id} — 读取已保存的候选 + 用户选择 */
  get(videoId: number) {
    return api.get<TitleSavedState>(`/title/${videoId}`)
  },
  /** PUT /api/title/{video_id} — 保存用户选择 */
  update(videoId: number, body: TitleSaveBody) {
    return api.put<TitleSavedState>(`/title/${videoId}`, body)
  },
}

// ── Phase 9: ChannelApi 频道管理 + 定时扫描 ──
export interface ChannelItem {
  id: number
  name: string
  url: string
  enabled: boolean
  scan_interval_hours: number
  last_scanned_at?: string | null
  filter_min_views?: number | null
  filter_max_duration_sec?: number | null
  filter_min_duration_sec?: number | null
  auto_publish: boolean
  created_at?: string
  updated_at?: string
}

export interface ChannelListResponse {
  total: number
  items: ChannelItem[]
}

export interface ChannelSaveBody {
  name: string
  url: string
  enabled?: boolean
  scan_interval_hours?: number
  filter_min_views?: number | null
  filter_max_duration_sec?: number | null
  filter_min_duration_sec?: number | null
  auto_publish?: boolean
}

export interface ScanLogItem {
  id: number
  channel_id: number
  scanned_at: string
  found_count: number
  added_count: number
  error_msg?: string | null
}

export interface ScanNowResponse {
  channel_id: number
  found_count: number
  added_count: number
  error_msg?: string | null
}

export const channelApi = {
  list() {
    return api.get<ChannelListResponse>('/channels')
  },
  get(id: number) {
    return api.get<ChannelItem>(`/channels/${id}`)
  },
  create(body: ChannelSaveBody) {
    return api.post<ChannelItem>('/channels', body)
  },
  update(id: number, body: Partial<ChannelSaveBody>) {
    return api.put<ChannelItem>(`/channels/${id}`, body)
  },
  remove(id: number) {
    return api.delete(`/channels/${id}`)
  },
  /** POST /api/channels/{id}/scan-now — 立即扫描 */
  scanNow(id: number) {
    return api.post<ScanNowResponse>(`/channels/${id}/scan-now`)
  },
  /** GET /api/channels/{id}/scan-logs — 扫描历史 */
  scanLogs(id: number, limit = 20) {
    return api.get<{ items: ScanLogItem[] }>(`/channels/${id}/scan-logs`, {
      params: { limit },
    })
  },
}

// ── Phase 9: BatchApi 批量任务操作 ──
export type BatchAction = 'pause' | 'resume' | 'retry' | 'delete'

export interface BatchActionBody {
  action: BatchAction
  ids: number[]
}

export interface BatchActionResponse {
  success_count: number
  failed_count: number
  errors: { id: number; error: string }[]
}

export const batchApi = {
  /** POST /api/tasks/batch — 批量 pause/resume/retry/delete */
  run(body: BatchActionBody) {
    return api.post<BatchActionResponse>('/tasks/batch', body)
  },
}

// ── Phase 9: ExportApi 导出 CSV/JSON ──
export type ExportFormat = 'csv' | 'json'

export const exportApi = {
  /** GET /api/export/tasks?format=csv|json — 导出任务 (返回 blob 用于下载) */
  tasks(
    format: ExportFormat,
    filters: {
      status?: string
      type?: string
      source?: string
      include_deleted?: boolean
      date_from?: string
      date_to?: string
    } = {},
  ) {
    return api.get('/export/tasks', {
      params: { format, ...filters },
      responseType: 'blob',
    })
  },
  /** 触发浏览器下载 */
  downloadBlob(blob: Blob, filename: string) {
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  },
}

// ── v3.2: Task Detail API ──
export interface SubtitleItem {
  id: number
  language: string
  source: string
  content: string | null
  filepath: string | null
  created_at: string | null
}

export interface TaskDetailResponse {
  task: {
    id: number
    video_id: number
    type: string
    status: string
    progress: number
    message: string | null
    error_msg: string | null
    video_title: string | null
    video_thumbnail_url: string | null
    created_at: string
    updated_at: string
  }
  video: {
    id: number
    title: string
    description: string | null
    youtube_url: string
    channel: string
    duration: number | null
    view_count: number | null
    thumbnail_url: string | null
    status: string
    created_at: string
  }
  subtitles: SubtitleItem[]
}

export const taskDetailApi = {
  /** GET /api/tasks/{task_id}/detail — 任务详情（视频简介 + 字幕） */
  get(taskId: number) {
    return api.get<TaskDetailResponse>(`/tasks/${taskId}/detail`)
  },
}

// ── DiscoveryApi: YouTube 关键词搜索 + 频道扫描 (Phase 2 backend) ──
export interface DiscoveryItem {
  youtube_id: string
  title: string
  channel: string
  duration: number
  view_count: number
  like_count: number
  thumbnail_url: string
  youtube_url: string
}

export interface DiscoveryResponse {
  items: DiscoveryItem[]
  total: number
}

export const discoveryApi = {
  /** POST /api/discovery/search — YouTube 关键词搜索 */
  search(query: string, maxResults = 12) {
    return api.post<DiscoveryResponse>('/discovery/search', {
      query,
      max_results: maxResults,
    })
  },
  /** POST /api/discovery/channel — 扫描频道最新视频 */
  scanChannel(channelUrl: string, maxResults = 12) {
    return api.post<DiscoveryResponse>('/discovery/channel', {
      query: channelUrl,
      max_results: maxResults,
    })
  },
}
