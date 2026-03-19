<template>
  <div class="stations-page">
    <!-- ── Header ── -->
    <div class="page-header mb28">
      <div>
        <h2 class="page-title">站点总览</h2>
        <p class="page-sub">监测节点在线状态 · 每 10 秒自动刷新</p>
      </div>
      <button class="refresh-btn" :class="{ spinning: loading }" @click="load" title="刷新">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
          <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
          <path d="M21 3v5h-5"/>
          <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
          <path d="M3 21v-5h5"/>
        </svg>
      </button>
    </div>

    <!-- ── Error ── -->
    <div v-if="error" class="error-bar mb20">{{ error }}</div>

    <!-- ── Stats strip ── -->
    <div v-if="stations.length" class="stats-strip mb28">
      <div class="stat-item">
        <div class="stat-val">{{ stations.length }}</div>
        <div class="stat-lbl">总站点</div>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <div class="stat-val online-val">{{ stations.filter(s => s.online).length }}</div>
        <div class="stat-lbl">在线</div>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <div class="stat-val offline-val">{{ stations.filter(s => !s.online).length }}</div>
        <div class="stat-lbl">离线</div>
      </div>
    </div>

    <!-- ── Empty state ── -->
    <div v-if="!loading && stations.length === 0 && !error" class="empty-state">
      <div class="empty-icon">📡</div>
      <div class="empty-text">暂无已注册站点</div>
      <div class="empty-hint">请启动边缘节点</div>
    </div>

    <!-- ── Station cards ── -->
    <div class="cards-grid">
      <div
        v-for="s in stations"
        :key="s.station_id"
        class="station-card"
        :class="{ online: s.online }"
        @click="goSpectrum(s.station_id)"
      >
        <div class="card-glow" v-if="s.online" />

        <div class="card-top">
          <div class="status-indicator" :class="s.online ? 'online' : 'offline'">
            <span class="dot" />
            <span class="pulse" v-if="s.online" />
          </div>
          <div class="card-arrow">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </div>
        </div>

        <div class="card-body">
          <div class="card-id">{{ s.station_id }}</div>
          <div class="card-name">{{ s.name || '—' }}</div>
        </div>

        <div class="card-footer">
          <span class="status-tag" :class="s.online ? 'tag-online' : 'tag-offline'">
            {{ s.online ? '在线' : '离线' }}
          </span>
          <span class="last-seen" v-if="s.last_seen_ms">{{ relativeTime(s.last_seen_ms) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getStations } from '../api/index.js'

const router = useRouter()
const stations = ref([])
const loading  = ref(false)
const error    = ref('')
let timer = null

async function load() {
  loading.value = true
  error.value = ''
  try {
    stations.value = await getStations()
  } catch (e) {
    error.value = '无法获取站点列表：' + (e.message || '网络错误')
  } finally {
    loading.value = false
  }
}

function goSpectrum(stationId) {
  router.push({ name: 'spectrum', params: { stationId } })
}

function relativeTime(ms) {
  const diff = Date.now() - ms
  if (diff < 60_000) return `${Math.floor(diff / 1000)} 秒前`
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  return `${Math.floor(diff / 3_600_000)} 小时前`
}

onMounted(() => {
  load()
  timer = setInterval(load, 10_000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.stations-page { transition: background 0.2s, border-color 0.2s, color 0.2s; }
.mb20 { margin-bottom: 20px; }
.mb28 { margin-bottom: 28px; }

/* ── Header ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.page-title { font-size: 24px; font-weight: 700; color: var(--c-text); letter-spacing: -0.3px; }
.page-sub   { font-size: 13px; color: var(--c-text-dim); margin-top: 3px; }

.refresh-btn {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 9px;
  background: var(--c-raised);
  border: 1px solid var(--c-border);
  color: var(--c-text-dim);
  cursor: pointer;
  transition: all .15s;
}
.refresh-btn:hover { border-color: var(--c-border-str); color: var(--c-text-muted); }
.refresh-btn.spinning svg { animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Error ── */
.error-bar {
  background: var(--c-red-bg); border: 1px solid var(--c-red-bd);
  border-radius: 10px; padding: 10px 16px; color: var(--c-red); font-size: 13px;
}

/* ── Stats strip ── */
.stats-strip {
  display: inline-flex;
  align-items: center;
  gap: 0;
  background: var(--c-card-2);
  border: 1px solid var(--c-border);
  border-radius: 12px;
  padding: 12px 24px;
  gap: 24px;
}
.stat-item { text-align: center; }
.stat-val  { font-size: 22px; font-weight: 700; color: var(--c-text-2); line-height: 1; }
.stat-lbl  { font-size: 11px; color: var(--c-text-faint); margin-top: 3px; }
.online-val  { color: var(--c-green); }
.offline-val { color: var(--c-text-dim); }
.stat-divider { width: 1px; height: 32px; background: var(--c-border); }

/* ── Empty ── */
.empty-state { text-align: center; padding: 100px 0; }
.empty-icon  { font-size: 52px; opacity: .3; margin-bottom: 12px; }
.empty-text  { font-size: 15px; color: var(--c-text-faint); }
.empty-hint  { font-size: 13px; color: var(--c-text-ghost); margin-top: 4px; }

/* ── Cards grid ── */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.station-card {
  position: relative;
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 18px;
  cursor: pointer;
  transition: border-color .2s, transform .15s, box-shadow .2s, background 0.2s, color 0.2s;
  overflow: hidden;
}
.station-card:hover {
  border-color: var(--c-border-str);
  transform: translateY(-2px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.station-card.online { border-color: #0f3d2a; }
.station-card.online:hover { border-color: #166534; }

.card-glow {
  position: absolute;
  top: -20px; right: -20px;
  width: 80px; height: 80px;
  background: radial-gradient(circle, var(--c-green-bg) 0%, transparent 70%);
  pointer-events: none;
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

/* Status indicator with pulse */
.status-indicator { position: relative; width: 10px; height: 10px; }
.status-indicator .dot {
  position: absolute; inset: 0;
  border-radius: 50%;
  background: var(--c-border);
}
.status-indicator.online .dot { background: var(--c-green); }
.status-indicator.online .pulse {
  position: absolute; inset: -3px;
  border-radius: 50%;
  background: var(--c-green-bd);
  animation: pulse 2s ease-out infinite;
}
@keyframes pulse {
  0%   { transform: scale(1); opacity: .6; }
  100% { transform: scale(2.2); opacity: 0; }
}

.card-arrow { color: var(--c-border); transition: color .15s; }
.station-card:hover .card-arrow { color: var(--c-border-str); }
.station-card.online:hover .card-arrow { color: #166534; }

.card-body { margin-bottom: 14px; }
.card-id   { font-size: 15px; font-weight: 600; color: var(--c-text-2); }
.card-name { font-size: 12px; color: var(--c-text-faint); margin-top: 3px; }

.card-footer { display: flex; align-items: center; gap: 10px; }

.status-tag {
  font-size: 11px; font-weight: 500;
  padding: 2px 9px; border-radius: 6px;
  border: 1px solid;
}
.tag-online  { background: var(--c-green-bg); border-color: var(--c-green-bd); color: var(--c-green); }
.tag-offline { background: rgba(71,85,105,0.2);   border-color: var(--c-border); color: var(--c-text-faint); }

.last-seen { font-size: 11px; color: var(--c-text-ghost); }
</style>
