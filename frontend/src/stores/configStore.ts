import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

interface ConfigItem {
  id: number
  key: string
  value: string
  description: string | null
}

export const useConfigStore = defineStore('config', () => {
  const configs = ref<Record<string, string>>({})
  const loading = ref(false)

  async function fetchConfig() {
    loading.value = true
    try {
      const res = await api.get<ConfigItem[]>('/config')
      const map: Record<string, string> = {}
      res.data.forEach((item: ConfigItem) => {
        map[item.key] = item.value
      })
      configs.value = map
    } catch (e) {
      console.error('Failed to fetch config:', e)
    } finally {
      loading.value = false
    }
  }

  async function updateConfig(updates: Record<string, string>) {
    try {
      const items = Object.entries(updates).map(([key, value]) => ({ key, value }))
      await api.put('/config', { configs: items })
      Object.assign(configs.value, updates)
    } catch (e) {
      console.error('Failed to update config:', e)
      throw e
    }
  }

  return { configs, loading, fetchConfig, updateConfig }
})
