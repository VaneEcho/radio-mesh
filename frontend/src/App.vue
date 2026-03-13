<template>
  <el-container class="app-layout">

    <!-- ── Sidebar ── -->
    <el-aside width="200px" class="sidebar">
      <div class="logo">
        <el-icon size="20"><Cpu /></el-icon>
        <span>RF·MESH</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        router
        background-color="#1a1f2e"
        text-color="#a0aec0"
        active-text-color="#63b3ed"
      >
        <el-menu-item index="/">
          <el-icon><Monitor /></el-icon>
          <span>站点总览</span>
        </el-menu-item>
        <el-menu-item index="/band-rules">
          <el-icon><List /></el-icon>
          <span>频段规则</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- ── Main ── -->
    <el-container>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>

  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
// Highlight the sidebar item that matches the current path
const activeMenu = computed(() => {
  if (route.path.startsWith('/spectrum')) return '/'
  return route.path
})
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #app { height: 100%; }
body { background: #0d111c; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
</style>

<style scoped>
.app-layout { height: 100vh; }

.sidebar {
  background: #1a1f2e;
  border-right: 1px solid #2d3748;
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  font-size: 18px;
  font-weight: 700;
  color: #63b3ed;
  border-bottom: 1px solid #2d3748;
  letter-spacing: 1px;
}

.main-content {
  background: #0d111c;
  padding: 24px;
  overflow-y: auto;
}
</style>
