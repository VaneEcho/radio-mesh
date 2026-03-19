<template>
  <div class="rt-view">

    <!-- ── Header ── -->
    <div class="rt-header">
      <div>
        <h1 class="page-title">实时频谱</h1>
        <p class="page-sub">订阅边缘节点的实时扫描帧，无刷新动态展示</p>
      </div>
      <!-- Connection controls -->
      <div class="ctrl-row">
        <select v-model="selectedStation" class="station-select" :disabled="connected">
          <option value="" disabled>-- 选择站点 --</option>
          <option v-for="s in stations" :key="s.station_id" :value="s.station_id">
            {{ s.name || s.station_id }}
            <template v-if="!s.online"> (离线)</template>
          </option>
        </select>
        <button
          class="btn"
          :class="connected ? 'btn-danger' : 'btn-primary'"
          :disabled="!selectedStation && !connected"
          @click="connected ? disconnect() : connect()"
        >
          {{ connected ? '断开' : '订阅' }}
        </button>
      </div>
    </div>

    <!-- ── Status bar ── -->
    <div class="status-bar">
      <span class="dot" :class="connected ? 'dot-green' : 'dot-grey'"></span>
      <span class="status-text">{{ statusText }}</span>
      <template v-if="connected">
        <span class="sep">·</span>
        <span>{{ frameCount }} 帧</span>
        <span class="sep">·</span>
        <span>{{ fpsDisplay }} fps</span>
        <span class="sep">·</span>
        <span>{{ rangeText }}</span>
      </template>
    </div>

    <!-- ── Chart ── -->
    <div class="chart-wrap">
      <div ref="chartEl" class="chart-canvas"></div>
      <div v-if="!connected && frameCount === 0" class="chart-placeholder">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#334155" stroke-width="1.2">
          <path d="M2 12 C5 7 9 4 12 4 C15 4 19 7 22 12"/>
          <path d="M5 12 C7 9 9.5 7 12 7 C14.5 7 17 9 19 12"/>
          <path d="M8 12 C9.5 10.5 10.5 10 12 10 C13.5 10 14.5 10.5 16 12"/>
          <circle cx="12" cy="14" r="2" fill="#334155" stroke="none"/>
        </svg>
        <p>选择在线站点后点击「订阅」</p>
      </div>
    </div>

    <!-- ── Waterfall ── -->
    <div v-if="waterfall.length > 0" class="section-title">瀑布图（最近 {{ waterfall.length }} 帧）</div>
    <div v-if="waterfall.length > 0" ref="wfEl" class="wf-wrap"></div>


  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { useTheme } from '../composables/useTheme.js'
import { getStations } from '../api/index.js'

const { isDark, chartColors } = useTheme()

// ── Station list ──────────────────────────────────────────────────────────────

const stations        = ref([])
const selectedStation = ref('')

async function fetchStations() {
  try { stations.value = await getStations() } catch { /* ignore */ }
}

onMounted(fetchStations)

// ── WebSocket state (spectrum) ────────────────────────────────────────────────

const connected  = ref(false)
const statusText = ref('未连接')
const frameCount = ref(0)
const rangeText  = ref('')

let ws       = null
let fpsFrames  = 0
let fpsTimer   = null
const fpsDisplay = ref('—')

// ── ECharts spectrum ──────────────────────────────────────────────────────────

const chartEl = ref(null)
let   chart   = null

function initChart() {
  if (!chartEl.value || chart) return
  chart = echarts.init(chartEl.value, chartColors.value.ecTheme)
  chart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 60, right: 16, top: 12, bottom: 36 },
    xAxis: {
      type: 'value',
      name: 'MHz',
      nameTextStyle: { color: chartColors.value.axisLabel, fontSize: 10 },
      axisLabel: { color: chartColors.value.axisLabel, fontSize: 10, formatter: v => v.toFixed(0) },
      axisLine: { lineStyle: { color: chartColors.value.axisLine } },
      splitLine: { lineStyle: { color: chartColors.value.splitLine, type: 'dashed' } },
    },
    yAxis: {
      type: 'value',
      name: 'dBm',
      nameTextStyle: { color: chartColors.value.axisLabel, fontSize: 10 },
      min: -120, max: -20,
      axisLabel: { color: chartColors.value.axisLabel, fontSize: 10 },
      axisLine: { lineStyle: { color: chartColors.value.axisLine } },
      splitLine: { lineStyle: { color: chartColors.value.splitLine, type: 'dashed' } },
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      {
        type: 'slider', xAxisIndex: 0, bottom: 6, height: 24,
        fillerColor: chartColors.value.dzFiller,
        borderColor: chartColors.value.axisLine,
        handleStyle: { color: chartColors.value.accent, borderColor: chartColors.value.accent },
        textStyle: { color: chartColors.value.axisLabel, fontSize: 10 },
        selectedDataBackground: {
          lineStyle: { color: chartColors.value.accent, width: 1 },
          areaStyle: { color: chartColors.value.dzFiller },
        },
        dataBackground: {
          lineStyle: { color: chartColors.value.axisLine, width: 1 },
          areaStyle: { color: chartColors.value.dzBg },
        },
      },
    ],
    series: [{
      type: 'line',
      data: [],
      symbol: 'none',
      sampling: 'lttb',
      lineStyle: { color: chartColors.value.accent, width: 1 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: chartColors.value.accentFill[1] },
            { offset: 1, color: chartColors.value.accentFill[2] },
          ],
        },
      },
    }],
  })
}

function updateChart(floats, meta) {
  if (!chart) initChart()
  if (!chart) return

  const step = meta.freq_step_hz ?? 25_000
  const f0   = meta.freq_start_hz ?? 20e6
  const data = Array.from(floats, (v, i) => [(f0 + i * step) / 1e6, Math.round(v * 10) / 10])

  const fStart = f0 / 1e6
  const fStop  = (f0 + (floats.length - 1) * step) / 1e6
  chart.setOption({ xAxis: { min: fStart, max: fStop }, series: [{ data }] }, false)

  rangeText.value = `${fStart.toFixed(1)} – ${fStop.toFixed(1)} MHz`
}

// ── Waterfall ─────────────────────────────────────────────────────────────────

const WF_ROWS  = 60
const waterfall = ref([])
const wfEl     = ref(null)
let   wfChart  = null

function initWfChart(numPts) {
  if (!wfEl.value) return
  if (wfChart) { wfChart.dispose(); wfChart = null }
  wfChart = echarts.init(wfEl.value, chartColors.value.ecTheme)
  wfChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 60, right: 16, top: 8, bottom: 36 },
    xAxis: {
      type: 'value',
      axisLabel: { color: chartColors.value.axisLabel, fontSize: 10, formatter: v => v.toFixed(0) + ' MHz' },
      axisLine: { lineStyle: { color: chartColors.value.axisLine } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      inverse: true,
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    visualMap: {
      show: false,
      min: -120, max: -30,
      inRange: {
        color: ['#060c18','#0f2040','#0e4080','#0060c0','#00a0e0','#00d0ff','#80ffff','#ffff00','#ff8000','#ff0000'],
      },
    },
    series: [{
      type: 'heatmap',
      data: [],
      itemStyle: { borderWidth: 0 },
    }],
  })
}

function updateWaterfall(floats, meta) {
  const arr = [...floats]
  waterfall.value.unshift(arr)
  if (waterfall.value.length > WF_ROWS) waterfall.value.pop()

  if (!wfEl.value) return

  const rows  = waterfall.value
  const step  = meta.freq_step_hz ?? 25_000
  const f0    = meta.freq_start_hz ?? 20e6
  const numPts = floats.length

  if (!wfChart || wfChart.getWidth() === 0) initWfChart(numPts)
  if (!wfChart) return

  const data = []
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r]
    for (let c = 0; c < row.length; c++) {
      data.push([(f0 + c * step) / 1e6, r, Math.round(row[c])])
    }
  }

  wfChart.setOption({
    xAxis: { min: f0 / 1e6, max: (f0 + (numPts - 1) * step) / 1e6 },
    yAxis: { min: 0, max: rows.length - 1 },
    series: [{ data }],
  }, false)
}

// ── Frame decode ──────────────────────────────────────────────────────────────

async function decodeFrame(msg) {
  const { b64, meta } = msg
  if (!b64 || !meta) return

  const binary = atob(b64)
  const bytes  = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

  const ds = new DecompressionStream('gzip')
  const writer = ds.writable.getWriter()
  writer.write(bytes)
  writer.close()

  try {
    const buf    = await new Response(ds.readable).arrayBuffer()
    const floats = new Float32Array(buf)
    updateChart(floats, meta)
    updateWaterfall(floats, meta)
  } catch {
    // ignore decode errors (stale/partial frame)
  }
}

// ── WebSocket connect / disconnect (spectrum) ─────────────────────────────────

function wsBase() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}`
}

function connect() {
  if (!selectedStation.value || connected.value) return

  const url = `${wsBase()}/api/v1/stream/${selectedStation.value}/ws`
  statusText.value = '连接中…'

  ws = new WebSocket(url)

  ws.onopen = () => {
    connected.value = true
    statusText.value = `已订阅 ${selectedStation.value}`
    startFpsTimer()
    if (!chart) initChart()
  }

  ws.onmessage = ({ data }) => {
    let msg
    try { msg = JSON.parse(data) } catch { return }

    if (msg.type === 'stream_frame') {
      frameCount.value++
      fpsFrames++
      decodeFrame(msg)
    }
  }

  ws.onerror = () => { statusText.value = '连接错误' }

  ws.onclose = () => {
    connected.value = false
    statusText.value = '已断开'
    stopFpsTimer()
    ws = null
  }
}

function disconnect() {
  if (ws) { ws.close(); ws = null }
}

function startFpsTimer() {
  fpsFrames = 0
  fpsTimer  = setInterval(() => {
    fpsDisplay.value = fpsFrames.toFixed(1)
    fpsFrames = 0
  }, 1000)
}

function stopFpsTimer() {
  if (fpsTimer) { clearInterval(fpsTimer); fpsTimer = null }
  fpsDisplay.value = '—'
}

// ── Resize handling ───────────────────────────────────────────────────────────

function onResize() {
  chart?.resize()
  wfChart?.resize()
}

watch(isDark, () => {
  if (chart) { chart.dispose(); chart = null }
  if (wfChart) { wfChart.dispose(); wfChart = null }
  // Charts will be re-initialized naturally when next frame arrives
})

onMounted(() => {
  window.addEventListener('resize', onResize)
  initChart()
})

onUnmounted(() => {
  disconnect()
  window.removeEventListener('resize', onResize)
  chart?.dispose();   chart   = null
  wfChart?.dispose(); wfChart = null
})
</script>

<style scoped>
.rt-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 100%;
  transition: background 0.2s, border-color 0.2s, color 0.2s;
}

/* ── Header ── */
.rt-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--c-text);
  margin-bottom: 4px;
}
.page-sub {
  font-size: 12px;
  color: var(--c-text-faint);
}

.ctrl-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}

.station-select {
  background: var(--c-raised);
  border: 1px solid var(--c-border);
  border-radius: 8px;
  color: var(--c-text-2);
  padding: 7px 12px;
  font-size: 13px;
  min-width: 180px;
  cursor: pointer;
}
.station-select:disabled { opacity: .5; cursor: default; }

.btn {
  padding: 7px 18px;
  border-radius: 8px;
  border: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
}
.btn:hover { opacity: .85; }
.btn:disabled { opacity: .35; cursor: default; }
.btn-primary   { background: var(--c-accent); color: var(--c-deep); }
.btn-danger    { background: var(--c-red); color: #fff; }
.btn-secondary { background: var(--c-border); color: var(--c-text-muted); border: 1px solid var(--c-border-str); }
.btn-sm { padding: 5px 12px; font-size: 12px; }

/* ── Status bar ── */
.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--c-text-dim);
  background: var(--c-card-2);
  border: 1px solid var(--c-border-sub);
  border-radius: 8px;
  padding: 8px 14px;
}
.dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-green { background: var(--c-green); box-shadow: 0 0 6px rgba(74,222,128,0.5); }
.dot-grey  { background: var(--c-text-ghost); }
.status-text { color: var(--c-text-muted); }
.sep { color: var(--c-border); }

/* ── Chart ── */
.chart-wrap {
  position: relative;
  background: var(--c-card);
  border: 1px solid var(--c-border-sub);
  border-radius: 12px;
  overflow: hidden;
  height: 320px;
}

.chart-canvas {
  width: 100%;
  height: 100%;
}

.chart-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--c-text-ghost);
  font-size: 13px;
  pointer-events: none;
}

/* ── Waterfall ── */
.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-text-faint);
  text-transform: uppercase;
  letter-spacing: .06em;
}

.wf-wrap {
  background: var(--c-card);
  border: 1px solid var(--c-border-sub);
  border-radius: 12px;
  overflow: hidden;
  height: 200px;
}

</style>
