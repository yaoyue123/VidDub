import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { discoveryApi, dubApi } from '@/api'
import type {
  DiscoveryItem,
  DiscoverySourceItem,
  DiscoverySourceCreateBody,
  DiscoverySourceUpdateBody,
  DiscoveryResultItem,
} from '@/api'

export const useDiscoveryStore = defineStore('discovery', () => {
  // ── State ──
  const sources = ref<DiscoverySourceItem[]>([])
  const searchResults = ref<DiscoveryItem[]>([])
  const scanResults = ref<DiscoveryResultItem[]>([])
  const loading = ref(false)
  const searchLoading = ref(false)
  const activeTab = ref<'search' | 'keywords' | 'channels'>('search')
  const filters = reactive({
    minViews: null as number | null,
    maxViews: null as number | null,
    minDuration: null as number | null,
    maxDuration: null as number | null,
  })
  const searchQuery = ref('')
  const error = ref<string | null>(null)

  // ── Actions ──

  /** Search YouTube videos by keyword */
  async function search(query: string, maxResults = 20) {
    searchLoading.value = true
    error.value = null
    try {
      const res = await discoveryApi.search(query, maxResults)
      searchResults.value = res.data.items
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '搜索失败'
      error.value = msg
    } finally {
      searchLoading.value = false
    }
  }

  /** Fetch all discovery sources */
  async function fetchSources() {
    loading.value = true
    error.value = null
    try {
      const res = await discoveryApi.listSources()
      sources.value = res.data.items
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '获取来源列表失败'
      error.value = msg
    } finally {
      loading.value = false
    }
  }

  /** Create a new discovery source */
  async function addSource(body: DiscoverySourceCreateBody) {
    error.value = null
    try {
      await discoveryApi.createSource(body)
      await fetchSources()
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '添加来源失败'
      error.value = msg
      throw e
    }
  }

  /** Update an existing discovery source */
  async function updateSource(id: number, body: DiscoverySourceUpdateBody) {
    error.value = null
    try {
      await discoveryApi.updateSource(id, body)
      await fetchSources()
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '更新来源失败'
      error.value = msg
      throw e
    }
  }

  /** Remove a discovery source */
  async function removeSource(id: number) {
    error.value = null
    try {
      await discoveryApi.deleteSource(id)
      await fetchSources()
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '删除来源失败'
      error.value = msg
      throw e
    }
  }

  /** Trigger a scan on a discovery source */
  async function triggerScan(id: number) {
    error.value = null
    try {
      await discoveryApi.triggerScan(id)
      await fetchSources()
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '触发扫描失败'
      error.value = msg
      throw e
    }
  }

  /** Fetch discovery results with optional filters */
  async function fetchResults(params?: { source_id?: number; status?: string }) {
    loading.value = true
    error.value = null
    try {
      const res = await discoveryApi.listResults(params)
      scanResults.value = res.data.items
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '获取结果失败'
      error.value = msg
    } finally {
      loading.value = false
    }
  }

  /** Ignore a discovery result */
  async function ignoreResult(id: number) {
    error.value = null
    try {
      await discoveryApi.ignoreResult(id)
      await fetchResults()
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '忽略结果失败'
      error.value = msg
      throw e
    }
  }

  /** Add a video to the processing pipeline via dubApi */
  async function addToPipeline(youtubeUrl: string) {
    error.value = null
    try {
      const res = await dubApi.create({ youtube_url: youtubeUrl })
      return res.data
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '添加到流水线失败'
      error.value = msg
      throw e
    }
  }

  /** Clear all search state */
  function clearSearch() {
    searchResults.value = []
    searchQuery.value = ''
    error.value = null
  }

  /** Set the active tab */
  function setActiveTab(tab: 'search' | 'keywords' | 'channels') {
    activeTab.value = tab
  }

  return {
    // State
    sources,
    searchResults,
    scanResults,
    loading,
    searchLoading,
    activeTab,
    filters,
    searchQuery,
    error,
    // Actions
    search,
    fetchSources,
    addSource,
    updateSource,
    removeSource,
    triggerScan,
    fetchResults,
    ignoreResult,
    addToPipeline,
    clearSearch,
    setActiveTab,
  }
})
