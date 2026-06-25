<script setup lang="ts">
/**
 * Phase 12: MainLayout — 7→3 navigation (首页 / 任务 / 设置).
 * Spec: DESIGN.md §1.1, §3.1, §4.1.
 *
 * - Sidebar collapses to 64px; expands to 220px.
 * - Visual grouping: primary flow vs configuration.
 * - Header: WS connection badge + collapse toggle + breadcrumb.
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWsStore } from '@/stores/wsStore'

const route = useRoute()
const router = useRouter()
const wsStore = useWsStore()

const isCollapsed = ref(false)
const sidebarWidth = computed(() => (isCollapsed.value ? '64px' : '220px'))

interface MenuEntry {
  path: string
  icon: string
  title: string
}
interface MenuGroup {
  label: string
  items: MenuEntry[]
}

// Phase 12 §3.1: only 3 top-level entries, grouped.
const menuGroups: MenuGroup[] = [
  {
    label: '主流程',
    items: [
      { path: '/dashboard', icon: 'HomeFilled', title: '首页' },
      { path: '/tasks', icon: 'List', title: '任务' },
    ],
  },
  {
    label: '配置',
    items: [{ path: '/settings', icon: 'Setting', title: '设置' }],
  },
]

const activeMenu = computed(() => {
  // Map subtitle editor subroute to its parent (/tasks).
  if (route.path.startsWith('/tasks')) return '/tasks'
  if (route.path.startsWith('/dashboard')) return '/dashboard'
  if (route.path.startsWith('/settings')) return '/settings'
  return route.path
})
const pageTitle = computed(() => (route.meta?.title as string) || '')

// Connect WebSocket on layout mount (only once app-wide).
wsStore.connect()
</script>

<template>
  <el-container class="app-container">
    <!-- Sidebar -->
    <el-aside :width="sidebarWidth" class="app-sidebar">
      <div class="sidebar-header">
        <div class="logo">
          <el-icon :size="isCollapsed ? 24 : 28" color="#fff">
            <VideoCamera />
          </el-icon>
          <span v-show="!isCollapsed" class="logo-text">You2Bili</span>
        </div>
      </div>

      <nav class="sidebar-nav" v-for="group in menuGroups" :key="group.label">
        <div v-if="!isCollapsed" class="nav-group-label">{{ group.label }}</div>
        <el-menu
          :default-active="activeMenu"
          :collapse="isCollapsed"
          :collapse-transition="false"
          router
          class="sidebar-menu"
        >
          <el-menu-item
            v-for="item in group.items"
            :key="item.path"
            :index="item.path"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>{{ item.title }}</template>
          </el-menu-item>
        </el-menu>
      </nav>
    </el-aside>

    <!-- Main Content -->
    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <el-icon :size="20" class="collapse-btn" @click="isCollapsed = !isCollapsed">
            <Fold v-if="!isCollapsed" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="pageTitle">{{ pageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <span
            class="status-badge"
            :class="wsStore.connectionStatus === 'connected' ? 'is-success' : 'is-danger'"
          >
            <span class="dot" />
            {{ wsStore.connectionStatus === 'connected' ? '已连接' : '离线' }}
          </span>
        </div>
      </el-header>

      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-container {
  height: 100vh;
}

.app-sidebar {
  background-color: var(--color-sidebar-bg);
  transition: width 0.3s;
  overflow-x: hidden;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: 0 0 var(--space-4) 0;
}

.sidebar-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: var(--space-2);
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: #fff;
  font-size: var(--fs-lg);
  font-weight: 600;
}

.logo-text {
  white-space: nowrap;
  letter-spacing: 0.3px;
}

.sidebar-nav {
  padding: 0;
}

.nav-group-label {
  color: rgba(255, 255, 255, 0.45);
  font-size: var(--fs-xs);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  padding: var(--space-2) var(--space-4);
  font-weight: 500;
}

.sidebar-menu {
  background-color: transparent !important;
  border-right: none;
}

.sidebar-menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.78);
  height: 44px;
  line-height: 44px;
  margin: 2px var(--space-2);
  border-radius: var(--radius-md);
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background-color: rgba(255, 255, 255, 0.06);
  color: #fff;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background-color: var(--color-primary);
  color: #fff;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg);
  border-bottom: 1px solid var(--color-border);
  padding: 0 var(--space-6);
  height: 60px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.collapse-btn {
  cursor: pointer;
  color: var(--color-text-regular);
}

.collapse-btn:hover {
  color: var(--color-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.status-badge .dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: currentColor;
  display: inline-block;
}

.app-main {
  background-color: var(--color-bg-page);
  padding: var(--space-6);
  overflow-y: auto;
}
</style>
