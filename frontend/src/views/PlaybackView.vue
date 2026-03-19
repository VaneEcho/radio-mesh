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
import { useTheme } from '../composables/useTheme.js'
import { getStations, listSnapshots, getSnapshot } from '../api/index.js'

const { isDark, chartColors } = useTheme()

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

watch(isDark, async () => {
  if (chart) { chart.dispose(); chart = null }
  await nextTick()
  renderChart()
})

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
  return new Float32Array(buf.buffer)
}

async function _decodeToArrays(frame) {
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
  const levels = new Float32Array(buf.buffer)
  const step   = frame.freq_step_hz / 1e6
  const start  = frame.freq_start_hz / 1e6
  const freqs  = new Float32Array(levels.length)
  for (let i = 0; i < levels.length; i++) freqs[i] = start + i * step
  return { freqs, levels }
}

// ── Max-pool downsampling ──────────────────────────────────────────────────

const TARGET_POINTS = 2000

function maxPoolArrays(freqs, levels, lo, hi, target) {
  const len = hi - lo
  if (len <= target) {
    const out = new Array(len)
    for (let i = 0; i < len; i++) out[i] = [freqs[lo + i], levels[lo + i]]
    return { data: out, raw: true }
  }
  const out = new Array(target)
  const binSize = len / target
  for (let i = 0; i < target; i++) {
    const binLo = Math.floor(i * binSize)
    const binHi = Math.min(Math.floor((i + 1) * binSize), len)
    let maxVal = -Infinity
    for (let j = binLo; j < binHi; j++) {
      if (levels[lo + j] > maxVal) maxVal = levels[lo + j]
    }
    const center = lo + Math.floor((binLo + binHi) / 2)
    out[i] = [freqs[center], maxVal]
  }
  return { data: out, raw: false }
}

// ── ECharts ────────────────────────────────────────────────────────────────

const chartEl = ref(null)
let chart = null
let _pbFreqs  = null   // Float32Array of MHz values for current single frame
let _pbLevels = null   // Float32Array of dBm values

function getOrCreateChart() {
  if (!chart && chartEl.value) {
    chart = echarts.init(chartEl.value, chartColors.value.ecTheme)
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
  const { freqs, levels } = await _decodeToArrays(frame)
  _pbFreqs  = freqs
  _pbLevels = levels

  const { data: overviewData } = maxPoolArrays(freqs, levels, 0, freqs.length, TARGET_POINTS)
  const minFreq = freqs[0]
  const maxFreq = freqs[freqs.length - 1]

  c.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { top: 30, right: 20, bottom: 54, left: 55 },
    xAxis: {
      type: 'value',
      min: minFreq, max: maxFreq,
      name: 'MHz',
      nameTextStyle: { color: chartColors.value.axisLabel, fontSize: 10 },
      axisLabel: { color: chartColors.value.tooltipMuted, fontSize: 10, formatter: v => v.toFixed(0) },
      axisLine: { lineStyle: { color: chartColors.value.axisLine } },
      splitLine: { lineStyle: { color: chartColors.value.splitLine, type: 'dashed' } },
    },
    yAxis: {
      type: 'value',
      name: 'dBm',
      nameTextStyle: { color: chartColors.value.axisLabel },
      axisLabel: { color: chartColors.value.tooltipMuted, fontSize: 11 },
      splitLine: { lineStyle: { color: chartColors.value.splitLine } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: chartColors.value.tooltipBg,
      borderColor: chartColors.value.tooltipBorder,
      textStyle: { color: chartColors.value.tooltipText, fontSize: 11 },
      formatter: ([p]) => `${p.data[0].toFixed(4)} MHz<br/>${p.data[1].toFixed(1)} dBm`,
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      {
        type: 'slider', xAxisIndex: 0, bottom: 6, height: 22,
        fillerColor: chartColors.value.dzFiller,
        borderColor: chartColors.value.axisLine,
        handleStyle: { color: chartColors.value.accent },
        textStyle: { color: chartColors.value.axisLabel, fontSize: 10 },
      },
    ],
    series: [{
      name: '电平',
      type: 'line',
      data: overviewData,
      sampling: null,
      symbol: 'none',
      lineStyle: { color: chartColors.value.accent, width: 1 },
      areaStyle: { color: chartColors.value.accentFill[0] },
    }],
  }, true)

  c.off('datazoom')
  c.on('datazoom', (e) => {
    if (!_pbFreqs) return
    const ev = e.batch?.[0] ?? e
    const startMHz = ev.startValue
    const endMHz   = ev.endValue
    if (startMHz == null || endMHz == null) return

    const span = _pbFreqs[_pbFreqs.length - 1] - _pbFreqs[0]
    if (span <= 0) return
    const step = span / (_pbFreqs.length - 1)
    const lo = Math.max(0, Math.floor((startMHz - _pbFreqs[0]) / step))
    const hi = Math.min(_pbFreqs.length, Math.ceil((endMHz - _pbFreqs[0]) / step) + 1)
    const { data } = maxPoolArrays(_pbFreqs, _pbLevels, lo, hi, TARGET_POINTS)
    c.setOption({ series: [{ data }] })
  })
}

async function renderCompareChart(fa, fb) {
  const c = getOrCreateChart()
  if (!c) return

  const [arrA, arrB] = await Promise.all([
    _decodeToArrays(fa),
    _decodeToArrays(fb),
  ])

  const { data: dataA } = maxPoolArrays(arrA.freqs, arrA.levels, 0, arrA.freqs.length, TARGET_POINTS)
  const { data: dataB } = maxPoolArrays(arrB.freqs, arrB.levels, 0, arrB.freqs.length, TARGET_POINTS)
  const minFreq = Math.min(arrA.freqs[0], arrB.freqs[0])
  const maxFreq = Math.max(arrA.freqs[arrA.freqs.length - 1], arrB.freqs[arrB.freqs.length - 1])

  c.off('datazoom')
  c.setOption({
    backgroundColor: 'transparent',
    animation: false,
    legend: {
      data: ['A 帧', 'B 帧'],
      textStyle: { color: chartColors.value.tooltipMuted },
      top: 4,
    },
    grid: { top: 40, right: 20, bottom: 54, left: 55 },
    xAxis: {
      type: 'value',
      min: minFreq, max: maxFreq,
      name: 'MHz',
      nameTextStyle: { color: chartColors.value.axisLabel, fontSize: 10 },
      axisLabel: { color: chartColors.value.tooltipMuted, fontSize: 10, formatter: v => v.toFixed(0) },
      axisLine: { lineStyle: { color: chartColors.value.axisLine } },
      splitLine: { lineStyle: { color: chartColors.value.splitLine, type: 'dashed' } },
    },
    yAxis: {
      type: 'value',
      name: 'dBm',
      nameTextStyle: { color: chartColors.value.axisLabel },
      axisLabel: { color: chartColors.value.tooltipMuted, fontSize: 11 },
      splitLine: { lineStyle: { color: chartColors.value.splitLine } },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: chartColors.value.tooltipBg,
      borderColor: chartColors.value.tooltipBorder,
      textStyle: { color: chartColors.value.tooltipText, fontSize: 11 },
      formatter: (params) => params.map(p => `${p.seriesName}: ${p.data[1].toFixed(1)} dBm`).join('<br/>'),
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      {
        type: 'slider', xAxisIndex: 0, bottom: 6, height: 22,
        fillerColor: chartColors.value.dzFiller,
        borderColor: chartColors.value.axisLine,
        handleStyle: { color: chartColors.value.accent },
        textStyle: { color: chartColors.value.axisLabel, fontSize: 10 },
      },
    ],
    series: [
      {
        name: 'A 帧',
        type: 'line',
        data: dataA,
        sampling: null,
        symbol: 'none',
        lineStyle: { color: chartColors.value.accent, width: 1.5 },
      },
      {
        name: 'B 帧',
        type: 'line',
        data: dataB,
        sampling: null,
        symbol: 'none',
        lineStyle: { color: '#f59e0b', width: 1.5 },
      },
    ],
  }, true)
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
.pb-view { display: flex; flex-direction: column; gap: 18px; transition: background 0.2s, border-color 0.2s, color 0.2s; }

.pb-header h1 { font-size: 22px; font-weight: 700; color: var(--c-text); }
.pb-header .page-sub { font-size: 13px; color: var(--c-text-faint); margin-top: 4px; }

.card {
  background: var(--c-card-2);
  border: 1px solid var(--c-border);
  border-radius: 10px;
  padding: 18px;
}

/* Query bar */
.query-bar { padding: 14px 18px; }
.qb-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.qb-label { font-size: 12px; color: var(--c-text-dim); white-space: nowrap; }
.sel, .dt-input {
  background: var(--c-raised); border: 1px solid var(--c-border); border-radius: 6px;
  color: var(--c-text-2); padding: 6px 10px; font-size: 13px;
}
.sel { min-width: 140px; }
.dt-input { min-width: 175px; }

.btn {
  padding: 7px 16px; border-radius: 6px; font-size: 13px;
  font-weight: 500; cursor: pointer; border: none;
  transition: opacity .15s;
}
.btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-primary { background: var(--c-accent); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--c-accent); opacity: .9; }
.btn-danger { background: var(--c-red); color: #fff; }
.btn-sm { padding: 5px 12px; font-size: 12px; }

/* Body layout */
.pb-body { display: flex; gap: 16px; height: 580px; }

/* Frame list */
.frame-list { width: 230px; flex-shrink: 0; display: flex; flex-direction: column; padding: 0; overflow: hidden; }
.fl-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--c-border);
}
.fl-title { font-size: 13px; font-weight: 600; color: var(--c-text-muted); }
.compare-toggle { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--c-text-dim); cursor: pointer; }
.fl-scroll { flex: 1; overflow-y: auto; padding: 6px 0; }
.fl-item {
  padding: 8px 14px; cursor: pointer; border-left: 3px solid transparent;
  transition: background .1s;
}
.fl-item:hover { background: rgba(255,255,255,0.03); }
.fl-active { background: var(--c-accent-bg); border-left-color: var(--c-accent); }
.fl-cmp-a { background: var(--c-accent-bg); border-left-color: var(--c-accent); }
.fl-cmp-b { background: var(--c-gold-bg); border-left-color: var(--c-gold); }
.fl-time { font-size: 12px; color: var(--c-text-2); font-variant-numeric: tabular-nums; }
.fl-meta { font-size: 11px; color: var(--c-text-faint); display: flex; gap: 8px; margin-top: 2px; }

.tag-a, .tag-b {
  font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px;
}
.tag-a { background: var(--c-accent-bgh); color: var(--c-accent); }
.tag-b { background: var(--c-gold-bg); color: var(--c-gold); }

/* Chart area */
.chart-area { flex: 1; display: flex; flex-direction: column; gap: 10px; }
.chart-info { display: flex; gap: 12px; font-size: 12px; color: var(--c-text-dim); }
.chart-canvas { flex: 1; min-height: 0; }
.chart-placeholder { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--c-text-ghost); font-size: 14px; }

/* Playback controls */
.pb-controls { display: flex; align-items: center; gap: 8px; padding-top: 6px; border-top: 1px solid var(--c-border); }
.speed-label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--c-text-dim); margin-left: auto; }
.sel-sm { background: var(--c-raised); border: 1px solid var(--c-border); border-radius: 4px; color: var(--c-text-2); padding: 3px 6px; font-size: 12px; }

.empty-hint { color: var(--c-text-faint); text-align: center; padding: 40px; }
</style>
