import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

/**
 * Phase 12 router — DESIGN.md §3.1, §3.3.
 *
 * Primary nav: / (Dashboard) /tasks /settings.
 * Legacy routes (/videos, /channels, /platform, /publish) redirect to their new homes:
 *   - /channels → /tasks?tab=channels
 *   - /publish  → /tasks?tab=publish
 *   - /platform → /dashboard (Platform Login is now a Drawer triggered from Dashboard)
 *   - /videos   → /dashboard (collapsed into Dashboard's New Dub flow)
 *   - /videos/:id/subtitles → /tasks/:id/subtitles (kept under /tasks so subtitle editor
 *     remains accessible as a hidden subroute from task cards)
 */
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '首页', icon: 'HomeFilled' },
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('@/views/TasksView.vue'),
        meta: { title: '任务', icon: 'List' },
      },
      {
        path: 'tasks/:videoId/subtitles',
        name: 'SubtitleEditor',
        component: () => import('@/views/SubtitleEditorView.vue'),
        meta: { title: '字幕编辑', hidden: true },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/SettingsView.vue'),
        meta: { title: '设置', icon: 'Setting' },
      },

      // ── Backward-compatible redirects (DESIGN.md R12) ──
      { path: 'videos', redirect: '/dashboard' },
      { path: 'videos/:videoId/subtitles', redirect: (to) => `/tasks/${to.params.videoId}/subtitles` },
      { path: 'channels', redirect: '/tasks?tab=channels' },
      { path: 'platform', redirect: '/dashboard' },
      { path: 'publish', redirect: '/tasks?tab=publish' },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
