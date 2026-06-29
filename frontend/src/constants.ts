/** Shared constants for task steps, statuses, and UI labels. */

/** Map dubbing pipeline step keys to Chinese labels. */
export const TASK_STEP_LABELS: Record<string, string> = {
  download: '下载',
  transcribe: '转写',
  translate: '翻译',
  synthesize: '合成配音',
  compose: '混音 + 成片',
  publish: '发布',
  idle: '空闲',
}

/** Ordered list of dubbing pipeline steps. */
export const STEP_ORDER = ['download', 'transcribe', 'translate', 'synthesize', 'compose', 'publish'] as const

/** Phase 4 task type literals (state machine per D-13). */
export const DUB_TASK_TYPES = ['download', 'transcribe', 'translate', 'synthesize', 'compose'] as const

/** Status metadata: label + Element Plus color + icon name. */
export const STATUS_META: Record<string, { label: string; color: string; icon: string }> = {
  pending:      { label: '等待中',   color: 'info',    icon: 'Clock' },
  running:      { label: '运行中',   color: 'warning', icon: 'Loading' },
  downloading:  { label: '下载中',   color: 'warning', icon: 'Download' },
  downloaded:   { label: '已下载',   color: 'primary', icon: 'Files' },
  transcribing: { label: '转写中',   color: 'warning', icon: 'Loading' },
  transcribed:  { label: '已转写',   color: 'primary', icon: 'Document' },
  translated:   { label: '已翻译',   color: 'primary', icon: 'Document' },
  synthesized:  { label: '已合成',   color: 'primary', icon: 'Microphone' },
  composed:     { label: '已混音',   color: 'primary', icon: 'Film' },
  completed:    { label: '已完成',   color: 'success', icon: 'CircleCheck' },
  failed:       { label: '失败',     color: 'danger',  icon: 'CircleClose' },
  cancelled:    { label: '已取消',   color: 'info',    icon: 'RemoveFilled' },
}
