<script setup lang="ts">
/**
 * Phase 12: DubCreateDialog — 3-step wizard.
 * Spec: DESIGN.md §5.2, R2 (keyword search expanded by default).
 *
 * Steps: 1) URL input + keyword search
 *        2) Voice / model / auto-publish defaults
 *        3) Confirm + launch
 *
 * Preserves batch URL capability (R5/R7).
 * Persists last-used config in localStorage for one-click reuse.
 */
import { ref, watch, computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import {
  dubApi,
  configApi,
  platformApi,
  discoveryApi,
  type PlatformStateItem,
  type DiscoveryItem,
} from '@/api'

interface VoiceOption { label: string; value: string }

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'created', videoIds: number[]): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ── Wizard state ──
const currentStep = ref(0)
const urlText = ref('')
const submitting = ref(false)
const showKeywordSearch = ref(true) // R2: expanded by default
const keywordQuery = ref('')
const searchLoading = ref(false)
const searchResults = ref<{ title: string; url: string; thumbnail?: string }[]>([])

const voices: VoiceOption[] = [
  { label: 'alex (男声)', value: 'alex' },
  { label: 'benjamin (男声)', value: 'benjamin' },
  { label: 'charles (男声)', value: 'charles' },
  { label: 'david (男声)', value: 'david' },
  { label: 'anna (女声，推荐)', value: 'anna' },
  { label: 'bella (女声)', value: 'bella' },
  { label: 'claire (女声)', value: 'claire' },
  { label: 'diana (女声)', value: 'diana' },
]
const whisperModels = [
  { label: 'tiny (最快)', value: 'tiny' },
  { label: 'base (推荐)', value: 'base' },
  { label: 'small', value: 'small' },
  { label: 'medium (很慢)', value: 'medium' },
]

// Load persisted config or use DESIGN.md §5.2 defaults.
const persisted = (() => {
  try {
    const raw = localStorage.getItem('viddub.dubConfig')
    if (raw) return JSON.parse(raw)
  } catch {}
  return {}
})()

const cfg = reactive({
  voice: persisted.voice || 'anna',
  whisperModel: persisted.whisperModel || 'tiny',
  autoPublish: persisted.autoPublish !== false, // default ON per spec
  aiTitle: persisted.aiTitle !== false,         // default ON per spec
  speed: persisted.speed ?? 1.0,
  showAdvanced: false,
  volume: persisted.volume ?? 0,
  translationTemp: persisted.translationTemp ?? 0.3,
})

const platformStates = ref<PlatformStateItem[]>([])
const loggedInPlatforms = computed(() => platformStates.value.filter((p) => p.logged_in).map((p) => p.platform))

async function loadPlatformStates() {
  try {
    const res = await platformApi.allState()
    platformStates.value = res.data.platforms
  } catch {
    platformStates.value = []
  }
}

const parsedUrls = computed(() =>
  urlText.value
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0),
)

const invalidUrls = computed(() => parsedUrls.value.filter((u) => !isValidYouTubeUrl(u)))

function isValidYouTubeUrl(url: string): boolean {
  return /^https?:\/\/(www\.|m\.|music\.)?youtube\.com\/|^https?:\/\/youtu\.be\//i.test(url)
}

function canNext() {
  if (currentStep.value === 0) {
    return parsedUrls.value.length > 0 && invalidUrls.value.length === 0
  }
  return true
}

function persistCfg() {
  try {
    localStorage.setItem('viddub.dubConfig', JSON.stringify({
      voice: cfg.voice,
      whisperModel: cfg.whisperModel,
      autoPublish: cfg.autoPublish,
      aiTitle: cfg.aiTitle,
      speed: cfg.speed,
      volume: cfg.volume,
      translationTemp: cfg.translationTemp,
    }))
  } catch {}
}

async function searchKeyword() {
  if (!keywordQuery.value.trim()) return
  searchLoading.value = true
  try {
    const res = await discoveryApi.search(keywordQuery.value, 12)
    const items: DiscoveryItem[] = res.data?.items || []
    searchResults.value = items.map((v) => ({
      title: v.title || '(无标题)',
      url: v.youtube_url || `https://www.youtube.com/watch?v=${v.youtube_id}`,
      thumbnail: v.thumbnail_url,
    }))
    if (searchResults.value.length === 0) {
      ElMessage.info('未找到相关视频。请直接粘贴 YouTube URL。')
    }
  } catch (e: any) {
    searchResults.value = []
    const msg = e?.response?.data?.detail || e?.message || '搜索失败'
    ElMessage.error(`关键词搜索失败：${msg}`)
  } finally {
    searchLoading.value = false
  }
}

function addUrl(url: string) {
  const trimmed = url.trim()
  if (!trimmed) return
  const existing = urlText.value.split(/\r?\n/).map((s) => s.trim())
  if (existing.includes(trimmed)) {
    ElMessage.info('已在列表中')
    return
  }
  urlText.value = (urlText.value ? urlText.value + '\n' : '') + trimmed
}

function next() {
  if (!canNext()) return
  if (currentStep.value === 1) persistCfg()
  currentStep.value = Math.min(currentStep.value + 1, 2)
}
function prev() {
  currentStep.value = Math.max(currentStep.value - 1, 0)
}

function close() {
  visible.value = false
}

async function submit() {
  const urls = parsedUrls.value
  if (urls.length === 0) {
    ElMessage.warning('请输入至少一个 YouTube URL')
    return
  }
  persistCfg()

  // Pre-flight check: warn if auto-publish ON but no platform logged in.
  if (cfg.autoPublish && loggedInPlatforms.value.length === 0) {
    ElMessage.warning('已启用自动发布但未登录任何平台，请先在 Dashboard 扫码登录')
  }

  submitting.value = true
  const createdIds: number[] = []
  let successCount = 0
  let failCount = 0
  const errors: string[] = []

  for (const url of urls) {
    try {
      const res = await dubApi.create({ youtube_url: url })
      createdIds.push(res.data.video_id)
      successCount++
    } catch (e: any) {
      failCount++
      errors.push(`${url}: ${e?.response?.data?.detail || e?.message || '创建失败'}`)
    }
  }

  // Optionally persist user-overridable settings to backend config.
  if (successCount > 0) {
    const cfgUpdates: { key: string; value: string }[] = [
      { key: 'whisper_model', value: cfg.whisperModel },
      { key: 'tts_voice_simple', value: cfg.voice },
      { key: 'tts_speed', value: String(cfg.speed) },
      { key: 'tts_gain', value: String(cfg.volume) },
      { key: 'auto_publish_enabled', value: String(cfg.autoPublish) },
      { key: 'title_generator_enabled', value: String(cfg.aiTitle) },
    ]
    try {
      await configApi.updateMany({ configs: cfgUpdates })
    } catch {
      // Non-fatal: defaults still apply via backend
    }
  }

  submitting.value = false
  if (successCount > 0) {
    ElMessage.success(`成功创建 ${successCount} 个配音任务`)
    emit('created', createdIds)
    close()
  }
  if (failCount > 0) {
    ElMessage.error(`${failCount} 个任务创建失败：` + errors[0])
  }

  // Reset wizard for next time
  currentStep.value = 0
  urlText.value = ''
}

// Reset on open.
watch(visible, (v) => {
  if (v) {
    currentStep.value = 0
    urlText.value = ''
    keywordQuery.value = ''
    searchResults.value = []
    loadPlatformStates()
  }
})
</script>

<template>
  <el-dialog
    v-model="visible"
    title="新建配音任务"
    width="680px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <!-- Wizard header -->
    <el-steps :active="currentStep" finish-status="finish" align-center class="wizard-steps">
      <el-step title="粘贴 URL" />
      <el-step title="配音配置" />
      <el-step title="确认启动" />
    </el-steps>

    <!-- ─── Step 1: URL input + keyword search ─── -->
    <section v-if="currentStep === 0" class="step-body">
      <label class="step-label">粘贴 YouTube 视频 URL（每行一个，支持批量）</label>
      <el-input
        v-model="urlText"
        type="textarea"
        :rows="6"
        placeholder="https://www.youtube.com/watch?v=...
https://youtu.be/..."
        :disabled="submitting"
      />
      <div class="url-meta">
        <span>
          已识别 <strong class="num-mono">{{ parsedUrls.length }}</strong> 个 URL
        </span>
        <span v-if="invalidUrls.length > 0" class="is-danger-text">
          （{{ invalidUrls.length }} 个格式无效）
        </span>
      </div>

      <!-- Keyword search (R2: default expanded) -->
      <div class="search-block">
        <div class="search-header" @click="showKeywordSearch = !showKeywordSearch">
          <el-icon><ArrowDown v-if="showKeywordSearch" /><ArrowRight v-else /></el-icon>
          <span>没有现成 URL？用关键词搜索 YouTube</span>
        </div>
        <div v-if="showKeywordSearch" class="search-body">
          <div class="search-input-row">
            <el-input
              v-model="keywordQuery"
              placeholder="输入关键词，例如：AI 编程 教程"
              @keyup.enter="searchKeyword"
            />
            <el-button type="primary" :loading="searchLoading" @click="searchKeyword">搜索</el-button>
          </div>
          <div v-if="searchResults.length > 0" class="search-results">
            <div
              v-for="r in searchResults"
              :key="r.url"
              class="search-result-row"
            >
              <img v-if="r.thumbnail" :src="r.thumbnail" alt="" class="thumb" />
              <span class="sr-title" :title="r.title">{{ r.title }}</span>
              <el-button text type="primary" size="small" @click="addUrl(r.url)">+ 添加</el-button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── Step 2: Configuration ─── -->
    <section v-else-if="currentStep === 1" class="step-body">
      <p class="step-hint">配音配置（默认值已选好，可直接下一步）</p>

      <el-form label-position="top" class="cfg-form">
        <el-form-item label="音色">
          <el-select v-model="cfg.voice" style="width: 100%">
            <el-option v-for="v in voices" :key="v.value" :label="v.label" :value="v.value" />
          </el-select>
        </el-form-item>

        <el-form-item label="Whisper 转写模型">
          <el-select v-model="cfg.whisperModel" style="width: 100%">
            <el-option v-for="m in whisperModels" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </el-form-item>

        <el-form-item label="语速">
          <el-slider v-model="cfg.speed" :min="0.5" :max="2.0" :step="0.05" show-input />
        </el-form-item>

        <el-form-item>
          <div class="switch-row">
            <div>
              <div>配音完成后自动发布</div>
              <div class="text-caption">
                新手建议开启，省去手动点击发布。
                <span v-if="cfg.autoPublish && loggedInPlatforms.length === 0" class="is-warning-text">
                  （尚未登录任何平台，将无法发布）
                </span>
              </div>
            </div>
            <el-switch v-model="cfg.autoPublish" />
          </div>
        </el-form-item>

        <el-form-item>
          <div class="switch-row">
            <div>
              <div>启用 AI 标题自动生成</div>
              <div class="text-caption">配音完成后自动生成 5 个候选标题。</div>
            </div>
            <el-switch v-model="cfg.aiTitle" />
          </div>
        </el-form-item>

        <!-- Advanced (collapsed by default) -->
        <el-collapse v-model="cfg.showAdvanced" class="advanced-collapse">
          <el-collapse-item title="高级参数" name="adv">
            <el-form-item label="音量增益 (dB)">
              <el-slider v-model="cfg.volume" :min="-10" :max="10" :step="1" show-input />
            </el-form-item>
            <el-form-item label="翻译温度">
              <el-slider v-model="cfg.translationTemp" :min="0" :max="1" :step="0.1" show-input />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>
    </section>

    <!-- ─── Step 3: Confirm ─── -->
    <section v-else class="step-body">
      <p class="step-hint">确认信息</p>

      <div class="confirm-section">
        <div class="confirm-label">将创建 {{ parsedUrls.length }} 个配音任务：</div>
        <ul class="url-list">
          <li v-for="(u, i) in parsedUrls" :key="i">
            <span class="num-mono">{{ i + 1 }}.</span>
            <span class="url-text" :title="u">{{ u }}</span>
          </li>
        </ul>
      </div>

      <div class="confirm-section">
        <div class="confirm-label">配置摘要：</div>
        <dl class="confirm-grid">
          <dt>音色</dt><dd>{{ cfg.voice }}</dd>
          <dt>Whisper 模型</dt><dd>{{ cfg.whisperModel }}</dd>
          <dt>语速</dt><dd class="num-mono">{{ cfg.speed.toFixed(2) }}</dd>
          <dt>自动发布</dt>
          <dd>
            {{ cfg.autoPublish ? '是' : '否' }}
            <span v-if="cfg.autoPublish" class="text-caption">
              （{{ loggedInPlatforms.length > 0 ? loggedInPlatforms.join(' + ') : '未登录平台' }}）
            </span>
          </dd>
          <dt>AI 标题</dt><dd>{{ cfg.aiTitle ? '启用（5 候选）' : '禁用' }}</dd>
        </dl>
      </div>

      <p class="text-caption">预计耗时：每个视频约 3-5 分钟。</p>
    </section>

    <template #footer>
      <el-button v-if="currentStep > 0" @click="prev" :disabled="submitting">← 上一步</el-button>
      <el-button @click="close" :disabled="submitting">取消</el-button>
      <el-button
        v-if="currentStep < 2"
        type="primary"
        :disabled="!canNext()"
        @click="next"
      >下一步 →</el-button>
      <el-button
        v-else
        type="primary"
        :loading="submitting"
        @click="submit"
      >🚀 启动配音</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.wizard-steps {
  margin-bottom: var(--space-6);
}
.step-body {
  min-height: 320px;
}
.step-label {
  display: block;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}
.step-hint {
  margin: 0 0 var(--space-4);
  color: var(--color-text-regular);
}
.url-meta {
  margin-top: var(--space-2);
  font-size: var(--fs-xs);
  color: var(--color-text-muted);
}
.url-meta strong { color: var(--color-primary); }
.is-danger-text { color: var(--color-danger); margin-left: var(--space-2); }
.is-warning-text { color: var(--color-warning); }

.search-block {
  margin-top: var(--space-4);
  border-top: 1px dashed var(--color-border);
  padding-top: var(--space-3);
}
.search-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  font-size: var(--fs-sm);
  color: var(--color-text-regular);
  user-select: none;
}
.search-header:hover { color: var(--color-primary); }
.search-body { margin-top: var(--space-3); }
.search-input-row {
  display: flex;
  gap: var(--space-2);
}
.search-results {
  margin-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 200px;
  overflow-y: auto;
}
.search-result-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}
.search-result-row .thumb {
  width: 80px;
  height: 45px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: var(--color-bg-soft);
}
.sr-title {
  flex: 1;
  font-size: var(--fs-sm);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cfg-form .el-form-item { margin-bottom: var(--space-4); }
.switch-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  gap: var(--space-4);
}
.advanced-collapse {
  border-top: 1px solid var(--color-border);
  margin-top: var(--space-2);
}

.confirm-section {
  margin-bottom: var(--space-4);
  padding: var(--space-3);
  background: var(--color-bg-soft);
  border-radius: var(--radius-md);
}
.confirm-label {
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}
.url-list {
  margin: 0;
  padding-left: var(--space-4);
  font-size: var(--fs-sm);
  color: var(--color-text-regular);
  max-height: 140px;
  overflow-y: auto;
}
.url-list li {
  padding: var(--space-1) 0;
  display: flex;
  gap: var(--space-2);
}
.url-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.confirm-grid {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--fs-sm);
}
.confirm-grid dt { color: var(--color-text-muted); margin: 0; }
.confirm-grid dd { color: var(--color-text); margin: 0; }
</style>
