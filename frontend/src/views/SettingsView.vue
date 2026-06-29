<script setup lang="ts">
/**
 * Phase 12 SettingsView — DESIGN.md §1.7, §3.2.
 *
 * 8 tabs → 3 vertical sections:
 *   1. API 配置 (SiliconFlow API Key + 测试 + 模型)
 *   2. 配音参数 (Whisper / TTS / Translate)
 *   3. 高级 (atempo + 自动发布 + AI 标题 + 调度)
 *
 * Platform management moved to Dashboard drawer (no longer a Settings section).
 * Top search bar filters fields.
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { configApi, type ConfigItem } from '@/api'
import PlatformLoginDrawer from '@/components/PlatformLoginDrawer.vue'

interface FieldDef {
  key: string
  label: string
  type: 'input' | 'password' | 'number' | 'select'
  placeholder?: string
  options?: { label: string; value: string }[]
  min?: number
  max?: number
  step?: number
  help?: string
  group: 'api' | 'dub' | 'advanced'
}

const loading = ref(false)
const testing = ref(false)
const testResult = ref<{ ok: boolean; latency_ms: number; error: string | null } | null>(null)
const configs = ref<Record<string, string>>({})
const searchQuery = ref('')
const platformDrawerVisible = ref(false)

const fields: FieldDef[] = [
  // ─── API 配置 ───
  {
    key: 'siliconflow_api_key', label: 'SiliconFlow API Key', type: 'password',
    placeholder: 'sk-xxxxxxxxxxxxxxxx',
    help: '从 https://cloud.siliconflow.cn/account/ak 获取',
    group: 'api',
  },
  {
    key: 'translation_model', label: '翻译模型', type: 'select',
    options: [
      { label: 'Qwen2.5-7B-Instruct (推荐)', value: 'Qwen/Qwen2.5-7B-Instruct' },
      { label: 'Qwen2.5-14B-Instruct', value: 'Qwen/Qwen2.5-14B-Instruct' },
    ],
    group: 'api',
  },

  // ─── 配音参数 ───
  {
    key: 'whisper_model', label: 'Whisper 模型', type: 'select',
    options: [
      { label: 'tiny (最快)', value: 'tiny' },
      { label: 'base (推荐)', value: 'base' },
      { label: 'small', value: 'small' },
      { label: 'medium (很慢)', value: 'medium' },
    ],
    help: '本地 STT 模型大小。视频较长建议 tiny 或 base。',
    group: 'dub',
  },
  {
    key: 'whisper_language', label: '源语言', type: 'select',
    options: [
      { label: '英语', value: 'en' },
      { label: '日语', value: 'ja' },
      { label: '韩语', value: 'ko' },
      { label: '自动检测', value: 'auto' },
    ],
    group: 'dub',
  },
  {
    key: 'tts_voice_simple', label: '默认音色', type: 'select',
    options: [
      { label: 'alex (男声)', value: 'alex' },
      { label: 'benjamin (男声)', value: 'benjamin' },
      { label: 'charles (男声)', value: 'charles' },
      { label: 'david (男声)', value: 'david' },
      { label: 'anna (女声)', value: 'anna' },
      { label: 'bella (女声)', value: 'bella' },
      { label: 'claire (女声)', value: 'claire' },
      { label: 'diana (女声)', value: 'diana' },
    ],
    help: '音色自动拼 model:voice 前缀',
    group: 'dub',
  },
  {
    key: 'tts_speed', label: '语速', type: 'number',
    placeholder: '1.0', min: 0.25, max: 4.0, step: 0.05,
    help: '0.25 (慢) - 4.0 (快)，默认 1.0',
    group: 'dub',
  },
  {
    key: 'tts_gain', label: '音量增益 (dB)', type: 'number',
    placeholder: '0', min: -10, max: 10, step: 1,
    help: '-10 (轻) 到 10 (响)，默认 0',
    group: 'dub',
  },
  {
    key: 'translation_context_window', label: '滑窗上下文段数', type: 'number',
    min: 0, max: 10, step: 1, placeholder: '2',
    help: '逐段翻译时携带的前 N 段作为 few-shot 示例',
    group: 'dub',
  },

  // ─── 高级 ───
  {
    key: 'background_separation_enabled', label: '背景音分离', type: 'select',
    options: [
      { label: '开启 (demucs 分离人声/背景)', value: 'true' },
      { label: '关闭 (不分离)', value: 'false' },
    ],
    help: '开启后使用 demucs 分离人声与背景音，转录更准、合成时保留原 BGM',
    group: 'advanced',
  },
  {
    key: 'background_volume', label: '背景音量比例', type: 'number',
    min: 0.0, max: 1.0, step: 0.05, placeholder: '0.3',
    help: '合成时背景音轨的音量比（0=静音，1=原始音量）',
    group: 'advanced',
  },
  {
    key: 'voice_clone_enabled', label: '自动音色克隆', type: 'select',
    options: [
      { label: '开启 (从原视频克隆说话人音色)', value: 'true' },
      { label: '关闭 (使用默认/自动选择的音色)', value: 'false' },
    ],
    help: '开启后截取原视频人声片段上传 SiliconFlow 克隆音色，配音更自然',
    group: 'advanced',
  },
  {
    key: 'auto_voice_selection_enabled', label: '自动音色选择', type: 'select',
    options: [
      { label: '开启 (pitch 分析自动匹配男女声)', value: 'true' },
      { label: '关闭 (使用指定默认音色)', value: 'false' },
    ],
    help: '音色克隆失败时，自动分析原声 pitch 选择匹配的男女声',
    group: 'advanced',
  },
  {
    key: 'atempo_min', label: 'atempo 下限', type: 'number',
    min: 0.5, max: 2.0, step: 0.05, placeholder: '0.7',
    help: 'TTS 时长超出原时长 ×（1/atempo_min）时改为补静音',
    group: 'advanced',
  },
  {
    key: 'atempo_max', label: 'atempo 上限', type: 'number',
    min: 0.5, max: 2.0, step: 0.05, placeholder: '1.5',
    help: 'TTS 时长不足原时长 ×（1/atempo_max）时改为截断',
    group: 'advanced',
  },
  {
    key: 'download_dir', label: '下载目录', type: 'input',
    placeholder: './downloads',
    help: '视频/音频/字幕文件存储目录（相对于 backend/）',
    group: 'advanced',
  },
  {
    key: 'max_concurrent_downloads', label: '最大并发任务', type: 'number',
    min: 1, max: 10, step: 1, placeholder: '3',
    group: 'advanced',
  },
  {
    key: 'auto_publish_enabled', label: '自动发布', type: 'select',
    options: [
      { label: '开启 (配音完成自动发布)', value: 'true' },
      { label: '关闭 (手动点发布)', value: 'false' },
    ],
    help: '关闭后，配音完成的视频停留在 completed 状态，需手动点「发布」按钮',
    group: 'advanced',
  },
  {
    key: 'bilibili_default_category', label: '哔哩哔哩分区 tid', type: 'select',
    options: [
      { label: '122 - 野生技术协会', value: '122' },
      { label: '95 - 数码', value: '95' },
      { label: '207 - 科技·科普', value: '207' },
      { label: '36 - 知识·科技科普·计算机', value: '36' },
      { label: '21 - 日常', value: '21' },
    ],
    group: 'advanced',
  },
  {
    key: 'publish_default_tags', label: '默认标签', type: 'input',
    placeholder: '搬运,英语学习,翻译',
    help: '逗号分隔，最多 10 个，发布时与 AI 翻译标签合并',
    group: 'advanced',
  },
  {
    key: 'publish_upload_timeout_sec', label: '上传超时秒数', type: 'number',
    min: 60, max: 1800, step: 30, placeholder: '600',
    help: '视频上传 + 处理最长等待秒数（默认 600=10 分钟）',
    group: 'advanced',
  },
  {
    key: 'title_generator_enabled', label: '启用 AI 标题自动生成', type: 'select',
    options: [
      { label: '启用 (配音完成后自动生成候选)', value: 'true' },
      { label: '禁用 (仅手动点 AI 标题触发)', value: 'false' },
    ],
    help: '关闭后，配音完成时不再自动调 SiliconFlow 生成标题候选',
    group: 'advanced',
  },
  {
    key: 'title_generator_candidate_count', label: '候选标题数', type: 'number',
    min: 1, max: 10, step: 1, placeholder: '5',
    group: 'advanced',
  },
  {
    key: 'title_generator_tag_count', label: '候选标签数', type: 'number',
    min: 1, max: 10, step: 1, placeholder: '8',
    group: 'advanced',
  },
]

const sections = computed(() => [
  {
    key: 'api',
    title: 'API 配置',
    description: 'SiliconFlow API Key 是必需的，用于云端 STT / TTS / 翻译。',
    fields: fields.filter((f) => f.group === 'api' && matchSearch(f)),
  },
  {
    key: 'dub',
    title: '配音参数',
    description: 'Whisper 转写模型、TTS 音色语速、翻译上下文。',
    fields: fields.filter((f) => f.group === 'dub' && matchSearch(f)),
  },
  {
    key: 'advanced',
    title: '高级',
    description: 'atempo 边界、自动发布策略、AI 标题、调度参数。',
    fields: fields.filter((f) => f.group === 'advanced' && matchSearch(f)),
  },
])

function matchSearch(f: FieldDef): boolean {
  if (!searchQuery.value.trim()) return true
  const q = searchQuery.value.toLowerCase()
  return (
    f.label.toLowerCase().includes(q) ||
    f.key.toLowerCase().includes(q) ||
    (f.help || '').toLowerCase().includes(q)
  )
}

async function loadConfigs() {
  loading.value = true
  try {
    const res = await configApi.list()
    const map: Record<string, string> = {}
    ;(res.data as ConfigItem[]).forEach((item: ConfigItem) => {
      map[item.key] = item.value
    })
    configs.value = map
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载配置失败')
  } finally {
    loading.value = false
  }
}

async function saveField(field: FieldDef) {
  const value = configs.value[field.key] ?? ''
  try {
    await configApi.updateOne(field.key, String(value))
    ElMessage.success(`${field.label} 已保存`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || `${field.label} 保存失败`)
  }
}

async function saveAll() {
  try {
    const items = Object.entries(configs.value).map(([key, value]) => ({ key, value: String(value) }))
    await configApi.updateMany({ configs: items })
    ElMessage.success('全部设置已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  }
}

async function testSiliconFlow() {
  testing.value = true
  testResult.value = null
  try {
    const newKey = configs.value['siliconflow_api_key']
    if (newKey) {
      try {
        await configApi.updateOne('siliconflow_api_key', String(newKey))
      } catch {}
    }
    const res = await configApi.testSiliconFlow()
    testResult.value = res.data
    if (res.data.ok) {
      ElMessage.success(`API Key 有效 (延迟 ${res.data.latency_ms}ms)`)
    } else {
      ElMessage.error(res.data.error || '测试失败')
    }
  } catch (e: any) {
    testResult.value = {
      ok: false, latency_ms: 0,
      error: e?.response?.data?.detail || e?.message || '请求失败',
    }
    ElMessage.error('测试请求失败')
  } finally {
    testing.value = false
  }
}

onMounted(() => loadConfigs())
</script>

<template>
  <div class="settings-view">
    <div class="page-header">
      <h1 class="page-title">设置</h1>
      <el-button type="primary" @click="saveAll">保存全部</el-button>
    </div>

    <div class="search-bar y2b-card y2b-card-pad">
      <el-input
        v-model="searchQuery"
        :prefix-icon="Search"
        placeholder="搜索设置项..."
        clearable
      />
      <el-button text @click="platformDrawerVisible = true">管理平台账号 →</el-button>
    </div>

    <div v-loading="loading" class="sections">
      <section
        v-for="s in sections"
        :key="s.key"
        class="settings-section y2b-card y2b-card-pad-lg"
        v-show="s.fields.length > 0"
      >
        <header class="section-header">
          <div>
            <h2 class="section-title">{{ s.title }}</h2>
            <p class="section-desc text-caption">{{ s.description }}</p>
          </div>
        </header>

        <el-form label-position="top" class="settings-form">
          <el-form-item v-for="field in s.fields" :key="field.key" :label="field.label">
            <div class="field-row">
              <!-- API key field gets test button -->
              <el-input
                v-if="field.type === 'password'"
                v-model="configs[field.key]"
                type="password"
                show-password
                :placeholder="field.placeholder"
                style="flex: 1; max-width: 480px;"
                @blur="saveField(field)"
              />
              <el-select
                v-else-if="field.type === 'select'"
                v-model="configs[field.key]"
                :placeholder="field.placeholder"
                style="flex: 1; max-width: 480px;"
                @change="saveField(field)"
              >
                <el-option
                  v-for="opt in field.options"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-input-number
                v-else-if="field.type === 'number'"
                v-model="configs[field.key]"
                :placeholder="field.placeholder"
                :min="field.min"
                :max="field.max"
                :step="field.step"
                style="flex: 1; max-width: 240px;"
                @change="saveField(field)"
              />
              <el-input
                v-else
                v-model="configs[field.key]"
                :placeholder="field.placeholder"
                style="flex: 1; max-width: 480px;"
                @blur="saveField(field)"
              />

              <el-button
                v-if="field.key === 'siliconflow_api_key'"
                type="primary"
                :loading="testing"
                @click="testSiliconFlow"
              >测试连通</el-button>
              <el-button v-else text type="primary" size="small" @click="saveField(field)">保存</el-button>
            </div>
            <div v-if="field.help" class="field-help">{{ field.help }}</div>
          </el-form-item>
        </el-form>

        <!-- Test result inline under API key -->
        <el-alert
          v-if="s.key === 'api' && testResult"
          :type="testResult.ok ? 'success' : 'error'"
          :closable="false"
          show-icon
          style="margin-top: var(--space-3);"
        >
          <template #title>
            <span v-if="testResult.ok">✓ 连通正常 · 延迟 {{ testResult.latency_ms }} ms</span>
            <span v-else>✗ {{ testResult.error }}</span>
          </template>
        </el-alert>
      </section>
    </div>

    <PlatformLoginDrawer v-model:visible="platformDrawerVisible" />
  </div>
</template>

<style scoped>
.settings-view {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.page-title {
  font-size: var(--fs-2xl);
  font-weight: 600;
  margin: 0;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.search-bar .el-input { flex: 1; }

.sections { display: flex; flex-direction: column; gap: var(--space-6); }

.settings-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.section-header { margin-bottom: var(--space-3); }
.section-title {
  font-size: var(--fs-lg);
  font-weight: 600;
  margin: 0 0 var(--space-1) 0;
  color: var(--color-text);
}
.section-desc { margin: 0; }

.settings-form .el-form-item {
  margin-bottom: var(--space-4);
}
.field-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
}
.field-help {
  font-size: var(--fs-xs);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}
</style>
