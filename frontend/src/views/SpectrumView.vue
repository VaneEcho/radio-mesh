<template>
  <div>
    <!-- ── Breadcrumb ── -->
    <el-breadcrumb separator="/" class="mb16">
      <el-breadcrumb-item :to="{ path: '/' }">站点总览</el-breadcrumb-item>
      <el-breadcrumb-item>{{ stationId }}</el-breadcrumb-item>
    </el-breadcrumb>

    <!-- ── Page header ── -->
    <div class="page-header mb24">
      <div>
        <h2 class="page-title">频谱查看 — {{ stationId }}</h2>
        <p class="page-sub">{{ frames.length }} 帧数据 · 点击频谱上的帧时间线可切换</p>
      </div>
    </div>

    <!-- ── Query bar ── -->
    <el-card class="query-bar mb24" shadow="never">
      <el-form inline>
        <el-form-item label="时间范围">
          <el-select v-model="preset" style="width:130px" @change="applyPreset">
            <el-option label="最近 1 小时" value="1h" />
            <el-option label="最近 6 小时" value="6h" />
            <el-option label="最近 24 小时" value="24h" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="preset === 'custom'" label="开始">
          <el-date-picker v-model="customStart" type="datetime" style="width:180px"
            value-format="x" placeholder="开始时间" />
        </el-form-item>
        <el-form-item v-if="preset === 'custom'" label="结束">
          <el-date-picker v-model="customEnd" type="datetime" style="width:180px"
            value-format="x" placeholder="结束时间" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="query">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ── Error ── -->
    <el-alert v-if="error" :title="error" type="error" show-icon closable class="mb24" />

    <!-- ── No data ── -->
    <el-empty v-if="!loading && frames.length === 0 && queried && !error"
      description="该时间段内暂无频谱数据" />

    <!-- ── Main chart ── -->
    <el-card v-if="currentFrame" shadow="never" class="mb16">
      <template #header>
        <div class="chart-header">
          <span>频谱 — {{ fmtTime(currentFrame.period_start_ms) }}</span>
          <span class="chart-meta">
            {{ (currentFrame.freq_start_hz / 1e6).toFixed(1) }} –
            {{ endFreqMHz(currentFrame).toFixed(1) }} MHz ·
            {{ currentFrame.num_points.toLocaleString() }} 点 ·
            {{ currentFrame.sweep_count }} 次扫描合并
          </span>
        </div>
      </template>
      <div ref="chartEl" class="chart-area" />
    </el-card>

    <!-- ── Frame timeline ── -->
    <el-card v-if="frames.length > 1" shadow="never">
      <template #header><span>帧时间线（共 {{ frames.length }} 帧，点击切换）</span></template>
      <div class="timeline">
        <div
          v-for="(f, i) in frames"
          :key="f.frame_id"
          class="tl-item"
          :class="{ active: i === frameIdx }"
          @click="selectFrame(i)"
        >
          {{ fmtTimeShort(f.period_start_ms) }}
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import pako from 'pako'
import { querySpectrum } from '../api/index.js'

const route = useRoute()
const stationId = route.params.stationId

// ── State ───────────────────────────────────────────────────────────────────

const preset      = ref('1h')
const customStart = ref(null)
const customEnd   = ref(null)
const loading     = ref(false)
const error       = ref('')
const frames      = ref([])
const frameIdx    = ref(0)
const queried     = ref(false)
const chartEl     = ref(null)

let chart = null

const currentFrame = ref(null)

// ── Time helpers ─────────────────────────────────────────────────────────────

function applyPreset() {
  if (preset.value !== 'custom') query()
}

function timeRange() {
  const end = Date.now()
  const map = { '1h': 3_600_000, '6h': 21_600_000, '24h': 86_400_000 }
  if (preset.value in map) return [end - map[preset.value], end]
  return [Number(customStart.value), Number(customEnd.value)]
}

function fmtTime(ms) {
  return new Date(ms).toLocaleString('zh-CN', { hour12: false })
}
function fmtTimeShort(ms) {
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false })
}
function endFreqMHz(f) {
  return (f.freq_start_hz + f.freq_step_hz * (f.num_points - 1)) / 1e6
}

// ── Query ────────────────────────────────────────────────────────────────────

async function query() {
  loading.value = true
  error.value = ''
  try {
    const [start, end] = timeRange()
    const res = await querySpectrum(stationId, start, end)
    frames.value = res.rows
    frameIdx.value = frames.value.length - 1   // start at the most recent
    queried.value = true
    if (frames.value.length) {
      currentFrame.value = frames.value[frameIdx.value]
    } else {
      currentFrame.value = null
    }
  } catch (e) {
    error.value = '查询失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function selectFrame(i) {
  frameIdx.value = i
  currentFrame.value = frames.value[i]
}

// ── Spectrum decoding ─────────────────────────────────────────────────────────

/**
 * Decode base64(gzip(float32[])) → { freqs: Float32Array, levels: Float32Array }
 *
 * Why pako?  The browser's native CompressionStream only supports streaming
 * decompression and can't handle raw gzip in a synchronous call.  pako is a
 * pure-JS zlib/gzip implementation that works synchronously.
 */
function decodeFrame(frame) {
  const b64    = frame.levels_dbm_b64
  const binary = atob(b64)
  const bytes  = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

  const raw    = pako.inflate(bytes)                      // Uint8Array
  const levels = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4)

  // Build parallel frequency array (MHz)
  const freqs = new Float32Array(levels.length)
  const start = frame.freq_start_hz / 1e6
  const step  = frame.freq_step_hz  / 1e6
  for (let i = 0; i < levels.length; i++) freqs[i] = start + i * step

  return { freqs, levels }
}

// ── ECharts ──────────────────────────────────────────────────────────────────

function buildChart() {
  if (!chartEl.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartEl.value, 'dark')
  window.__rfmeshChart = chart   // handy for debug in browser console
}

// Zoom threshold: visible range < 5% of total → disable LTTB, show raw points
const ZOOM_RAW_THRESHOLD = 5

let _cachedData = null

function renderFrame(frame) {
  if (!chart) return
  const { freqs, levels } = decodeFrame(frame)

  const data = []
  for (let i = 0; i < freqs.length; i++) {
    data.push([freqs[i], levels[i]])
  }

  const minFreq = freqs[0]
  const maxFreq = freqs[freqs.length - 1]
  _cachedData = data

  chart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 60, right: 20, top: 20, bottom: 50 },
    tooltip: {
      trigger: 'axis',
      formatter: ([p]) => `${p.data[0].toFixed(3)} MHz<br/>${p.data[1].toFixed(1)} dBm`,
      backgroundColor: '#1a1f2e',
      borderColor: '#4a5568',
      textStyle: { color: '#e2e8f0', fontSize: 12 },
    },
    xAxis: {
      type: 'value',
      name: '频率 (MHz)',
      nameLocation: 'middle',
      nameGap: 30,
      min: minFreq,
      max: maxFreq,
      axisLabel: { color: '#a0aec0', fontSize: 11 },
      splitLine: { lineStyle: { color: '#2d3748' } },
    },
    yAxis: {
      type: 'value',
      name: 'dBm',
      nameLocation: 'middle',
      nameGap: 40,
      axisLabel: { color: '#a0aec0', fontSize: 11 },
      splitLine: { lineStyle: { color: '#2d3748' } },
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      { type: 'slider',  xAxisIndex: 0, bottom: 4,
        fillerColor: 'rgba(99,179,237,0.1)',
        borderColor: '#4a5568',
        textStyle: { color: '#a0aec0' },
      },
    ],
    series: [{
      type: 'line',
      data,
      sampling: 'lttb',
      symbol: 'none',
      lineStyle: { color: '#63b3ed', width: 1.2 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(99,179,237,0.3)' },
          { offset: 1, color: 'rgba(99,179,237,0)' },
        ]),
      },
    }],
  }, true)

  // Adaptive sampling: switch to raw points when zoomed in past threshold
  chart.off('datazoom')
  chart.on('datazoom', () => {
    const option = chart.getOption()
    const dz = option.dataZoom[0]
    const visiblePct = (dz.end ?? 100) - (dz.start ?? 0)
    const sampling = visiblePct < ZOOM_RAW_THRESHOLD ? null : 'lttb'
    chart.setOption({ series: [{ sampling }] })
  })
}

// Re-render whenever currentFrame changes
watch(currentFrame, async (frame) => {
  if (!frame) return
  await nextTick()
  if (!chart) buildChart()
  renderFrame(frame)
})

// Handle window resize
function onResize() { chart?.resize() }

onMounted(() => {
  window.addEventListener('resize', onResize)
  query()   // auto-load last 1 hour on open
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<style scoped>
.mb16  { margin-bottom: 16px; }
.mb24  { margin-bottom: 24px; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; }
.page-title  { font-size: 22px; font-weight: 600; color: #e2e8f0; }
.page-sub    { font-size: 13px; color: #718096; margin-top: 4px; }

:deep(.query-bar .el-card__body) { padding: 14px 20px 4px; }
:deep(.el-card) {
  background: #1a1f2e;
  border-color: #2d3748;
  --el-card-bg-color: #1a1f2e;
}
:deep(.el-card__header) {
  border-bottom-color: #2d3748;
  padding: 12px 20px;
  color: #a0aec0;
  font-size: 13px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #e2e8f0;
  font-size: 14px;
}
.chart-meta { color: #718096; font-size: 12px; }

.chart-area { width: 100%; height: 420px; }

.timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
}
.tl-item {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  background: #2d3748;
  color: #a0aec0;
  cursor: pointer;
  white-space: nowrap;
  transition: background .15s;
}
.tl-item:hover  { background: #4a5568; }
.tl-item.active { background: #2b4c7e; color: #63b3ed; }
</style>
