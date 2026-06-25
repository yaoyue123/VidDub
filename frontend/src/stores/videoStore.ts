import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

export interface Video {
  id: number
  youtube_url: string
  youtube_id: string
  title: string
  channel: string
  duration: number | null
  view_count: number | null
  like_count: number | null
  thumbnail_url: string | null
  status: string
  filepath: string | null
  dubbed_filepath: string | null
  created_at: string
  updated_at: string
}

interface VideoListResponse {
  total: number
  items: Video[]
}

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
      const res = await api.get<VideoListResponse>('/videos', { params })
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
      await api.delete(`/videos/${id}`)
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
      await api.patch(`/videos/${id}/status`, { status })
      const video = videos.value.find((v) => v.id === id)
      if (video) video.status = status
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  return { videos, loading, error, total, currentPage, pageSize, fetchVideos, deleteVideo, updateVideoStatus }
})
