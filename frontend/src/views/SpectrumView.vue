<template>
  <div class="spectrum-page">
    <!-- ── Breadcrumb ── -->
    <div class="breadcrumb mb20">
      <router-link to="/" class="bc-link">站点总览</router-link>
      <span class="bc-sep">/</span>
      <span class="bc-cur">{{ stationId }}</span>
    </div>

    <!-- ── Page header ── -->
    <div class="page-header mb24">
      <div>
        <h2 class="page-title">频谱分析</h2>
        <p class="page-sub">{{ stationId }} · {{ frames.length > 0 ? frames.length + ' 帧' : '暂无数据' }}</p>
      </div>
      <div class="header-badges" v-if="currentFrame">
        <span class="badge badge-freq">
          {{ (currentFrame.freq_start_hz / 1e6).toFixed(1) }} – {{ endFreqMHz(currentFrame).toFixed(1) }} MHz
        </span>
        <span class="badge badge-pts">{{ currentFrame.num_points.toLocaleString() }} 点</span>
        <span class="badge badge-sweep">合并 {{ currentFrame.sweep_count }} 次扫描</span>
      </div>
    </div>

    <!-- ── Query bar ── -->
    <div class="query-bar mb20">
      <div class="query-presets">
        <button
          v-for="p in PRESETS"
          :key="p.value"
          class="preset-btn"
          :class="{ active: preset === p.value }"
          @click="preset = p.value; applyPreset()"
        >{{ p.label }}</button>
      </div>
      <div v-if="preset === 'custom'" class="custom-range">
        <el-date-picker v-model="customStart" type="datetime" style="width:180px"
          value-format="x" placeholder="开始时间" size="small" />
        <span class="range-to">→</span>
        <el-date-picker v-model="customEnd" type="datetime" style="width:180px"
          value-format="x" placeholder="结束时间" size="small" />
        <el-button type="primary" size="small" :loading="loading" @click="query">查询</el-button>
      </div>
      <div class="query-status" v-if="loading">
        <span class="spinner" />加载中…
      </div>
    </div>

    <!-- ── Error ── -->
    <div v-if="error" class="error-bar mb20">
      <span>⚠ {{ error }}</span>
      <button @click="error = ''" class="error-close">×</button>
    </div>

    <!-- ── No data ── -->
    <div v-if="!loading && frames.length === 0 && queried && !error" class="empty-state">
      <div class="empty-icon">📡</div>
      <div class="empty-text">该时间段内暂无频谱数据</div>
    </div>

    <!-- ── Main chart ── -->
    <div v-if="currentFrame" class="chart-card mb16">
      <div class="chart-topbar">
        <div class="chart-title">
          <span class="chart-time">{{ fmtTime(currentFrame.period_start_ms) }}</span>
          <span v-if="isShowingRaw" class="zoom-badge">🔍 原始分辨率</span>
        </div>
        <div class="chart-actions">
          <button v-if="isZoomed" class="action-btn" @click="resetZoom">重置缩放</button>
        </div>
      </div>
      <div ref="chartEl" class="chart-area" />
    </div>

    <!-- ── Frame timeline ── -->
    <div v-if="frames.length > 1" class="tl-card">
      <div class="tl-header">帧时间线 <span class="tl-count">共 {{ frames.length }} 帧</span></div>
      <div class="timeline">
        <div
          v-for="(f, i) in frames"
          :key="f.frame_id"
          class="tl-item"
          :class="{ active: i === frameIdx }"
          @click="selectFrame(i)"
        >
          <div class="tl-time">{{ fmtTimeShort(f.period_start_ms) }}</div>
          <div class="tl-sweeps">{{ f.sweep_count }}次</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import pako from 'pako'
import { querySpectrum } from '../api/index.js'
import { useTheme } from '../composables/useTheme.js'

const route = useRoute()
const stationId = route.params.stationId
const { isDark, chartColors } = useTheme()

const PRESETS = [
  { label: '1 小时', value: '1h' },
  { label: '6 小时', value: '6h' },
  { label: '24 小时', value: '24h' },
  { label: '自定义', value: 'custom' },
]

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
const isShowingRaw = ref(false)
const isZoomed     = ref(false)

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
    frameIdx.value = frames.value.length - 1
    queried.value = true
    currentFrame.value = frames.value.length ? frames.value[frameIdx.value] : null
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

// ── Max-pool downsampling ─────────────────────────────────────────────────────
// For spectrograms, max-pooling is critical: merging N points into 1 takes the
// maximum so narrow signal peaks are never lost in the overview.

const TARGET_POINTS = 2000

function maxPool(freqs, levels, target) {
  const n = freqs.length
  if (n <= target) {
    const out = new Array(n)
    for (let i = 0; i < n; i++) out[i] = [freqs[i], levels[i]]
    return out
  }
  const out = new Array(target)
  const binSize = n / target
  for (let i = 0; i < target; i++) {
    const lo = Math.floor(i * binSize)
    const hi = Math.min(Math.floor((i + 1) * binSize), n)
    let maxVal = -Infinity
    for (let j = lo; j < hi; j++) {
      if (levels[j] > maxVal) maxVal = levels[j]
    }
    // Use center frequency of the bin
    const centerIdx = Math.floor((lo + hi) / 2)
    out[i] = [freqs[centerIdx], maxVal]
  }
  return out
}

/** Build [freq, level] pairs for ECharts from a slice of the full arrays */
function buildData(freqs, levels, startIdx, endIdx, target) {
  const len = endIdx - startIdx
  if (len <= target) {
    const out = new Array(len)
    for (let i = 0; i < len; i++) out[i] = [freqs[startIdx + i], levels[startIdx + i]]
    return { data: out, raw: true }
  }
  const slice = { freqs: { length: len, at: (i) => freqs[startIdx + i] }, levels: { length: len, at: (i) => levels[startIdx + i] } }
  // use maxPool on slice
  const target2 = target
  const binSize = len / target2
  const out = new Array(target2)
  for (let i = 0; i < target2; i++) {
    const lo = Math.floor(i * binSize)
    const hi = Math.min(Math.floor((i + 1) * binSize), len)
    let maxVal = -Infinity
    for (let j = lo; j < hi; j++) {
      const v = levels[startIdx + j]
      if (v > maxVal) maxVal = v
    }
    const centerIdx = startIdx + Math.floor((lo + hi) / 2)
    out[i] = [freqs[centerIdx], maxVal]
  }
  return { data: out, raw: false }
}

// ── Spectrum decoding ─────────────────────────────────────────────────────────

function decodeFrame(frame) {
  const binary = atob(frame.levels_dbm_b64)
  const bytes  = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const raw    = pako.inflate(bytes)
  const levels = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4)
  const freqs  = new Float64Array(levels.length)
  const start  = frame.freq_start_hz / 1e6
  const step   = frame.freq_step_hz  / 1e6
  for (let i = 0; i < levels.length; i++) freqs[i] = start + i * step
  return { freqs, levels }
}

// ── ECharts ──────────────────────────────────────────────────────────────────

function buildChart() {
  if (!chartEl.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartEl.value, chartColors.value.ecTheme)
  window.__rfmeshChart = chart
}

let _fullFreqs  = null
let _fullLevels = null

function resetZoom() {
  if (!chart) return
  chart.dispatchAction({ type: 'dataZoom', start: 0, end: 100 })
}

function renderFrame(frame) {
  if (!chart) return
  const { freqs, levels } = decodeFrame(frame)
  _fullFreqs  = freqs
  _fullLevels = levels

  const overviewData = maxPool(freqs, levels, TARGET_POINTS)
  const minFreq = freqs[0]
  const maxFreq = freqs[freqs.length - 1]

  isShowingRaw.value = false
  isZoomed.value = false

  chart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 64, right: 24, top: 16, bottom: 54 },
    tooltip: {
      trigger: 'axis',
      formatter: ([p]) => `<span style="color:#94a3b8;font-size:11px">${p.data[0].toFixed(4)} MHz</span><br/><b style="color:#e2e8f0;font-size:13px">${p.data[1].toFixed(1)} dBm</b>`,
      backgroundColor: chartColors.value.tooltipBg,
      borderColor: chartColors.value.tooltipBorder,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: chartColors.value.tooltipText, fontSize: 12 },
    },
    xAxis: {
      type: 'value',
      name: 'MHz',
      nameLocation: 'end',
      nameTextStyle: { color: chartColors.value.axisLabel, fontSize: 11 },
      min: minFreq,
      max: maxFreq,
      axisLabel: { color: chartColors.value.axisLabel, fontSize: 11, formatter: v => v.toFixed(0) },
      axisLine: { lineStyle: { color: chartColors.value.axisLine } },
      splitLine: { lineStyle: { color: chartColors.value.splitLine, type: 'dashed' } },
    },
    yAxis: {
      type: 'value',
      name: 'dBm',
      nameLocation: 'end',
      nameTextStyle: { color: chartColors.value.axisLabel, fontSize: 11 },
      axisLabel: { color: chartColors.value.axisLabel, fontSize: 11 },
      axisLine: { lineStyle: { color: chartColors.value.axisLine } },
      splitLine: { lineStyle: { color: chartColors.value.splitLine, type: 'dashed' } },
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      {
        type: 'slider', xAxisIndex: 0, bottom: 6, height: 28,
        fillerColor: chartColors.value.dzFiller,
        borderColor: chartColors.value.axisLine,
        handleStyle: { color: chartColors.value.accent, borderColor: chartColors.value.accent },
        moveHandleStyle: { color: chartColors.value.accent },
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
      data: overviewData,
      sampling: null,     // we do our own max-pool, don't let ECharts subsample further
      symbol: 'none',
      lineStyle: { color: chartColors.value.accent, width: 1.5 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: chartColors.value.accentFill[0] },
          { offset: 0.7, color: chartColors.value.accentFill[1] },
          { offset: 1, color: chartColors.value.accentFill[2] },
        ]),
      },
    }],
  }, true)

  // On zoom: slice full data and apply max-pool → gives "original resolution" in view
  chart.off('datazoom')
  chart.on('datazoom', (e) => {
    const ev = e.batch?.[0] ?? e
    if (!_fullFreqs) return
    let startMHz = ev.startValue
    let endMHz   = ev.endValue
    // inside-type dataZoom emits {start, end} percentages, not startValue/endValue.
    // Convert percentages to MHz when absolute values are absent.
    if (startMHz == null || endMHz == null) {
      const minF = _fullFreqs[0]
      const maxF = _fullFreqs[_fullFreqs.length - 1]
      startMHz = minF + (maxF - minF) * (ev.start ?? 0)   / 100
      endMHz   = minF + (maxF - minF) * (ev.end   ?? 100) / 100
    }
    if (startMHz == null || endMHz == null) return

    const span     = _fullFreqs[_fullFreqs.length - 1] - _fullFreqs[0]
    const startPct = (startMHz - _fullFreqs[0]) / span * 100
    const endPct   = (endMHz   - _fullFreqs[0]) / span * 100

    isZoomed.value = startPct > 0.5 || endPct < 99.5

    if (!isZoomed.value) {
      // Zoomed back out → restore overview max-pool
      isShowingRaw.value = false
      chart.setOption({ series: [{ data: overviewData }] })
      return
    }

    // Find index range in full arrays using actual frequency values
    const step = span / (_fullFreqs.length - 1)
    const lo = Math.max(0,              Math.floor((startMHz - _fullFreqs[0]) / step))
    const hi = Math.min(_fullFreqs.length, Math.ceil((endMHz   - _fullFreqs[0]) / step) + 1)

    const { data, raw } = buildData(_fullFreqs, _fullLevels, lo, hi, TARGET_POINTS)
    isShowingRaw.value = raw
    chart.setOption({ series: [{ data }] })
  })
}

watch(currentFrame, async (frame) => {
  if (!frame) return
  await nextTick()
  if (!chart) buildChart()
  renderFrame(frame)
})

watch(isDark, async () => {
  if (!chart || !currentFrame.value) return
  await nextTick()
  buildChart()
  renderFrame(currentFrame.value)
})

function onResize() { chart?.resize() }

onMounted(() => {
  window.addEventListener('resize', onResize)
  query()
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})
</script>

<style scoped>
.spectrum-page { padding-bottom: 32px; }
.mb16 { margin-bottom: 16px; }
.mb20 { margin-bottom: 20px; }
.mb24 { margin-bottom: 24px; }

/* ── Breadcrumb ── */
.breadcrumb { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.bc-link { color: var(--c-accent); text-decoration: none; }
.bc-link:hover { text-decoration: underline; }
.bc-sep { color: var(--c-border-str); }
.bc-cur { color: var(--c-text-dim); }

/* ── Page header ── */
.page-header { display: flex; justify-content: space-between; align-items: flex-start; }
.page-title  { font-size: 24px; font-weight: 700; color: var(--c-text); letter-spacing: -0.3px; }
.page-sub    { font-size: 13px; color: var(--c-text-dim); margin-top: 3px; }

.header-badges { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 4px; }
.badge {
  font-size: 11px; font-weight: 500; padding: 3px 10px; border-radius: 20px;
  border: 1px solid; white-space: nowrap;
}
.badge-freq  { background: var(--c-accent-bgx); border-color: var(--c-accent-bds); color: var(--c-accent); }
.badge-pts   { background: var(--c-indigo-bg); border-color: var(--c-indigo-bd); color: var(--c-indigo); }
.badge-sweep { background: var(--c-green-bg); border-color: var(--c-green-bd); color: var(--c-green); }

/* ── Query bar ── */
.query-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  background: var(--c-raised);
  border: 1px solid var(--c-border);
  border-radius: 12px;
  padding: 12px 16px;
}
.query-presets { display: flex; gap: 6px; }
.preset-btn {
  padding: 5px 14px;
  border-radius: 8px;
  border: 1px solid var(--c-border);
  background: transparent;
  color: var(--c-text-dim);
  font-size: 13px;
  cursor: pointer;
  transition: all .15s;
}
.preset-btn:hover  { border-color: var(--c-border-str); color: var(--c-text-muted); }
.preset-btn.active { background: var(--c-accent-bgh); border-color: var(--c-accent); color: var(--c-accent); }

.custom-range { display: flex; align-items: center; gap: 10px; }
.range-to { color: var(--c-border-str); }

.query-status { display: flex; align-items: center; gap: 8px; color: var(--c-text-dim); font-size: 13px; }
.spinner {
  display: inline-block;
  width: 14px; height: 14px;
  border: 2px solid var(--c-border);
  border-top-color: var(--c-accent);
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Error ── */
.error-bar {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--c-red-bg); border: 1px solid var(--c-red-bd);
  border-radius: 10px; padding: 10px 16px; color: var(--c-red); font-size: 13px;
}
.error-close { background: none; border: none; color: var(--c-red); font-size: 18px; cursor: pointer; }

/* ── Empty ── */
.empty-state { text-align: center; padding: 80px 0; }
.empty-icon  { font-size: 48px; margin-bottom: 12px; opacity: .4; }
.empty-text  { color: var(--c-text-faint); font-size: 14px; }

/* ── Chart card ── */
.chart-card {
  background: var(--c-card-2);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  overflow: hidden;
}
.chart-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px 12px;
  border-bottom: 1px solid var(--c-border);
}
.chart-title { display: flex; align-items: center; gap: 10px; }
.chart-time  { font-size: 13px; color: var(--c-text-muted); font-weight: 500; }
.zoom-badge  {
  font-size: 11px; padding: 2px 8px; border-radius: 6px;
  background: var(--c-gold-bg); border: 1px solid var(--c-gold-bd); color: var(--c-gold);
}
.chart-actions { display: flex; gap: 8px; }
.action-btn {
  padding: 4px 12px; border-radius: 7px;
  border: 1px solid var(--c-border-str); background: transparent; color: var(--c-text-dim);
  font-size: 12px; cursor: pointer; transition: all .15s;
}
.action-btn:hover { border-color: var(--c-accent); color: var(--c-accent); }

.chart-area { width: 100%; height: 460px; }

/* ── Timeline ── */
.tl-card {
  background: var(--c-card-2);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 16px 20px;
}
.tl-header {
  font-size: 13px; color: var(--c-text-dim); margin-bottom: 12px; font-weight: 500;
}
.tl-count { color: var(--c-border-str); font-weight: 400; }

.timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 130px;
  overflow-y: auto;
}
.tl-item {
  padding: 5px 10px;
  border-radius: 8px;
  background: var(--c-raised);
  border: 1px solid var(--c-border);
  cursor: pointer;
  transition: all .15s;
  text-align: center;
  min-width: 64px;
}
.tl-item:hover { border-color: var(--c-border-str); }
.tl-item.active { background: var(--c-accent-bgx); border-color: var(--c-accent-bd); }

.tl-time   { font-size: 11px; color: var(--c-text-dim); }
.tl-sweeps { font-size: 10px; color: var(--c-text-faint); margin-top: 1px; }
.tl-item.active .tl-time { color: var(--c-accent); }
</style>
