<template>
  <div class="pb-view">

    <!-- ── Header ── -->
    <div class="pb-header">
      <div>
        <h1 class="page-title">历史回放</h1>
        <p class="page-sub">浏览指定站点、时间段内的历史频谱帧，支持逐帧回放与对比</p>
      </div>
    </div>

    <!-- ── Query bar ── -->
    <div class="query-bar card">
      <div class="qb-row">
        <label class="qb-label">站点</label>
        <select v-model="selectedStation" class="sel">
          <option value="" disabled>-- 选择站点 --</option>
          <option v-for="s in stations" :key="s.station_id" :value="s.station_id">
            {{ s.name || s.station_id }}
          </option>
        </select>

        <label class="qb-label">开始时间</label>
        <input type="datetime-local" v-model="startDt" class="dt-input" />

        <label class="qb-label">结束时间</label>
        <input type="datetime-local" v-model="endDt" class="dt-input" />

        <button class="btn btn-primary" :disabled="loading || !selectedStation" @click="querySnapshots">
          {{ loading ? '查询中…' : '查询' }}
        </button>
      </div>
    </div>

    <!-- ── Content ── -->
    <div v-if="snapshots.length > 0" class="pb-body">

      <!-- Left: frame list -->
      <div class="frame-list card">
        <div class="fl-header">
          <span class="fl-title">帧列表（{{ snapshots.length }} 帧）</span>
          <label class="compare-toggle">
            <input type="checkbox" v-model="compareMode" />
            对比模式
          </label>
        </div>
        <div class="fl-scroll">
          <div
            v-for="snap in snapshots"
            :key="snap.frame_id"
            class="fl-item"
            :class="{
              'fl-active': !compareMode && selectedFrame?.frame_id === snap.frame_id,
              'fl-cmp-a': compareMode && cmpA?.frame_id === snap.frame_id,
              'fl-cmp-b': compareMode && cmpB?.frame_id === snap.frame_id,
            }"
            @click="onFrameClick(snap)"
          >
            <div class="fl-time">{{ fmtTime(snap.period_start_ms) }}</div>
            <div class="fl-meta">
              <span>{{ snap.sweep_count }} 次扫描</span>
              <span>{{ snap.num_points }} 点</span>
              <span v-if="compareMode && cmpA?.frame_id === snap.frame_id" class="tag-a">A</span>
              <span v-if="compareMode && cmpB?.frame_id === snap.frame_id" class="tag-b">B</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: chart -->
      <div class="chart-area card">
        <div v-if="!chartData && !compareMode" class="chart-placeholder">
          <p>点击左侧帧查看频谱</p>
        </div>
        <div v-if="compareMode && (!cmpA || !cmpB)" class="chart-placeholder">
          <p>请选择 A、B 两帧进行对比（点击帧依次选择）</p>
        </div>
        <div class="chart-info" v-if="selectedFrame && !compareMode">
          <span>帧 #{{ selectedFrame.frame_id }}</span>
          <span>{{ fmtTime(selectedFrame.period_start_ms) }} — {{ fmtTime(selectedFrame.period_end_ms) }}</span>
          <span>{{ (selectedFrame.freq_start_hz / 1e6).toFixed(1) }} MHz ~
                {{ ((selectedFrame.freq_start_hz + selectedFrame.freq_step_hz * (selectedFrame.num_points - 1)) / 1e6).toFixed(1) }} MHz</span>
        </div>
        <div class="chart-info" v-if="compareMode && cmpA && cmpB">
          <span class="tag-a">A</span> {{ fmtTime(cmpA.period_start_ms) }}
          &nbsp;vs&nbsp;
          <span class="tag-b">B</span> {{ fmtTime(cmpB.period_start_ms) }}
        </div>
        <div ref="chartEl" class="chart-canvas" v-show="chartData || (compareMode && cmpA && cmpB)"></div>

        <!-- Playback controls -->
        <div class="pb-controls" v-if="!compareMode && snapshots.length > 1">
          <button class="btn btn-sm" @click="stepFrame(-1)" :disabled="currentIndex <= 0">◀ 上一帧</button>
          <button class="btn btn-sm" :class="playing ? 'btn-danger' : 'btn-primary'" @click="togglePlay">
            {{ playing ? '⏹ 停止' : '▶ 播放' }}
          </button>
          <button class="btn btn-sm" @click="stepFrame(1)" :disabled="currentIndex >= snapshots.length - 1">下一帧 ▶</button>
          <label class="speed-label">
            间隔
            <select v-model="playIntervalMs" class="sel-sm">
              <option :value="500">0.5 s</option>
              <option :value="1000">1 s</option>
              <option :value="2000">2 s</option>
              <option :value="5000">5 s</option>
            </select>
          </label>
        </div>
      </div>
    </div>

    <div v-else-if="queried && !loading" class="empty-hint card">
      该时间段内无频谱数据
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getStations, listSnapshots, getSnapshot } from '../api/index.js'

// ── Stations ───────────────────────────────────────────────────────────────

const stations = ref([])
const selectedStation = ref('')

async function fetchStations() {
  try { stations.value = await getStations() } catch { /* ignore */ }
}

onMounted(fetchStations)

// ── Query parameters ───────────────────────────────────────────────────────

function defaultDt(offsetMs = 0) {
  const d = new Date(Date.now() + offsetMs)
  d.setSeconds(0, 0)
  return d.toISOString().slice(0, 16)
}

const startDt = ref(defaultDt(-3600_000))   // 1 hour ago
const endDt   = ref(defaultDt())

const loading = ref(false)
const queried = ref(false)

// ── Snapshots ──────────────────────────────────────────────────────────────

const snapshots = ref([])

async function querySnapshots() {
  if (!selectedStation.value) return
  const startMs = new Date(startDt.value).getTime()
  const endMs   = new Date(endDt.value).getTime()
  if (endMs <= startMs) { alert('结束时间必须晚于开始时间'); return }

  loading.value = true
  queried.value = true
  snapshots.value = []
  selectedFrame.value = null
  chartData.value = null
  resetCompare()

  try {
    const res = await listSnapshots(selectedStation.value, startMs, endMs, 2000)
    snapshots.value = res.snapshots || []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

// ── Frame selection & playback ─────────────────────────────────────────────

const selectedFrame = ref(null)
const chartData     = ref(null)
const compareMode   = ref(false)
const cmpA          = ref(null)
const cmpB          = ref(null)

function resetCompare() {
  cmpA.value = null
  cmpB.value = null
}

watch(compareMode, () => {
  resetCompare()
  selectedFrame.value = null
  chartData.value = null
  renderChart()
})

const currentIndex = computed(() =>
  snapshots.value.findIndex(s => s.frame_id === selectedFrame.value?.frame_id)
)

async function onFrameClick(snap) {
  if (compareMode.value) {
    // Alternate A / B selection
    if (!cmpA.value) {
      cmpA.value = snap
    } else if (!cmpB.value && snap.frame_id !== cmpA.value.frame_id) {
      cmpB.value = snap
      await loadCompare()
    } else {
      // Reset and start over
      cmpA.value = snap
      cmpB.value = null
      chartData.value = null
      renderChart()
    }
  } else {
    await loadFrame(snap)
  }
}

async function loadFrame(snap) {
  if (selectedFrame.value?.frame_id === snap.frame_id) return
  try {
    const detail = await getSnapshot(snap.frame_id)
    selectedFrame.value = detail
    chartData.value = decodeFrame(detail)
    await nextTick()
    renderChart()
  } catch (e) {
    console.error(e)
  }
}

async function loadCompare() {
  try {
    const [fa, fb] = await Promise.all([
      getSnapshot(cmpA.value.frame_id),
      getSnapshot(cmpB.value.frame_id),
    ])
    await nextTick()
    renderCompareChart(fa, fb)
  } catch (e) {
    console.error(e)
  }
}

// ── Auto-play ──────────────────────────────────────────────────────────────

const playing = ref(false)
const playIntervalMs = ref(1000)
let playTimer = null

function togglePlay() {
  if (playing.value) {
    stopPlay()
  } else {
    playing.value = true
    if (currentIndex.value < 0) loadFrame(snapshots.value[0])
    playTimer = setInterval(async () => {
      const next = currentIndex.value + 1
      if (next >= snapshots.value.length) {
        stopPlay()
      } else {
        await loadFrame(snapshots.value[next])
      }
    }, playIntervalMs.value)
  }
}

function stopPlay() {
  playing.value = false
  clearInterval(playTimer)
  playTimer = null
}

async function stepFrame(dir) {
  const idx = currentIndex.value + dir
  if (idx < 0 || idx >= snapshots.value.length) return
  await loadFrame(snapshots.value[idx])
}

onUnmounted(stopPlay)

// ── Decode gzip frame ──────────────────────────────────────────────────────

function decodeFrame(frame) {
  const b64 = frame.levels_dbm_b64
  const binaryStr = atob(b64)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i)
  const ds = new DecompressionStream('gzip')
  const writer = ds.writable.getWriter()
  writer.write(bytes)
  writer.close()
  return { frame, stream: ds.readable }
}

async function resolveStream(streamData) {
  const chunks = []
  const reader = streamData.stream.getReader()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
  }
  const total = chunks.reduce((s, c) => s + c.length, 0)
  const buf = new Uint8Array(total)
  let off = 0
  for (const c of chunks) { buf.set(c, off); off += c.length }
  const floats = new Float32Array(buf.buffer)
  return Array.from(floats)
}

// ── ECharts ────────────────────────────────────────────────────────────────

const chartEl = ref(null)
let chart = null

function getOrCreateChart() {
  if (!chart && chartEl.value) {
    chart = echarts.init(chartEl.value, 'dark')
    window.addEventListener('resize', () => chart?.resize())
  }
  return chart
}

async function renderChart() {
  const c = getOrCreateChart()
  if (!c) return

  if (!chartData.value) {
    c.clear()
    return
  }

  const { frame } = chartData.value
  const levels = await resolveStream(chartData.value)

  const freqMhz = Array.from({ length: levels.length }, (_, i) =>
    ((frame.freq_start_hz + i * frame.freq_step_hz) / 1e6).toFixed(4)
  )

  c.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { top: 30, right: 20, bottom: 40, left: 55 },
    xAxis: {
      type: 'category',
      data: freqMhz,
      axisLabel: { color: '#94a3b8', fontSize: 10, interval: Math.floor(levels.length / 8) },
      axisLine: { lineStyle: { color: '#1e293b' } },
      name: 'MHz',
      nameTextStyle: { color: '#64748b' },
    },
    yAxis: {
      type: 'value',
      name: 'dBm',
      nameTextStyle: { color: '#64748b' },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: '#1e293b' } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f172a',
      borderColor: '#1e293b',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
      formatter: p => `${p[0].name} MHz<br/>${p[0].value.toFixed(1)} dBm`,
    },
    series: [{
      name: '电平',
      type: 'line',
      data: levels,
      showSymbol: false,
      lineStyle: { color: '#38bdf8', width: 1 },
      areaStyle: { color: 'rgba(56,189,248,0.06)' },
    }],
  })
}

async function renderCompareChart(fa, fb) {
  const c = getOrCreateChart()
  if (!c) return

  const [lvA, lvB] = await Promise.all([
    _decodeFrameData(fa),
    _decodeFrameData(fb),
  ])

  const freqMhz = Array.from({ length: lvA.length }, (_, i) =>
    ((fa.freq_start_hz + i * fa.freq_step_hz) / 1e6).toFixed(4)
  )

  c.setOption({
    backgroundColor: 'transparent',
    animation: false,
    legend: {
      data: ['A 帧', 'B 帧'],
      textStyle: { color: '#94a3b8' },
      top: 4,
    },
    grid: { top: 40, right: 20, bottom: 40, left: 55 },
    xAxis: {
      type: 'category',
      data: freqMhz,
      axisLabel: { color: '#94a3b8', fontSize: 10, interval: Math.floor(lvA.length / 8) },
      axisLine: { lineStyle: { color: '#1e293b' } },
      name: 'MHz',
      nameTextStyle: { color: '#64748b' },
    },
    yAxis: {
      type: 'value',
      name: 'dBm',
      nameTextStyle: { color: '#64748b' },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: '#1e293b' } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f172a',
      borderColor: '#1e293b',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
    },
    series: [
      {
        name: 'A 帧',
        type: 'line',
        data: lvA,
        showSymbol: false,
        lineStyle: { color: '#38bdf8', width: 1.5 },
      },
      {
        name: 'B 帧',
        type: 'line',
        data: lvB,
        showSymbol: false,
        lineStyle: { color: '#f59e0b', width: 1.5 },
      },
    ],
  })
}

async function _decodeFrameData(frame) {
  const b64 = frame.levels_dbm_b64
  const binaryStr = atob(b64)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i)
  const ds = new DecompressionStream('gzip')
  const writer = ds.writable.getWriter()
  writer.write(bytes)
  writer.close()
  const chunks = []
  const reader = ds.readable.getReader()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
  }
  const total = chunks.reduce((s, c) => s + c.length, 0)
  const buf = new Uint8Array(total)
  let off = 0
  for (const c of chunks) { buf.set(c, off); off += c.length }
  return Array.from(new Float32Array(buf.buffer))
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtTime(ms) {
  if (!ms) return '--'
  return new Date(ms).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>

<style scoped>
.pb-view { display: flex; flex-direction: column; gap: 18px; }

.pb-header h1 { font-size: 22px; font-weight: 700; color: #f1f5f9; }
.pb-header .page-sub { font-size: 13px; color: #475569; margin-top: 4px; }

.card {
  background: #0a1628;
  border: 1px solid #1e293b;
  border-radius: 10px;
  padding: 18px;
}

/* Query bar */
.query-bar { padding: 14px 18px; }
.qb-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.qb-label { font-size: 12px; color: #64748b; white-space: nowrap; }
.sel, .dt-input {
  background: #0f172a; border: 1px solid #1e293b; border-radius: 6px;
  color: #e2e8f0; padding: 6px 10px; font-size: 13px;
}
.sel { min-width: 140px; }
.dt-input { min-width: 175px; }

.btn {
  padding: 7px 16px; border-radius: 6px; font-size: 13px;
  font-weight: 500; cursor: pointer; border: none;
  transition: opacity .15s;
}
.btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-primary { background: #0ea5e9; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #38bdf8; }
.btn-danger { background: #dc2626; color: #fff; }
.btn-sm { padding: 5px 12px; font-size: 12px; }

/* Body layout */
.pb-body { display: flex; gap: 16px; height: 580px; }

/* Frame list */
.frame-list { width: 230px; flex-shrink: 0; display: flex; flex-direction: column; padding: 0; overflow: hidden; }
.fl-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid #1e293b;
}
.fl-title { font-size: 13px; font-weight: 600; color: #94a3b8; }
.compare-toggle { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #64748b; cursor: pointer; }
.fl-scroll { flex: 1; overflow-y: auto; padding: 6px 0; }
.fl-item {
  padding: 8px 14px; cursor: pointer; border-left: 3px solid transparent;
  transition: background .1s;
}
.fl-item:hover { background: rgba(255,255,255,0.03); }
.fl-active { background: rgba(56,189,248,0.06); border-left-color: #38bdf8; }
.fl-cmp-a { background: rgba(56,189,248,0.06); border-left-color: #38bdf8; }
.fl-cmp-b { background: rgba(245,158,11,0.06); border-left-color: #f59e0b; }
.fl-time { font-size: 12px; color: #e2e8f0; font-variant-numeric: tabular-nums; }
.fl-meta { font-size: 11px; color: #475569; display: flex; gap: 8px; margin-top: 2px; }

.tag-a, .tag-b {
  font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px;
}
.tag-a { background: rgba(56,189,248,0.2); color: #38bdf8; }
.tag-b { background: rgba(245,158,11,0.2); color: #f59e0b; }

/* Chart area */
.chart-area { flex: 1; display: flex; flex-direction: column; gap: 10px; }
.chart-info { display: flex; gap: 12px; font-size: 12px; color: #64748b; }
.chart-canvas { flex: 1; min-height: 0; }
.chart-placeholder { flex: 1; display: flex; align-items: center; justify-content: center; color: #334155; font-size: 14px; }

/* Playback controls */
.pb-controls { display: flex; align-items: center; gap: 8px; padding-top: 6px; border-top: 1px solid #1e293b; }
.speed-label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #64748b; margin-left: auto; }
.sel-sm { background: #0f172a; border: 1px solid #1e293b; border-radius: 4px; color: #e2e8f0; padding: 3px 6px; font-size: 12px; }

.empty-hint { color: #475569; text-align: center; padding: 40px; }
</style>
