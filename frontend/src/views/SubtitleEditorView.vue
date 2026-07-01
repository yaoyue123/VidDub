<script setup lang="ts">
/**
 * Phase 12 SubtitleEditorView — DESIGN.md §5.4 split-screen.
 *
 * Left: video player (final.mp4 or original.mp4 fallback)
 * Right: compact bilingual subtitle list (single-line edit per row)
 *
 * Click subtitle row → video jumps to segment.start + auto-play.
 * Toolbar: 保存全部 (primary) / 全部重译 / 单行重译 / 导出 SRT / 导出双语
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Refresh, Download, Document, VideoPlay } from '@element-plus/icons-vue'
import axios from 'axios'
import { subtitlesApi } from '@/api'

const route = useRoute()
const router = useRouter()
const videoId = computed(() => Number(route.params.videoId))

interface Segment {
  id: number
  start: number
  end: number
  text: string
  text_zh: string
  _dirty?: boolean
  _retranslating?: boolean
}

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const video = ref<any>(null)
const segments = ref<Segment[]>([])
const currentSegmentId = ref<number | null>(null)

// ── Video player refs ──
const videoEl = ref<HTMLVideoElement | null>(null)
const videoKind = ref<'final' | 'original'>('final')
const videoUrl = computed(() => `/api/dub/${videoId.value}/preview/${videoKind.value}`)

function fmt(s: number): string {
  if (s == null || isNaN(s)) return '00:00.0'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1)
  return `${String(m).padStart(2, '0')}:${sec.padStart(4, '0')}`
}

function fmtDuration(seg: Segment): string {
  const d = (seg.end || 0) - (seg.start || 0)
  return d >= 0 ? `${d.toFixed(1)}s` : '-'
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const vRes = await axios.get(`/api/videos/${videoId.value}`)
    video.value = vRes.data

    let srtText = ''
    try {
      const srtRes = await axios.get<string>(
        `/api/dub/${videoId.value}/subtitle`,
        { responseType: 'text', transformResponse: (d) => d },
      )
      srtText = srtRes.data || ''
    } catch {
      // subtitle not available yet — empty is fine
    }

    segments.value = parseSrt(srtText).map((s, i) => ({
      id: i, start: s.start, end: s.end, text: s.text_en || '', text_zh: s.text_zh || s.text || '',
    }))
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function parseSrt(text: string) {
  const out: { start: number; end: number; text: string; text_en?: string; text_zh?: string }[] = []
  const blocks = text.trim().split(/\r?\n\r?\n/)
  for (const b of blocks) {
    const linesList = b.split(/\r?\n/).filter((l) => l.trim() !== '')
    if (linesList.length < 2) continue
    let i = 0
    if (/^\d+$/.test(linesList[0].trim())) i = 1
    const tm = linesList[i]?.match(/([\d:,]+)\s*-->\s*([\d:,]+)/)
    if (!tm) continue
    const start = parseSrtTime(tm[1])
    const end = parseSrtTime(tm[2])
    i++
    const t = linesList.slice(i).join('\n')
    // Bilingual SRT: first line is original, second line is translation
    const parts = t.split('\n').filter(Boolean)
    const text_en = parts.length > 1 ? parts[0].trim() : ''
    const text_zh = parts.length > 1 ? parts.slice(1).join('\n').trim() : t.trim()
    out.push({ start, end, text: text_zh || text_en, text_en, text_zh })
  }
  return out
}

function parseSrtTime(t: string): number {
  const m = t.match(/(\d+):(\d+):(\d+)[,\.](\d+)/)
  if (!m) return 0
  const [, h, mi, s, ms] = m
  return Number(h) * 3600 + Number(mi) * 60 + Number(s) + Number(ms) / 1000
}

function secondsToSrtTime(s: number): string {
  if (s < 0) s = 0
  const ms = Math.round((s - Math.floor(s)) * 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')},${String(ms).padStart(3, '0')}`
}

function buildSrt(useZh: boolean): string {
  const lines: string[] = []
  segments.value.forEach((seg, i) => {
    lines.push(String(i + 1))
    lines.push(`${secondsToSrtTime(seg.start)} --> ${secondsToSrtTime(seg.end)}`)
    lines.push(useZh ? seg.text_zh : seg.text)
    lines.push('')
  })
  return lines.join('\n')
}

function buildBilingualSrt(): string {
  const lines: string[] = []
  segments.value.forEach((seg, i) => {
    lines.push(String(i + 1))
    lines.push(`${secondsToSrtTime(seg.start)} --> ${secondsToSrtTime(seg.end)}`)
    lines.push(seg.text)
    lines.push(seg.text_zh)
    lines.push('')
  })
  return lines.join('\n')
}

function downloadText(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/plain; charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function exportSrt() { downloadText(buildSrt(true), `subtitle_${videoId.value}_zh.srt`) }
function exportBilingualSrt() { downloadText(buildBilingualSrt(), `subtitle_${videoId.value}_bilingual.srt`) }

// ── Click segment → jump video + play ──
function jumpToSegment(seg: Segment) {
  currentSegmentId.value = seg.id
  const el = videoEl.value
  if (!el) return
  // Force the source to final.mp4 / original.mp4 depending on toggle
  if (el.src !== videoUrl.value) el.src = videoUrl.value
  el.currentTime = seg.start
  el.play().catch(() => {
    /* user gesture required in some browsers — silent */
  })
}

async function handleEditBlur(seg: Segment) {
  if (!seg._dirty) return
  seg._dirty = false
  saving.value = true
  try {
    const newSrt = buildSrt(true)
    await subtitlesApi.save(videoId.value, { content: newSrt, language: 'zh', source: 'manual' })
    ElMessage.success(`段 #${seg.id + 1} 已保存`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
    seg._dirty = true
  } finally {
    saving.value = false
  }
}

function markDirty(seg: Segment) { seg._dirty = true }

async function retranslateSegment(seg: Segment) {
  if (seg._retranslating) return
  seg._retranslating = true
  try {
    const res = await subtitlesApi.retranslate(videoId.value, seg.id)
    seg.text_zh = res.data.translated_text
    ElMessage.success(`段 #${seg.id + 1} 已重新翻译`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '重新翻译失败')
  } finally {
    seg._retranslating = false
  }
}

async function retranslateAll() {
  try {
    await ElMessageBox.confirm(
      `确认重新翻译全部 ${segments.value.length} 段？这将按顺序调用 SiliconFlow，可能耗时较长。`,
      '全部重新翻译',
      { type: 'warning' },
    )
  } catch { return }
  for (const seg of segments.value) await retranslateSegment(seg)
  ElMessage.success('全部段已重新翻译')
}

async function saveAll() {
  saving.value = true
  try {
    await subtitlesApi.save(videoId.value, {
      content: buildSrt(true), language: 'zh', source: 'manual',
    })
    ElMessage.success('全部字幕已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadData)
onBeforeUnmount(() => {
  const el = videoEl.value
  if (el) el.pause()
})
</script>

<template>
  <div class="subtitle-editor">
    <!-- Header -->
    <div class="editor-header">
      <el-button :icon="ArrowLeft" text @click="router.push('/tasks')">返回任务</el-button>
      <h1 class="editor-title">字幕编辑</h1>
      <span v-if="video" class="text-caption">{{ video.title }}</span>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon closable />

    <!-- Toolbar -->
    <div v-if="!loading && !error" class="editor-toolbar y2b-card y2b-card-pad">
      <div class="toolbar-left">
        <el-button type="primary" :icon="Document" :loading="saving" @click="saveAll">保存全部</el-button>
        <el-button :icon="Refresh" type="warning" @click="retranslateAll" :disabled="segments.length === 0">全部重译</el-button>
      </div>
      <div class="toolbar-right">
        <el-select v-model="videoKind" size="small" style="width: 120px;">
          <el-option label="最终视频" value="final" />
          <el-option label="原视频" value="original" />
        </el-select>
        <el-button :icon="Download" @click="exportSrt" :disabled="segments.length === 0">导出 SRT</el-button>
        <el-button :icon="Download" @click="exportBilingualSrt" :disabled="segments.length === 0">双语 SRT</el-button>
      </div>
    </div>

    <!-- Split view -->
    <div v-if="!loading && !error" class="split-view">
      <!-- Left: video player -->
      <div class="video-pane">
        <video
          ref="videoEl"
          :src="videoUrl"
          controls
          class="video-player"
        />
        <div v-if="currentSegmentId !== null" class="current-seg-hint">
          <el-icon><VideoPlay /></el-icon>
          <span>当前段 #{{ currentSegmentId + 1 }}</span>
        </div>
        <p class="text-caption video-tip">
          点击右侧字幕行 → 视频跳转到该段时间戳并自动播放。
        </p>
      </div>

      <!-- Right: subtitle list -->
      <div class="subs-pane">
        <div v-if="segments.length === 0" class="empty-subs">
          <el-empty description="暂无字幕数据，请先完成转写 + 翻译步骤" />
        </div>

        <div v-else class="subs-list">
          <div
            v-for="seg in segments"
            :key="seg.id"
            class="sub-row"
            :class="{ 'is-current': currentSegmentId === seg.id }"
            @click="jumpToSegment(seg)"
          >
            <div class="sub-header">
              <span class="sub-index num-mono">#{{ String(seg.id + 1).padStart(2, '0') }}</span>
              <span class="sub-time num-mono">{{ fmt(seg.start) }} → {{ fmt(seg.end) }}</span>
              <span class="sub-dur text-caption">{{ fmtDuration(seg) }}</span>
              <el-button
                text size="small"
                :icon="VideoPlay"
                @click.stop="jumpToSegment(seg)"
              />
              <el-button
                text size="small"
                :icon="Refresh"
                :loading="seg._retranslating"
                @click.stop="retranslateSegment(seg)"
              >重译</el-button>
            </div>
            <div class="sub-text sub-text-en">{{ seg.text || '(无原文)' }}</div>
            <el-input
              v-model="seg.text_zh"
              size="small"
              placeholder="中文翻译..."
              @input="markDirty(seg)"
              @blur="handleEditBlur(seg)"
              @click.stop
            />
          </div>
        </div>
      </div>
    </div>

    <el-empty v-if="loading" description="加载中..." />
  </div>
</template>

<style scoped>
.subtitle-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 1400px;
  margin: 0 auto;
}

.editor-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}
.editor-title {
  font-size: var(--fs-2xl);
  font-weight: 600;
  margin: 0;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.toolbar-left, .toolbar-right {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}

.split-view {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
  min-height: calc(100vh - 220px);
}

.video-pane {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  position: sticky;
  top: var(--space-4);
  align-self: flex-start;
}
.video-player {
  width: 100%;
  aspect-ratio: 16/9;
  background: #000;
  border-radius: var(--radius-md);
}
.current-seg-hint {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  background: var(--color-primary-light);
  color: var(--color-primary);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  align-self: flex-start;
}
.video-tip {
  margin: 0;
}

.subs-pane {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  max-height: calc(100vh - 220px);
  overflow-y: auto;
}
.empty-subs {
  padding: var(--space-8) 0;
  text-align: center;
}

.subs-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.sub-row {
  border: 1px solid var(--color-border);
  border-left: 3px solid transparent;
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.sub-row:hover {
  border-color: var(--color-primary-light-7);
}
.sub-row.is-current {
  border-color: var(--color-primary-light-7);
  border-left-color: var(--color-primary);
  background: var(--color-primary-light);
}

.sub-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
}
.sub-index {
  color: var(--color-text-muted);
  font-weight: 600;
  min-width: 32px;
}
.sub-time { color: var(--color-text-regular); }
.sub-dur { margin-left: auto; margin-right: var(--space-2); }

.sub-text {
  font-size: var(--fs-sm);
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
}
.sub-text-en { color: var(--color-text-regular); }
</style>
