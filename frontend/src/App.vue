<template>
  <div class="app-layout">

    <!-- ── Sidebar ── -->
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="3" fill="#38bdf8"/>
            <circle cx="12" cy="12" r="7" stroke="#38bdf8" stroke-width="1.5" stroke-dasharray="2 2" opacity=".5"/>
            <circle cx="12" cy="12" r="11" stroke="#38bdf8" stroke-width="1" stroke-dasharray="1 3" opacity=".25"/>
          </svg>
        </div>
        <span class="logo-text">RF·MESH</span>
      </div>

      <nav class="sidebar-nav">
        <router-link to="/" class="nav-item" :class="{ active: activeMenu === '/' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="3" width="7" height="7" rx="1.5"/>
            <rect x="15" y="3" width="7" height="7" rx="1.5"/>
            <rect x="2" y="14" width="7" height="7" rx="1.5"/>
            <rect x="15" y="14" width="7" height="7" rx="1.5"/>
          </svg>
          <span>站点总览</span>
        </router-link>
        <router-link to="/freq-query" class="nav-item" :class="{ active: activeMenu === '/freq-query' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
            <path d="M11 8v6M8 11h6"/>
          </svg>
          <span>频点查询</span>
        </router-link>
        <router-link to="/freq-assign" class="nav-item" :class="{ active: activeMenu === '/freq-assign' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12h18M3 6h18M3 18h18"/>
            <circle cx="9" cy="6" r="2" fill="currentColor" stroke="none"/>
            <circle cx="15" cy="12" r="2" fill="currentColor" stroke="none"/>
            <circle cx="9"  cy="18" r="2" fill="currentColor" stroke="none"/>
          </svg>
          <span>频率指配</span>
        </router-link>
        <router-link to="/tasks" class="nav-item" :class="{ active: activeMenu === '/tasks' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/>
            <rect x="9" y="3" width="6" height="4" rx="1"/>
            <path d="M9 12h6M9 16h4"/>
          </svg>
          <span>任务下发</span>
        </router-link>
        <router-link to="/realtime" class="nav-item" :class="{ active: activeMenu === '/realtime' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="2 12 6 6 10 14 14 8 18 14 22 9"/>
          </svg>
          <span>实时频谱</span>
        </router-link>
        <router-link to="/playback" class="nav-item" :class="{ active: activeMenu === '/playback' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none"/>
          </svg>
          <span>历史回放</span>
        </router-link>
        <router-link to="/analysis" class="nav-item" :class="{ active: activeMenu === '/analysis' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V9"/>
            <polyline points="9 3 9 9 15 9"/>
            <line x1="12" y1="13" x2="12" y2="17"/>
            <line x1="10" y1="15" x2="14" y2="15"/>
          </svg>
          <span>信号分析</span>
        </router-link>
        <router-link to="/signals" class="nav-item" :class="{ active: activeMenu === '/signals' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
            <line x1="10" y1="8" x2="16" y2="8"/>
            <line x1="10" y1="12" x2="16" y2="12"/>
            <line x1="10" y1="16" x2="14" y2="16"/>
          </svg>
          <span>信号库</span>
        </router-link>
        <router-link to="/band-rules" class="nav-item" :class="{ active: activeMenu === '/band-rules' }">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 6h16M4 10h16M4 14h10M4 18h7"/>
          </svg>
          <span>频段规则</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="version-badge">v0.8</div>
      </div>
    </aside>

    <!-- ── Main ── -->
    <main class="main-content">
      <router-view />
    </main>

  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => {
  if (route.path.startsWith('/spectrum')) return '/'
  return route.path
})
</script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #app { height: 100%; }
body {
  background: #060c18;
  color: #e2e8f0;
  font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}

/* Element Plus dark overrides */
:root {
  --el-color-primary: #38bdf8;
  --el-bg-color: #0f172a;
  --el-bg-color-overlay: #0f172a;
  --el-border-color: #1e293b;
  --el-text-color-primary: #e2e8f0;
  --el-text-color-regular: #94a3b8;
  --el-fill-color-blank: #0f172a;
}
</style>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ── Sidebar ── */
.sidebar {
  width: 200px;
  flex-shrink: 0;
  background: #080e1c;
  border-right: 1px solid #0f1a2e;
  display: flex;
  flex-direction: column;
  padding: 0;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 20px 18px;
  border-bottom: 1px solid #0f1a2e;
}
.logo-icon {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(56,189,248,0.08);
  border: 1px solid rgba(56,189,248,0.2);
  border-radius: 8px;
}
.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: #f1f5f9;
  letter-spacing: 1px;
}

.sidebar-nav {
  flex: 1;
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  text-decoration: none;
  transition: all .15s;
}
.nav-item:hover { background: rgba(255,255,255,0.03); color: #94a3b8; }
.nav-item.active { background: rgba(56,189,248,0.1); color: #38bdf8; }
.nav-item.active .nav-icon { opacity: 1; }

.nav-icon {
  width: 16px; height: 16px;
  flex-shrink: 0;
  opacity: .6;
}
.nav-item.active .nav-icon { opacity: 1; }

.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid #0f1a2e;
}
.version-badge {
  display: inline-block;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 5px;
  background: #0f172a;
  color: #334155;
  border: 1px solid #1e293b;
}

/* ── Main ── */
.main-content {
  flex: 1;
  overflow-y: auto;
  background: #060c18;
  padding: 28px 32px;
}
</style>
