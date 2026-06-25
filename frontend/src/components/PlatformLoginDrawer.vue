<script setup lang="ts">
/**
 * Phase 12: PlatformLoginDrawer — extracted from PlatformLoginView.
 * Spec: DESIGN.md §1.6, §5.5.
 *
 * Triggered from Dashboard's "平台账号" card or Settings.
 * Preserves WS subscription (#86101 fix) and QR scan flow.
 */
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import {
  platformApi,
  type PlatformName,
  type PlatformStateItem,
} from '@/api'
import { useWsStore } from '@/stores/wsStore'

type LoginStage =
  | 'idle'
  | 'loading_qr'
  | 'waiting_scan'
  | 'scanned'
  | 'success'
  | 'expired'
  | 'failed'
  | 'timeout'

interface PlatformPanelState {
  platform: PlatformName
  displayName: string
  logoColor: string
  logoText: string
  logged_in: boolean
  expired: boolean
  user_info: Record<string, unknown> | null
  stage: LoginStage
  qr_image_base64: string | null
  expires_at: number | null
  message: string | null
}

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v) => emit('update:visible', v),
})

const wsStore = useWsStore()

const panels = ref<Record<PlatformName, PlatformPanelState>>({
  bilibili: {
    platform: 'bilibili', displayName: '哔哩哔哩', logoColor: '#fb7299', logoText: 'B',
    logged_in: false, expired: false, user_info: null, stage: 'idle',
    qr_image_base64: null, expires_at: null, message: null,
  },
  ixigua: {
    platform: 'ixigua', displayName: '西瓜视频', logoColor: '#ff5c5c', logoText: '西',
    logged_in: false, expired: false, user_info: null, stage: 'idle',
    qr_image_base64: null, expires_at: null, message: null,
  },
})

const loadingState = ref(false)
const panelList = computed(() => Object.values(panels.value))

function statusTagType(p: PlatformPanelState): 'success' | 'info' | 'warning' | 'danger' {
  if (p.stage === 'success' || (p.logged_in && !p.expired && p.stage === 'idle')) return 'success'
  if (p.expired) return 'danger'
  if (p.stage === 'loading_qr' || p.stage === 'waiting_scan' || p.stage === 'scanned') return 'warning'
  return 'info'
}

function statusLabel(p: PlatformPanelState): string {
  if (p.stage === 'success') return '登录成功'
  if (p.stage === 'loading_qr') return '正在加载二维码...'
  if (p.stage === 'waiting_scan') return '等待扫码'
  if (p.stage === 'scanned') return '已扫码，等待确认'
  if (p.stage === 'expired') return '二维码已过期'
  if (p.stage === 'timeout') return '登录超时'
  if (p.stage === 'failed') return '登录失败'
  if (p.expired) return '登录态过期'
  if (p.logged_in) return '已登录'
  return '未登录'
}

function qrDataUrl(p: PlatformPanelState): string | null {
  if (!p.qr_image_base64) return null
  return `data:image/png;base64,${p.qr_image_base64}`
}

function userDisplay(p: PlatformPanelState): string {
  if (!p.user_info) return '-'
  const uname = p.user_info.username || p.user_info.uname || p.user_info.name
  const uid = p.user_info.uid || p.user_info.user_id || p.user_info.mid
  if (uname && uid) return `${uname} (UID: ${uid})`
  if (uname) return String(uname)
  if (uid) return `UID: ${uid}`
  return '已登录'
}

async function loadAllState() {
  loadingState.value = true
  try {
    const res = await platformApi.allState()
    for (const item of res.data.platforms as PlatformStateItem[]) {
      const p = panels.value[item.platform as PlatformName]
      if (!p) continue
      p.logged_in = item.logged_in
      p.user_info = item.user_info ?? null
      p.expired = false
      if (p.stage === 'success') p.stage = 'idle'
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载平台登录态失败')
  } finally {
    loadingState.value = false
  }
}

async function startLogin(p: PlatformPanelState) {
  p.stage = 'loading_qr'
  p.qr_image_base64 = null
  p.expires_at = null
  p.message = null
  try {
    const res = await platformApi.start(p.platform)
    p.qr_image_base64 = res.data.qr_image_base64
    p.expires_at = res.data.expires_at
    p.stage = 'waiting_scan'
  } catch (e: any) {
    p.stage = 'failed'
    const detail = e?.response?.data?.detail || e?.message || '启动登录失败'
    p.message = detail
    ElMessage.error(`${p.displayName}：${detail}`)
  }
}

async function checkLogin(p: PlatformPanelState) {
  try {
    const res = await platformApi.check(p.platform)
    p.logged_in = res.data.logged_in
    p.expired = res.data.expired
    p.user_info = res.data.user_info ?? p.user_info
    if (res.data.expired) {
      ElMessage.warning(`${p.displayName}：登录态已过期，请重新登录`)
    } else if (res.data.logged_in) {
      ElMessage.success(`${p.displayName}：登录态正常`)
    } else {
      ElMessage.info(`${p.displayName}：未登录`)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '检测失败')
  }
}

async function logout(p: PlatformPanelState) {
  try {
    await platformApi.logout(p.platform)
    p.logged_in = false
    p.user_info = null
    p.expired = false
    p.stage = 'idle'
    p.qr_image_base64 = null
    ElMessage.success(`${p.displayName}：已退出登录`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '登出失败')
  }
}

function resetStage(p: PlatformPanelState) {
  p.stage = 'idle'
  p.qr_image_base64 = null
  p.expires_at = null
  p.message = null
}

// ── WebSocket (preserved from PlatformLoginView) ──
let unsubWs: (() => void) | null = null
let lastProcessedMsgIdx = -1
let watchTimer: ReturnType<typeof setInterval> | null = null

function handleWsMessage(msg: any) {
  const t = msg?.type
  const data = msg?.data
  if (!data) return
  const platform = data.platform as PlatformName | undefined
  if (!platform) return
  const p = panels.value[platform]
  if (!p) return

  if (t === 'platform_qr_update') {
    if (p.stage === 'waiting_scan' || p.stage === 'loading_qr') {
      p.qr_image_base64 = data.qr_image_base64
      p.expires_at = data.expires_at
    }
  } else if (t === 'platform_login_status') {
    const status = data.status
    if (status === 'waiting') p.stage = 'waiting_scan'
    else if (status === 'scanned') p.stage = 'scanned'
    else if (status === 'success') {
      p.stage = 'success'
      p.logged_in = true
      p.expired = false
      p.user_info = data.user_info ?? p.user_info
      ElMessage.success(`${p.displayName}：登录成功`)
      setTimeout(() => { if (p.stage === 'success') p.stage = 'idle' }, 5000)
    } else if (status === 'expired') p.stage = 'expired'
    else if (status === 'timeout') p.stage = 'timeout'
    else if (status === 'failed') { p.stage = 'failed'; p.message = data.message }
    else if (status === 'logged_out') {
      p.logged_in = false
      p.user_info = null
      p.stage = 'idle'
    }
  } else if (t === 'platform_login_expired') {
    p.expired = true
    p.logged_in = false
    ElMessage.warning(`${p.displayName}：检测到登录态过期`)
  }
}

function watchMessages() {
  const msgs = wsStore.messages
  if (msgs.length > lastProcessedMsgIdx + 1) {
    for (let i = lastProcessedMsgIdx + 1; i < msgs.length; i++) {
      handleWsMessage(msgs[i])
    }
    lastProcessedMsgIdx = msgs.length - 1
  }
}

function attachWs() {
  if (unsubWs === null) {
    unsubWs = wsStore.subscribe(handleWsMessage)
  }
  if (watchTimer === null) {
    watchTimer = setInterval(watchMessages, 300)
  }
}

function detachWs() {
  if (unsubWs) { unsubWs(); unsubWs = null }
  if (watchTimer) { clearInterval(watchTimer); watchTimer = null }
  lastProcessedMsgIdx = -1
}

// On open: load + attach WS. On close: detach WS (but keep state for reopen).
watch(() => props.visible, (v) => {
  if (v) {
    loadAllState()
    attachWs()
  } else {
    detachWs()
  }
}, { immediate: true })

onBeforeUnmount(detachWs)

defineExpose({ loadAllState })
</script>

<template>
  <el-drawer
    v-model="dialogVisible"
    title="平台账号管理"
    direction="rtl"
    size="420px"
    :close-on-click-modal="false"
  >
    <div class="drawer-intro">
      扫码登录后，配音完成的视频可自动发布到对应平台。
    </div>

    <div class="panel-list">
      <div v-for="p in panelList" :key="p.platform" class="platform-card y2b-card y2b-card-pad">
        <!-- Header -->
        <div class="card-header">
          <div class="logo-circle" :style="{ backgroundColor: p.logoColor }">{{ p.logoText }}</div>
          <div class="header-info">
            <div class="display-name">{{ p.displayName }}</div>
            <span class="status-badge" :class="`is-${statusTagType(p)}`">
              {{ statusLabel(p) }}
            </span>
          </div>
        </div>

        <!-- 已登录 -->
        <div v-if="p.logged_in && p.stage === 'idle'" class="logged-in-block">
          <dl class="user-info">
            <div class="ui-row">
              <dt>账号</dt>
              <dd>{{ userDisplay(p) }}</dd>
            </div>
            <div v-if="p.user_info?.level" class="ui-row">
              <dt>等级</dt>
              <dd>{{ p.user_info.level }}</dd>
            </div>
          </dl>
          <div class="action-row">
            <el-button size="small" @click="checkLogin(p)">检测登录态</el-button>
            <el-button size="small" type="danger" plain @click="logout(p)">退出</el-button>
          </div>
        </div>

        <!-- 登录中 -->
        <div
          v-else-if="['loading_qr','waiting_scan','scanned','success','expired','timeout','failed'].includes(p.stage)"
          class="qr-block"
        >
          <div v-if="p.stage === 'loading_qr'" class="qr-placeholder">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span class="text-caption">正在加载二维码...</span>
          </div>

          <div v-else-if="qrDataUrl(p)" class="qr-image-wrap">
            <img :src="qrDataUrl(p)!" alt="QR Code" class="qr-image" />
            <div class="qr-hint">
              <span v-if="p.stage === 'waiting_scan'">请使用 {{ p.displayName }} App 扫码</span>
              <span v-else-if="p.stage === 'scanned'" class="is-success-text">已扫描，请在手机上确认</span>
              <span v-else-if="p.stage === 'success'" class="is-success-text">登录成功！</span>
              <span v-else-if="p.stage === 'expired'" class="is-danger-text">二维码已过期</span>
              <span v-else-if="p.stage === 'timeout'" class="is-danger-text">登录超时，请重试</span>
              <span v-else-if="p.stage === 'failed'" class="is-danger-text">{{ p.message || '登录失败' }}</span>
            </div>
          </div>

          <div class="action-row">
            <el-button
              v-if="['expired', 'timeout', 'failed'].includes(p.stage)"
              size="small"
              type="primary"
              @click="startLogin(p)"
            >重新登录</el-button>
            <el-button size="small" @click="resetStage(p)">取消</el-button>
          </div>
        </div>

        <!-- 未登录 -->
        <div v-else class="not-logged-block">
          <p class="text-caption" style="margin: 0 0 var(--space-3) 0;">
            尚未登录。点击下方按钮启动扫码流程。
          </p>
          <div class="action-row">
            <el-button type="primary" @click="startLogin(p)">扫码登录</el-button>
            <el-button size="small" @click="checkLogin(p)">检测登录态</el-button>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button :loading="loadingState" @click="loadAllState">刷新状态</el-button>
      <el-button @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.drawer-intro {
  color: var(--color-text-regular);
  font-size: var(--fs-sm);
  margin-bottom: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-soft);
  border-radius: var(--radius-md);
}
.panel-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.platform-card { padding: var(--space-4); }
.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.logo-circle {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  color: #fff;
  font-size: var(--fs-sm);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.header-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.display-name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--color-text);
}
.action-row {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.qr-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: var(--space-3);
  color: var(--color-text-muted);
}
.qr-image-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}
.qr-image {
  width: 200px;
  height: 200px;
  image-rendering: pixelated;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.qr-hint {
  font-size: var(--fs-xs);
  color: var(--color-text-regular);
  text-align: center;
}
.is-success-text { color: var(--color-success); }
.is-danger-text { color: var(--color-danger); }
.user-info {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.ui-row {
  display: flex;
  gap: var(--space-2);
  font-size: var(--fs-sm);
}
.ui-row dt {
  color: var(--color-text-muted);
  min-width: 48px;
  margin: 0;
}
.ui-row dd {
  color: var(--color-text);
  margin: 0;
  flex: 1;
  word-break: break-all;
}
</style>
