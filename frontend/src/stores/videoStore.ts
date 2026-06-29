import { defineStore } from 'pinia'
import { ref } from 'vue'
import { videoApi } from '@/api'
import type { Video } from '@/api'

export const useVideoStore = defineStore('video', () => {
  const videos = ref<Video[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const total = ref(0)
  const currentPage = ref(1)
  const pageSize = ref(20)

  async function fetchVideos(params?: {
    page?: number
    page_size?: number
    status?: string
    search?: string
  }) {
    loading.value = true
    error.value = null
    try {
      const res = await videoApi.list(params)
      videos.value = res.data.items
      total.value = res.data.total
      if (params?.page) currentPage.value = params.page
      if (params?.page_size) pageSize.value = params.page_size
    } catch (e) {
      error.value = '获取视频列表失败'
      console.error(e)
    } finally {
      loading.value = false
    }
  }

  async function deleteVideo(id: number) {
    try {
      await videoApi.remove(id)
      videos.value = videos.value.filter((v) => v.id !== id)
      total.value--
    } catch (e) {
      error.value = '删除视频失败'
      console.error(e)
      throw e
    }
  }

  async function updateVideoStatus(id: number, status: string) {
    try {
      await videoApi.updateStatus(id, status)
      const video = videos.value.find((v) => v.id === id)
      if (video) video.status = status
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  return { videos, loading, error, total, currentPage, pageSize, fetchVideos, deleteVideo, updateVideoStatus }
})
