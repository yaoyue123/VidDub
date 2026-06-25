<script setup lang="ts">
/**
 * F8: AudioPreview — 可复用的音频试听组件。
 *
 * 功能：
 *   - src 属性变化时自动 load
 *   - 支持 seek-to-start（点击行跳到指定秒数）
 *   - 显示播放进度 + 时长
 *
 * 用法：
 *   <AudioPreview :src="url" :seek-to="segment.start" />
 */
import { ref, watch, onBeforeUnmount } from 'vue'

const props = defineProps<{
  src: string
  /** 初始/外部触发的跳转秒数（变化时会 seek） */
  seekTo?: number
  /** 是否自动播放（seek 后） */
  autoplay?: boolean
}>()

const audioEl = ref<HTMLAudioElement | null>(null)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const error = ref('')

function fmt(sec: number): string {
  if (!sec || !isFinite(sec)) return '00:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function togglePlay() {
  const el = audioEl.value
  if (!el) return
  if (playing.value) {
    el.pause()
  } else {
    el.play().catch((e) => {
      error.value = String(e?.message || e)
    })
  }
}

function onTimeUpdate() {
  const el = audioEl.value
  if (!el) return
  currentTime.value = el.currentTime
}

function onLoadedMeta() {
  const el = audioEl.value
  if (!el) return
  duration.value = el.duration
  error.value = ''
}

function onEnded() {
  playing.value = false
}

function onError() {
  error.value = '音频加载失败'
  playing.value = false
}

function onPlay() {
  playing.value = true
}
function onPause() {
  playing.value = false
}

function seekToStart(sec: number) {
  const el = audioEl.value
  if (!el || !isFinite(sec)) return
  el.currentTime = Math.max(0, sec)
  if (props.autoplay && !playing.value) {
    el.play().catch(() => { /* ignore */ })
  }
}

watch(
  () => props.seekTo,
  (val) => {
    if (typeof val === 'number' && isFinite(val)) {
      seekToStart(val)
    }
  },
)

watch(
  () => props.src,
  () => {
    error.value = ''
    playing.value = false
    currentTime.value = 0
    duration.value = 0
  },
)

onBeforeUnmount(() => {
  const el = audioEl.value
  if (el) {
    el.pause()
  }
})
</script>

<template>
  <div class="audio-preview">
    <audio
      ref="audioEl"
      :src="src"
      preload="metadata"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMeta"
      @ended="onEnded"
      @error="onError"
      @play="onPlay"
      @pause="onPause"
    />
    <el-button
      size="small"
      :type="playing ? 'warning' : 'primary'"
      :icon="playing ? 'VideoPause' : 'VideoPlay'"
      @click="togglePlay"
    >
      {{ playing ? '暂停' : '播放' }}
    </el-button>
    <span class="audio-time">{{ fmt(currentTime) }} / {{ fmt(duration) }}</span>
    <el-slider
      :model-value="currentTime"
      :min="0"
      :max="duration || 100"
      :step="0.1"
      :show-tooltip="false"
      style="flex: 1; min-width: 120px"
      @input="(v: number) => { if (audioEl) audioEl.currentTime = v }"
    />
    <span v-if="error" class="audio-error">{{ error }}</span>
  </div>
</template>

<style scoped>
.audio-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.audio-time {
  font-family: 'Courier New', Courier, monospace;
  font-size: 12px;
  color: #606266;
  min-width: 90px;
}
.audio-error {
  color: #f56c6c;
  font-size: 12px;
}
</style>
