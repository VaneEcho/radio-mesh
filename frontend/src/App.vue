<template>
  <div class="app-layout">

    <!-- ── Sidebar ── -->
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="3" fill="var(--c-accent)"/>
            <circle cx="12" cy="12" r="7" stroke="var(--c-accent)" stroke-width="1.5" stroke-dasharray="2 2" opacity=".5"/>
            <circle cx="12" cy="12" r="11" stroke="var(--c-accent)" stroke-width="1" stroke-dasharray="1 3" opacity=".25"/>
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
        <!-- Task sub-items -->
        <div class="nav-sub-group">
          <router-link :to="{ path: '/tasks', query: { type: 'band_scan' } }" class="nav-item nav-sub-item" :class="{ active: activeMenu === '/tasks?type=band_scan' }">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M3 10h18M3 14h18M3 18h18"/>
            </svg>
            <span>频段扫描</span>
          </router-link>
          <router-link :to="{ path: '/tasks', query: { type: 'channel_scan' } }" class="nav-item nav-sub-item" :class="{ active: activeMenu === '/tasks?type=channel_scan' }">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="5" width="18" height="14" rx="2"/>
              <path d="M8 5v14M16 5v14"/>
            </svg>
            <span>信道扫描</span>
          </router-link>
          <router-link :to="{ path: '/tasks', query: { type: 'if_analysis' } }" class="nav-item nav-sub-item" :class="{ active: activeMenu === '/tasks?type=if_analysis' }">
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4"/>
              <circle cx="12" cy="12" r="4"/>
            </svg>
            <span>中频分析</span>
          </router-link>
        </div>
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
        <button class="theme-btn" @click="toggleTheme" :title="isDark ? '切换到白天模式' : '切换到夜间模式'">
          <!-- Moon icon for dark mode (click to go light) -->
          <svg v-if="isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
          <!-- Sun icon for light mode (click to go dark) -->
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15">
            <circle cx="12" cy="12" r="5"/>
            <line x1="12" y1="1" x2="12" y2="3"/>
            <line x1="12" y1="21" x2="12" y2="23"/>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
            <line x1="1" y1="12" x2="3" y2="12"/>
            <line x1="21" y1="12" x2="23" y2="12"/>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
          <span>{{ isDark ? '夜间' : '白天' }}</span>
        </button>
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
import { useTheme } from './composables/useTheme.js'

const route = useRoute()
const activeMenu = computed(() => {
  if (route.path.startsWith('/spectrum')) return '/'
  if (route.path === '/tasks' && route.query.type) return `/tasks?type=${route.query.type}`
  return route.path
})

const { isDark, toggleTheme } = useTheme()
</script>

<style>
/* ── CSS Variables ────────────────────────────────────────────────────────── */
:root {
  /* Backgrounds */
  --c-bg:        #060c18;
  --c-card:      #080e1c;
  --c-card-2:    #0a0f1e;
  --c-raised:    #0f172a;
  --c-deep:      #040810;
  /* Borders */
  --c-border-sub: #0f1a2e;
  --c-border:     #1e293b;
  --c-border-str: #334155;
  /* Text */
  --c-text:       #f1f5f9;
  --c-text-2:     #e2e8f0;
  --c-text-muted: #94a3b8;
  --c-text-dim:   #64748b;
  --c-text-faint: #475569;
  --c-text-ghost: #334155;
  /* Accent (sky) */
  --c-accent:     #38bdf8;
  --c-accent-bg:  rgba(56,189,248,0.08);
  --c-accent-bgh: rgba(56,189,248,0.15);
  --c-accent-bgx: rgba(56,189,248,0.10);
  --c-accent-bgs: rgba(56,189,248,0.20);
  --c-accent-bds: rgba(56,189,248,0.20);
  --c-accent-bd:  rgba(56,189,248,0.40);
  /* Status */
  --c-green:      #4ade80;
  --c-green-bg:   rgba(74,222,128,0.08);
  --c-green-bd:   rgba(74,222,128,0.25);
  --c-red:        #f87171;
  --c-red-bg:     rgba(239,68,68,0.08);
  --c-red-bd:     rgba(239,68,68,0.25);
  --c-red-bdx:    rgba(239,68,68,0.40);
  --c-indigo:     #818cf8;
  --c-indigo-bg:  rgba(99,102,241,0.08);
  --c-indigo-bd:  rgba(99,102,241,0.30);
  --c-gold:       #fbbf24;
  --c-gold-bg:    rgba(251,191,36,0.10);
  --c-gold-bd:    rgba(251,191,36,0.30);
  --c-orange:     #fb923c;
  /* Overlay */
  --c-overlay:    rgba(0,0,0,0.60);
  --c-overlay-s:  rgba(0,0,0,0.70);
  /* Element Plus dark overrides */
  --el-color-primary:       #38bdf8;
  --el-bg-color:            #0f172a;
  --el-bg-color-overlay:    #0f172a;
  --el-border-color:        #1e293b;
  --el-text-color-primary:  #e2e8f0;
  --el-text-color-regular:  #94a3b8;
  --el-fill-color-blank:    #0f172a;
}

[data-theme="light"] {
  --c-bg:        #f0f4f8;
  --c-card:      #ffffff;
  --c-card-2:    #f8fafc;
  --c-raised:    #f1f5f9;
  --c-deep:      #f1f5f9;
  --c-border-sub: #e8edf2;
  --c-border:     #cbd5e1;
  --c-border-str: #94a3b8;
  --c-text:       #0f172a;
  --c-text-2:     #1e293b;
  --c-text-muted: #475569;
  --c-text-dim:   #64748b;
  --c-text-faint: #94a3b8;
  --c-text-ghost: #cbd5e1;
  --c-accent:     #0284c7;
  --c-accent-bg:  rgba(2,132,199,0.06);
  --c-accent-bgh: rgba(2,132,199,0.12);
  --c-accent-bgx: rgba(2,132,199,0.08);
  --c-accent-bgs: rgba(2,132,199,0.15);
  --c-accent-bds: rgba(2,132,199,0.25);
  --c-accent-bd:  rgba(2,132,199,0.50);
  --c-green:      #16a34a;
  --c-green-bg:   rgba(22,163,74,0.08);
  --c-green-bd:   rgba(22,163,74,0.30);
  --c-red:        #dc2626;
  --c-red-bg:     rgba(220,38,38,0.08);
  --c-red-bd:     rgba(220,38,38,0.30);
  --c-red-bdx:    rgba(220,38,38,0.50);
  --c-indigo:     #4f46e5;
  --c-indigo-bg:  rgba(79,70,229,0.08);
  --c-indigo-bd:  rgba(79,70,229,0.30);
  --c-gold:       #d97706;
  --c-gold-bg:    rgba(217,119,6,0.08);
  --c-gold-bd:    rgba(217,119,6,0.30);
  --c-orange:     #ea580c;
  --c-overlay:    rgba(0,0,0,0.30);
  --c-overlay-s:  rgba(0,0,0,0.40);
  /* Element Plus light overrides */
  --el-color-primary:       #0284c7;
  --el-bg-color:            #f1f5f9;
  --el-bg-color-overlay:    #ffffff;
  --el-border-color:        #cbd5e1;
  --el-text-color-primary:  #0f172a;
  --el-text-color-regular:  #475569;
  --el-fill-color-blank:    #ffffff;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #app { height: 100%; }
body {
  background: var(--c-bg);
  color: var(--c-text-2);
  font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
  transition: background 0.2s, color 0.2s;
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
  background: var(--c-card);
  border-right: 1px solid var(--c-border-sub);
  display: flex;
  flex-direction: column;
  transition: background 0.2s, border-color 0.2s;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 20px 18px;
  border-bottom: 1px solid var(--c-border-sub);
}
.logo-icon {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  background: var(--c-accent-bg);
  border: 1px solid var(--c-accent-bds);
  border-radius: 8px;
}
.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--c-text);
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
  color: var(--c-text-faint);
  text-decoration: none;
  transition: all .15s;
}
.nav-item:hover { background: var(--c-accent-bg); color: var(--c-text-muted); }
.nav-item.active { background: var(--c-accent-bgx); color: var(--c-accent); }
.nav-item.active .nav-icon { opacity: 1; }

.nav-icon {
  width: 16px; height: 16px;
  flex-shrink: 0;
  opacity: .6;
}
.nav-item.active .nav-icon { opacity: 1; }

.nav-sub-group {
  position: relative;
  padding-left: 18px;
  margin: 1px 0 2px;
}
.nav-sub-group::before {
  content: '';
  position: absolute;
  left: 20px;
  top: 6px;
  bottom: 6px;
  width: 1px;
  background: var(--c-border);
}
.nav-sub-item {
  font-size: 12px;
  padding: 7px 10px 7px 16px;
  color: var(--c-text-ghost);
}
.nav-sub-item .nav-icon { width: 14px; height: 14px; }
.nav-sub-item:hover { color: var(--c-text-dim); }
.nav-sub-item.active { color: var(--c-accent); }

.sidebar-footer {
  padding: 12px 14px;
  border-top: 1px solid var(--c-border-sub);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.theme-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 8px;
  background: var(--c-raised);
  border: 1px solid var(--c-border);
  color: var(--c-text-dim);
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
}
.theme-btn:hover { border-color: var(--c-accent); color: var(--c-accent); }

.version-badge {
  display: inline-block;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 5px;
  background: var(--c-raised);
  color: var(--c-text-ghost);
  border: 1px solid var(--c-border);
}

/* ── Main ── */
.main-content {
  flex: 1;
  overflow-y: auto;
  background: var(--c-bg);
  padding: 28px 32px;
  transition: background 0.2s;
}
</style>
