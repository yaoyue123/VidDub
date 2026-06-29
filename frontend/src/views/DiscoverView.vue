<script setup lang="ts">
/**
 * Placeholder for Phase 10 DiscoverView rewrite.
 * Phase 7 cleanup removed v4.0 scoring references.
 */
</script>

<template>
  <div class="discover-placeholder">
    <el-empty
      description="发现页面正在重构中 (Phase 10)"
      :image-size="80"
    >
      <el-button type="primary" @click="$router.push('/videos')">
        前往视频列表
      </el-button>
    </el-empty>
  </div>
</template>

<style scoped>
.discover-placeholder {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
}
</style>
