<script setup lang="ts">
/**
 * VideoCard.vue — Reusable presentational component for displaying a
 * single YouTube video result as a card with thumbnail, metadata, and
 * "Add to Pipeline" action button.
 *
 * Used as the atomic unit of the DiscoverView results grid (Plan 10-03).
 * Pure presentational: no Pinia or API dependencies. All data arrives
 * via props; user actions are emitted upward.
 */
import { ref } from 'vue'
import { ElButton, ElIcon } from 'element-plus'
import { Plus, VideoPlay } from '@element-plus/icons-vue'
import type { DiscoveryItem } from '@/api'

const props = withDefaults(defineProps<{
  video: DiscoveryItem
  loading?: boolean
  actionLabel?: string
  compact?: boolean
}>(), {
  loading: false,
  actionLabel: '加入搬运',
  compact: false,
})

const emit = defineEmits<{
  (e: 'add-to-pipeline'): void
}>()

const thumbError = ref(false)

/** Format view count to K/M notation (e.g. 1500 -> "1.5K"). */
function formatViews(n: number | null | undefined): string {
  if (n === null || n === undefined) return '-'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

/** Format duration in seconds to M:SS (e.g. 845 -> "14:05"). */
function formatDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return '-'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Format date string to zh-CN locale. */
function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleDateString('zh-CN')
  } catch {
    return '-'
  }
}
</script>

<template>
  <div
    class="video-card y2b-card"
    :class="{ 'is-compact': compact, 'is-loading': loading }"
  >
    <!-- ── Loading skeleton ── -->
    <template v-if="loading">
      <div class="card-thumb skeleton">
        <div class="skeleton-block thumb-skeleton" />
      </div>
      <div class="card-body">
        <div class="skeleton-block title-skeleton" />
        <div class="skeleton-block channel-skeleton" />
        <div class="skeleton-block meta-skeleton" />
        <div class="skeleton-block btn-skeleton" />
      </div>
    </template>

    <!-- ── Actual content ── -->
    <template v-else>
      <!-- Thumbnail -->
      <div class="card-thumb">
        <img
          v-if="video.thumbnail_url && !thumbError"
          :src="video.thumbnail_url"
          alt=""
          loading="lazy"
          @error="thumbError = true"
        />
        <div v-else class="thumb-placeholder">
          <el-icon :size="compact ? 24 : 32">
            <VideoPlay />
          </el-icon>
        </div>
        <span class="duration-badge">{{ formatDuration(video.duration) }}</span>
      </div>

      <!-- Card body -->
      <div class="card-body">
        <h3 class="card-title" :title="video.title">{{ video.title }}</h3>
        <p class="card-channel" :title="video.channel">{{ video.channel }}</p>
        <div class="card-meta">
          <span>{{ formatViews(video.view_count) }} 播放</span>
          <span v-if="(video as any).published_at">{{ formatDate((video as any).published_at) }}</span>
        </div>
        <el-button
          size="small"
          type="primary"
          :icon="Plus"
          @click.stop="emit('add-to-pipeline')"
          class="card-action"
        >
          {{ actionLabel }}
        </el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.video-card {
  overflow: hidden;
  transition: box-shadow 0.2s, border-color 0.2s, transform 0.2s;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}
.video-card:hover {
  box-shadow: var(--shadow-subtle);
  border-color: var(--color-primary);
  transform: translateY(-2px);
}
.video-card.is-loading {
  pointer-events: none;
}

/* ── Thumbnail ── */
.card-thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--color-bg-page);
}
.card-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--color-text-muted);
  background: var(--color-bg-soft);
}
.duration-badge {
  position: absolute;
  bottom: var(--space-2);
  right: var(--space-2);
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  font-size: var(--fs-xs);
  font-family: var(--font-mono);
  padding: 1px var(--space-2);
  border-radius: var(--radius-sm);
  line-height: 1.5;
  font-variant-numeric: tabular-nums;
}

/* ── Card body ── */
.card-body {
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}
.card-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--color-text);
  line-height: 1.4;
  margin: 0 0 2px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: break-word;
}
.card-channel {
  font-size: var(--fs-xs);
  color: var(--color-text-muted);
  margin: 0 0 2px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--fs-xs);
  color: var(--color-text-regular);
  font-variant-numeric: tabular-nums;
}
.card-action {
  margin-top: 6px;
  width: 100%;
}

/* ── Skeleton loading ── */
@keyframes shimmer {
  0% { background-position: -200px 0; }
  100% { background-position: calc(200px + 100%) 0; }
}
.skeleton-block {
  background: linear-gradient(
    90deg,
    var(--color-bg-soft) 25%,
    var(--color-border) 50%,
    var(--color-bg-soft) 75%
  );
  background-size: 200px 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}
.thumb-skeleton {
  width: 100%;
  height: 100%;
}
.title-skeleton {
  height: 14px;
  width: 85%;
  margin-bottom: 6px;
}
.channel-skeleton {
  height: 12px;
  width: 55%;
  margin-bottom: 6px;
}
.meta-skeleton {
  height: 12px;
  width: 40%;
  margin-bottom: 8px;
}
.btn-skeleton {
  height: 28px;
  width: 100%;
  border-radius: var(--radius-md);
}

/* ── Compact variant ── */
.is-compact .card-thumb {
  aspect-ratio: 16 / 9;
}
.is-compact .card-body {
  padding: var(--space-2);
}
.is-compact .card-title {
  font-size: var(--fs-xs);
  -webkit-line-clamp: 1;
}
.is-compact .card-channel {
  display: none;
}
.is-compact .card-meta {
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.is-compact .card-action {
  margin-top: 4px;
  font-size: var(--fs-xs);
  height: 24px;
}
</style>
