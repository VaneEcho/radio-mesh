<template>
  <div>
    <!-- ── Header ── -->
    <div class="page-header">
      <div>
        <h2 class="page-title">站点总览</h2>
        <p class="page-sub">监测节点在线状态 · 每 10 秒自动刷新</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load" circle />
    </div>

    <!-- ── Error banner ── -->
    <el-alert v-if="error" :title="error" type="error" show-icon closable class="mb" />

    <!-- ── Empty state ── -->
    <el-empty
      v-if="!loading && stations.length === 0 && !error"
      description="暂无已注册站点 — 请启动边缘节点"
    />

    <!-- ── Station cards ── -->
    <div class="cards-grid">
      <div
        v-for="s in stations"
        :key="s.station_id"
        class="station-card"
        :class="{ online: s.online }"
        @click="goSpectrum(s.station_id)"
      >
        <!-- Status indicator dot -->
        <span class="status-dot" :class="s.online ? 'dot-online' : 'dot-offline'" />

        <div class="card-body">
          <div class="card-id">{{ s.station_id }}</div>
          <div class="card-name">{{ s.name }}</div>
        </div>

        <div class="card-footer">
          <el-tag :type="s.online ? 'success' : 'info'" size="small" effect="dark">
            {{ s.online ? '在线' : '离线' }}
          </el-tag>
          <span class="last-seen" v-if="s.last_seen_ms">
            {{ relativeTime(s.last_seen_ms) }}
          </span>
        </div>

        <div class="card-arrow">
          <el-icon><ArrowRight /></el-icon>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, ArrowRight } from '@element-plus/icons-vue'
import { getStations } from '../api/index.js'

const router = useRouter()
const stations = ref([])
const loading = ref(false)
const error = ref('')
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

/** e.g. "3 分钟前" */
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
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}
.page-title { font-size: 22px; font-weight: 600; color: #e2e8f0; }
.page-sub { font-size: 13px; color: #718096; margin-top: 4px; }
.mb { margin-bottom: 16px; }

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.station-card {
  position: relative;
  background: #1a1f2e;
  border: 1px solid #2d3748;
  border-radius: 10px;
  padding: 18px 44px 18px 18px;
  cursor: pointer;
  transition: border-color .2s, transform .1s;
}
.station-card:hover { border-color: #4a5568; transform: translateY(-1px); }
.station-card.online { border-color: #276749; }
.station-card.online:hover { border-color: #38a169; }

.status-dot {
  position: absolute;
  top: 18px;
  right: 44px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.dot-online  { background: #48bb78; box-shadow: 0 0 6px #48bb78; }
.dot-offline { background: #4a5568; }

.card-body { margin-bottom: 14px; }
.card-id   { font-size: 15px; font-weight: 600; color: #e2e8f0; }
.card-name { font-size: 13px; color: #a0aec0; margin-top: 2px; }

.card-footer {
  display: flex;
  align-items: center;
  gap: 10px;
}
.last-seen { font-size: 12px; color: #718096; }

.card-arrow {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  color: #4a5568;
}
.station-card:hover .card-arrow { color: #a0aec0; }
</style>
