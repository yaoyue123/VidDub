<script setup lang="ts">
/**
 * Phase 8: AI 智能标题与标签选择器 (F2).
 *
 * 功能：
 *   - 弹窗展示 5 个候选标题（单选）
 *   - 8 个候选标签（多选）
 *   - 可编辑自定义标题输入框
 *   - "重新生成"按钮 → POST generate
 *   - "保存选择"按钮 → PUT update
 *
 * 父组件用法：
 *   <AiTitleSelector v-model:visible="show" :video-id="123"
 *                    @saved="(s) => { ... }" />
 */
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Check } from '@element-plus/icons-vue'
import { titleApi, type TitleSavedState } from '@/api'

const props = defineProps<{
  visible: boolean
  videoId: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', state: TitleSavedState): void
}>()

// ── 状态 ──
const loading = ref(false)
const generating = ref(false)
const candidates = ref<string[]>([])
const tagCandidates = ref<string[]>([])
const summaryZh = ref('')
const selectedTitle = ref<string>('')   // 当前选中的标题（可为用户自定义）
const customMode = ref(false)            // 是否切换到自定义输入
const customTitle = ref('')
const selectedTags = ref<string[]>([])

// ── 拉取已保存的候选 + 用户选择 ──
async function loadSaved() {
  if (!props.videoId) return
  loading.value = true
  try {
    const res = await titleApi.get(props.videoId)
    candidates.value = res.data.ai_title_candidates || []
    tagCandidates.value = res.data.ai_tags_candidates || []
    summaryZh.value = res.data.summary_zh || ''
    if (res.data.title_chosen) {
      // 已有选择：判断是候选之一还是自定义
      const idx = candidates.value.indexOf(res.data.title_chosen)
      if (idx >= 0) {
        selectedTitle.value = res.data.title_chosen
        customMode.value = false
      } else {
        customMode.value = true
        customTitle.value = res.data.title_chosen
        selectedTitle.value = res.data.title_chosen
      }
    } else if (candidates.value.length > 0) {
      selectedTitle.value = candidates.value[0]
    }
    selectedTags.value = res.data.tags_chosen || []
  } catch (e: any) {
    ElMessage.error('加载候选失败：' + (e?.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// ── 重新生成 ──
async function regenerate() {
  if (!props.videoId) return
  generating.value = true
  try {
    const res = await titleApi.generate(props.videoId)
    candidates.value = res.data.titles || []
    tagCandidates.value = res.data.tags || []
    summaryZh.value = res.data.summary_zh || ''
    if (candidates.value.length > 0) {
      selectedTitle.value = candidates.value[0]
      customMode.value = false
    }
    ElMessage.success(`已生成 ${candidates.value.length} 个标题 + ${tagCandidates.value.length} 个标签`)
  } catch (e: any) {
    ElMessage.error('生成失败：' + (e?.response?.data?.detail || e?.message || '请稍后重试'))
  } finally {
    generating.value = false
  }
}

// ── 选择标题（候选 radio 切换）──
function pickCandidate(t: string) {
  customMode.value = false
  selectedTitle.value = t
}

function enableCustom() {
  customMode.value = true
  if (!customTitle.value && selectedTitle.value) {
    customTitle.value = selectedTitle.value
  }
  selectedTitle.value = customTitle.value
}

function onCustomInput(v: string) {
  customTitle.value = v
  selectedTitle.value = v
}

// ── 标签多选 toggle ──
function toggleTag(t: string) {
  const i = selectedTags.value.indexOf(t)
  if (i >= 0) {
    selectedTags.value.splice(i, 1)
  } else {
    selectedTags.value.push(t)
  }
}

// ── 保存 ──
async function save() {
  if (!selectedTitle.value || !selectedTitle.value.trim()) {
    ElMessage.warning('请先选择或输入标题')
    return
  }
  loading.value = true
  try {
    const res = await titleApi.update(props.videoId, {
      title_chosen: selectedTitle.value.trim(),
      tags_chosen: selectedTags.value,
    })
    ElMessage.success('已保存选择')
    emit('saved', res.data)
    emit('update:visible', false)
  } catch (e: any) {
    ElMessage.error('保存失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function close() {
  emit('update:visible', false)
}

// ── visible / videoId 变化时拉数据 ──
watch(
  () => [props.visible, props.videoId],
  ([v, _id]) => {
    if (v && props.videoId) {
      loadSaved()
    }
  },
  { immediate: true },
)

// dialog visible 双向绑定代理
const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="AI 标题与标签选择"
    width="680px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-loading="loading || generating" class="ai-title-selector">
      <!-- 候选标题 -->
      <section class="block">
        <header class="block-header">
          <h3>候选标题</h3>
          <el-button size="small" :icon="Refresh" :loading="generating" @click="regenerate">
            重新生成
          </el-button>
        </header>

        <el-radio-group
          v-if="candidates.length > 0"
          :model-value="customMode ? '' : selectedTitle"
          @update:model-value="(v: any) => pickCandidate(String(v))"
          class="title-radio-group"
        >
          <el-radio
            v-for="(t, idx) in candidates"
            :key="idx"
            :value="t"
            class="title-radio"
          >
            {{ t }}
          </el-radio>
        </el-radio-group>

        <el-empty
          v-else
          description="暂无候选，点击右上角「重新生成」"
          :image-size="80"
        />

        <!-- 自定义标题 -->
        <div class="custom-row">
          <el-radio
            :model-value="customMode ? 'custom' : ''"
            value="custom"
            @update:model-value="() => enableCustom()"
          >
            自定义标题
          </el-radio>
          <el-input
            v-if="customMode"
            :model-value="customTitle"
            placeholder="输入自定义标题（不超过 80 字）"
            maxlength="80"
            show-word-limit
            @update:model-value="(v: string) => onCustomInput(v)"
          />
        </div>
      </section>

      <!-- 候选标签 -->
      <section class="block">
        <header class="block-header">
          <h3>候选标签（已选 {{ selectedTags.length }}）</h3>
        </header>
        <div v-if="tagCandidates.length > 0" class="tag-list">
          <el-tag
            v-for="t in tagCandidates"
            :key="t"
            :type="selectedTags.includes(t) ? 'primary' : 'info'"
            :effect="selectedTags.includes(t) ? 'dark' : 'plain'"
            class="tag-chip"
            @click="toggleTag(t)"
          >
            {{ t }}
          </el-tag>
        </div>
        <el-empty v-else description="暂无标签候选" :image-size="60" />
      </section>

      <!-- 摘要（只读展示） -->
      <section v-if="summaryZh" class="block">
        <header class="block-header">
          <h3>内容摘要</h3>
        </header>
        <p class="summary-text">{{ summaryZh }}</p>
      </section>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="close">取消</el-button>
        <el-button type="primary" :icon="Check" :loading="loading" @click="save">
          保存选择
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<style scoped>
.ai-title-selector {
  padding: 0 8px;
}
.block {
  margin-bottom: 24px;
}
.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.block-header h3 {
  margin: 0;
  font-size: 14px;
  color: #303133;
  font-weight: 600;
}
.title-radio-group {
  display: flex;
  flex-direction: column;
  width: 100%;
}
.title-radio {
  margin: 0 0 8px 0;
  padding: 8px 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  transition: border-color 0.2s;
  white-space: normal;
  line-height: 1.4;
}
.title-radio:hover {
  border-color: #409eff;
}
.title-radio.is-checked {
  border-color: #409eff;
  background-color: #ecf5ff;
}
.custom-row {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 12px;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tag-chip {
  cursor: pointer;
  user-select: none;
}
.summary-text {
  margin: 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
  background-color: #f5f7fa;
  padding: 10px 12px;
  border-radius: 4px;
}
</style>
