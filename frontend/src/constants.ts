/** Shared constants for task steps, statuses, and UI labels. */

/** Map dubbing pipeline step keys to Chinese labels. */
export const TASK_STEP_LABELS: Record<string, string> = {
  download: '下载',
  transcribe: '转写',
  translate: '翻译',
  synthesize: '合成',
  compose: '混音',
  publish: '发布',
}

/** Ordered list of dubbing pipeline steps. */
export const STEP_ORDER = ['download', 'transcribe', 'translate', 'synthesize', 'compose', 'publish'] as const

/** Status metadata: label + Element Plus type. */
export const STATUS_META: Record<string, { label: string; type: string }> = {
  pending: { label: '等待中', type: 'info' },
  running: { label: '运行中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  cancelled: { label: '已取消', type: 'info' },
  paused: { label: '已暂停', type: 'info' },
}
