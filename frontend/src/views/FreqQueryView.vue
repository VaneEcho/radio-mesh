<template>
  <div class="freqquery-page">
    <!-- ── Header ── -->
    <div class="page-header mb24">
      <div>
        <h2 class="page-title">频点查询</h2>
        <p class="page-sub">输入频点，查看所有站点在该频率上的历史电平</p>
      </div>
    </div>

    <!-- ── Search bar ── -->
    <div class="search-bar mb24">
      <div class="freq-input-wrap">
        <input
          v-model="freqInput"
          class="freq-input"
          type="number"
          step="0.001"
          placeholder="频率 (MHz)"
          @keydown.enter="query"
        />
        <span class="freq-unit">MHz</span>
      </div>
      <div class="time-presets">
        <button
          v-for="p in PRESETS"
          :key="p.value"
          class="preset-btn"
          :class="{ active: preset === p.value }"
          @click="preset = p.value; if (preset !== 'custom') query()"
        >{{ p.label }}</button>
      </div>
      <div v-if="preset === 'custom'" class="custom-range">
        <el-date-picker v-model="customStart" type="datetime" style="width:170px"
          value-format="x" placeholder="开始" size="small" />
        <span style="color:#334155">→</span>
        <el-date-picker v-model="customEnd" type="datetime" style="width:170px"
          value-format="x" placeholder="结束" size="small" />
      </div>
      <button class="query-btn" :disabled="loading" @click="query">
        <span v-if="loading" class="spinner" />
        <span v-else>查询</span>
      </button>
    </div>

    <!-- ── Error ── -->
    <div v-if="error" class="error-bar mb20">⚠ {{ error }}</div>

    <!-- ── Empty ── -->
    <div v-if="queried && !loading && result && result.stations.length === 0" class="empty-state">
      <div class="empty-icon">📡</div>
      <div class="empty-text">该频点在所选时间段内无数据</div>
      <div class="empty-hint">{{ fmtFreq(result.freq_hz) }} · {{ fmtMs(result.start_ms) }} – {{ fmtMs(result.end_ms) }}</div>
    </div>

    <!-- ── Results ── -->
    <template v-if="result && result.stations.length > 0">
      <!-- Summary chips -->
      <div class="result-meta mb20">
        <span class="meta-chip chip-freq">{{ fmtFreq(result.freq_hz) }}</span>
        <span class="meta-chip chip-range">{{ fmtMs(result.start_ms) }} – {{ fmtMs(result.end_ms) }}</span>
        <span class="meta-chip chip-stations">{{ result.stations.length }} 个站点有数据</span>
      </div>

      <!-- Station ranking table -->
      <div class="table-card mb20">
        <div class="table-header">
          <span>站点排名 <span class="sub">按最大电平降序</span></span>
        </div>
        <table class="rank-table">
          <thead>
            <tr>
              <th>#</th>
              <th>站点</th>
              <th>最大电平</th>
              <th>中位电平</th>
              <th>帧数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(s, i) in result.stations"
              :key="s.station_id"
              class="rank-row"
              :class="{ selected: selectedStation === s.station_id }"
              @click="selectStation(s)"
            >
              <td class="cell-rank">
                <span class="rank-badge" :class="rankClass(i)">{{ i + 1 }}</span>
              </td>
              <td class="cell-station">
                <div class="stn-id">{{ s.station_id }}</div>
                <div class="stn-name" v-if="s.name">{{ s.name }}</div>
              </td>
              <td class="cell-dbm" :style="dbmStyle(s.max_dbm)">
                {{ s.max_dbm.toFixed(1) }} dBm
              </td>
              <td class="cell-dbm-med">{{ s.median_dbm.toFixed(1) }} dBm</td>
              <td class="cell-frames">{{ s.frame_count }}</td>
              <td class="cell-action">
                <button class="select-btn" :class="{ active: selectedStation === s.station_id }"
                  @click.stop="selectStation(s)">
                  {{ selectedStation === s.station_id ? '▲ 收起' : '▼ 展开' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Time-axis chart for selected station -->
      <div v-if="activeStation" class="chart-card">
        <div class="chart-topbar">
          <div class="chart-title">
            {{ activeStation.station_id }}
            <span v-if="activeStation.name" class="chart-sname">— {{ activeStation.name }}</span>
            <span v-if="isShowingRaw" class="zoom-badge">🔍 原始分辨率</span>
          </div>
          <div class="chart-actions">
            <span class="chart-meta">{{ fmtFreq(result.freq_hz) }} · {{ activeStation.frame_count }} 帧</span>
            <button v-if="isZoomed" class="action-btn" @click="resetZoom">重置缩放</button>
          </div>
        </div>
        <div ref="chartEl" class="chart-area" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { queryFreqTimeseries } from '../api/index.js'

const PRESETS = [
  { label: '1 小时', value: '1h' },
  { label: '6 小时', value: '6h' },
  { label: '24 小时', value: '24h' },
  { label: '7 天',   value: '7d' },
  { label: '自定义', value: 'custom' },
]

const freqInput   = ref('')
const preset      = ref('24h')
const customStart = ref(null)
const customEnd   = ref(null)
const loading     = ref(false)
const error       = ref('')
const queried     = ref(false)
const result      = ref(null)
const selectedStation = ref(null)
const activeStation   = ref(null)
const chartEl     = ref(null)
const isShowingRaw = ref(false)
const isZoomed     = ref(false)

let chart = null

// ── Time helpers ──────────────────────────────────────────────────────────────

function timeRange() {
  const end = Date.now()
  const map = { '1h': 3_600_000, '6h': 21_600_000, '24h': 86_400_000, '7d': 604_800_000 }
  if (preset.value in map) return [end - map[preset.value], end]
  return [Number(customStart.value), Number(customEnd.value)]
}

function fmtFreq(hz) {
  return (hz / 1e6).toFixed(4) + ' MHz'
}
function fmtMs(ms) {
  return new Date(ms).toLocaleString('zh-CN', { hour12: false })
}

// ── Query ─────────────────────────────────────────────────────────────────────

async function query() {
  const mhz = parseFloat(freqInput.value)
  if (isNaN(mhz) || mhz <= 0) {
    error.value = '请输入有效的频率（MHz）'
    return
  }

  loading.value = true
  error.value = ''
  try {
    const [start, end] = timeRange()
    result.value = await queryFreqTimeseries(mhz * 1e6, start, end)
    queried.value = true
    selectedStation.value = null
    activeStation.value = null
  } catch (e) {
    error.value = '查询失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

// ── Station selection ─────────────────────────────────────────────────────────

function selectStation(s) {
  if (selectedStation.value === s.station_id) {
    selectedStation.value = null
    activeStation.value = null
  } else {
    selectedStation.value = s.station_id
    activeStation.value = s
  }
}

// ── Max-pool downsampling ─────────────────────────────────────────────────────

const TARGET_PTS = 500   // time axis has fewer frames, 500 is plenty

function maxPool(series, target) {
  const n = series.length
  if (n <= target) return series
  const out = []
  const binSize = n / target
  for (let i = 0; i < target; i++) {
    const lo = Math.floor(i * binSize)
    const hi = Math.min(Math.floor((i + 1) * binSize), n)
    let maxDbm = -Infinity
    let maxT = series[lo].t
    for (let j = lo; j < hi; j++) {
      if (series[j].dbm > maxDbm) { maxDbm = series[j].dbm; maxT = series[j].t }
    }
    out.push([maxT, maxDbm])
  }
  return out
}

function buildSeriesData(series, loIdx, hiIdx, target) {
  const len = hiIdx - loIdx
  if (len <= target) {
    const out = new Array(len)
    for (let i = 0; i < len; i++) out[i] = [series[loIdx + i].t, series[loIdx + i].dbm]
    return { data: out, raw: true }
  }
  const binSize = len / target
  const out = []
  for (let i = 0; i < target; i++) {
    const lo = loIdx + Math.floor(i * binSize)
    const hi = loIdx + Math.min(Math.floor((i + 1) * binSize), len)
    let maxDbm = -Infinity
    let maxT = series[lo].t
    for (let j = lo; j < hi; j++) {
      if (series[j].dbm > maxDbm) { maxDbm = series[j].dbm; maxT = series[j].t }
    }
    out.push([maxT, maxDbm])
  }
  return { data: out, raw: false }
}

// ── Chart ─────────────────────────────────────────────────────────────────────

function buildChart() {
  if (!chartEl.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartEl.value, 'dark')
}

function resetZoom() {
  chart?.dispatchAction({ type: 'dataZoom', start: 0, end: 100 })
}

function renderStationChart(s) {
  if (!chart) return
  const series = s.series    // [{t, dbm}, ...]
  const overviewData = maxPool(series, TARGET_PTS)

  isShowingRaw.value = false
  isZoomed.value = false

  chart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 64, right: 24, top: 16, bottom: 54 },
    tooltip: {
      trigger: 'axis',
      formatter: ([p]) => {
        const d = new Date(p.data[0])
        const ts = d.toLocaleString('zh-CN', { hour12: false })
        return `<span style="color:#94a3b8;font-size:11px">${ts}</span><br/><b style="color:#e2e8f0;font-size:13px">${p.data[1].toFixed(1)} dBm</b>`
      },
      backgroundColor: '#0f172a',
      borderColor: '#334155',
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: '#e2e8f0', fontSize: 12 },
    },
    xAxis: {
      type: 'time',
      axisLabel: {
        color: '#64748b', fontSize: 11,
        formatter: (v) => {
          const d = new Date(v)
          return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
        },
      },
      axisLine: { lineStyle: { color: '#1e293b' } },
      splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
    },
    yAxis: {
      type: 'value',
      name: 'dBm',
      nameLocation: 'end',
      nameTextStyle: { color: '#64748b', fontSize: 11 },
      axisLabel: { color: '#64748b', fontSize: 11 },
      axisLine: { lineStyle: { color: '#1e293b' } },
      splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      {
        type: 'slider', xAxisIndex: 0, bottom: 6, height: 28,
        fillerColor: 'rgba(56,189,248,0.08)',
        borderColor: '#1e293b',
        handleStyle: { color: '#38bdf8', borderColor: '#38bdf8' },
        textStyle: { color: '#64748b', fontSize: 10 },
        selectedDataBackground: {
          lineStyle: { color: '#38bdf8', width: 1 },
          areaStyle: { color: 'rgba(56,189,248,0.06)' },
        },
        dataBackground: {
          lineStyle: { color: '#334155', width: 1 },
          areaStyle: { color: 'rgba(51,65,85,0.3)' },
        },
      },
    ],
    series: [{
      type: 'line',
      data: overviewData,
      sampling: null,
      smooth: false,
      symbol: 'none',
      lineStyle: { color: '#38bdf8', width: 1.5 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(56,189,248,0.25)' },
          { offset: 0.7, color: 'rgba(56,189,248,0.04)' },
          { offset: 1, color: 'rgba(56,189,248,0)' },
        ]),
      },
    }],
  }, true)

  chart.off('datazoom')
  chart.on('datazoom', () => {
    const opt = chart.getOption()
    const dz  = opt.dataZoom[0]
    const startPct = dz.start ?? 0
    const endPct   = dz.end   ?? 100

    isZoomed.value = startPct > 0.5 || endPct < 99.5

    if (!isZoomed.value) {
      isShowingRaw.value = false
      chart.setOption({ series: [{ data: overviewData, smooth: false }] })
      return
    }

    const total = series.length
    const lo = Math.max(0,     Math.floor(startPct / 100 * total))
    const hi = Math.min(total, Math.ceil(endPct   / 100 * total))

    const { data, raw } = buildSeriesData(series, lo, hi, TARGET_PTS)
    isShowingRaw.value = raw
    // Smooth when zoomed in far enough to show individual points
    chart.setOption({ series: [{ data, smooth: raw }] })
  })
}

watch(activeStation, async (s) => {
  if (!s) return
  await nextTick()
  if (!chart) buildChart()
  renderStationChart(s)
})

function onResize() { chart?.resize() }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})

// ── UI helpers ────────────────────────────────────────────────────────────────

function rankClass(i) {
  if (i === 0) return 'gold'
  if (i === 1) return 'silver'
  if (i === 2) return 'bronze'
  return ''
}

function dbmStyle(dbm) {
  // Map dBm range [-120, -20] to a color from dim to bright
  const t = Math.max(0, Math.min(1, (dbm + 120) / 100))
  if (t > 0.7) return { color: '#f87171' }
  if (t > 0.4) return { color: '#fb923c' }
  if (t > 0.2) return { color: '#38bdf8' }
  return { color: '#475569' }
}
</script>

<style scoped>
.freqquery-page { padding-bottom: 32px; }
.mb20 { margin-bottom: 20px; }
.mb24 { margin-bottom: 24px; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; }
.page-title  { font-size: 24px; font-weight: 700; color: #f1f5f9; letter-spacing: -0.3px; }
.page-sub    { font-size: 13px; color: #64748b; margin-top: 3px; }

/* ── Search bar ── */
.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background: #0a0f1e;
  border: 1px solid #1e293b;
  border-radius: 14px;
  padding: 14px 18px;
}

.freq-input-wrap {
  display: flex;
  align-items: center;
  background: #060c18;
  border: 1px solid #1e293b;
  border-radius: 9px;
  overflow: hidden;
}
.freq-input {
  background: transparent;
  border: none;
  color: #e2e8f0;
  font-size: 15px;
  font-weight: 600;
  padding: 8px 12px;
  width: 130px;
  outline: none;
  font-variant-numeric: tabular-nums;
}
.freq-input::-webkit-inner-spin-button { opacity: 0; }
.freq-unit {
  padding: 0 12px 0 0;
  font-size: 12px;
  color: #475569;
}

.time-presets { display: flex; gap: 5px; }
.preset-btn {
  padding: 6px 12px; border-radius: 8px;
  border: 1px solid #1e293b; background: transparent;
  color: #64748b; font-size: 12px; cursor: pointer; transition: all .15s;
}
.preset-btn:hover  { border-color: #334155; color: #94a3b8; }
.preset-btn.active { background: rgba(56,189,248,0.1); border-color: #38bdf8; color: #38bdf8; }

.custom-range { display: flex; align-items: center; gap: 8px; }

.query-btn {
  padding: 8px 20px; border-radius: 9px;
  background: rgba(56,189,248,0.12); border: 1px solid rgba(56,189,248,0.4); color: #38bdf8;
  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 8px; min-width: 60px; justify-content: center;
}
.query-btn:hover:not(:disabled) { background: rgba(56,189,248,0.2); }
.query-btn:disabled { opacity: .5; cursor: not-allowed; }
.spinner {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid #1e293b; border-top-color: #38bdf8;
  border-radius: 50%; animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Error / empty ── */
.error-bar {
  background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25);
  border-radius: 10px; padding: 10px 16px; color: #f87171; font-size: 13px;
}
.empty-state { text-align: center; padding: 80px 0; }
.empty-icon  { font-size: 48px; opacity: .3; margin-bottom: 12px; }
.empty-text  { font-size: 15px; color: #475569; }
.empty-hint  { font-size: 12px; color: #334155; margin-top: 4px; }

/* ── Result meta chips ── */
.result-meta { display: flex; gap: 8px; flex-wrap: wrap; }
.meta-chip {
  font-size: 11px; font-weight: 500; padding: 3px 10px; border-radius: 20px;
  border: 1px solid;
}
.chip-freq    { background: rgba(56,189,248,0.08); border-color: rgba(56,189,248,0.3); color: #38bdf8; }
.chip-range   { background: rgba(99,102,241,0.08); border-color: rgba(99,102,241,0.3); color: #818cf8; }
.chip-stations{ background: rgba(34,197,94,0.08);  border-color: rgba(34,197,94,0.3);  color: #4ade80; }

/* ── Rank table ── */
.table-card {
  background: #080e1c;
  border: 1px solid #1e293b;
  border-radius: 14px;
  overflow: hidden;
}
.table-header {
  padding: 12px 18px; font-size: 13px; color: #64748b; font-weight: 500;
  border-bottom: 1px solid #1e293b;
}
.table-header .sub { color: #334155; font-weight: 400; margin-left: 6px; }

.rank-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.rank-table th {
  background: #060c18; padding: 9px 16px;
  text-align: left; font-size: 11px; font-weight: 600;
  color: #475569; text-transform: uppercase; letter-spacing: .4px;
  border-bottom: 1px solid #1e293b;
}
.rank-table td { padding: 10px 16px; border-bottom: 1px solid #0f172a; color: #94a3b8; }
.rank-row:last-child td { border-bottom: none; }
.rank-row { cursor: pointer; transition: background .1s; }
.rank-row:hover td { background: rgba(255,255,255,0.015); }
.rank-row.selected td { background: rgba(56,189,248,0.05); }

.rank-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%;
  font-size: 11px; font-weight: 700;
  background: #1e293b; color: #475569;
}
.rank-badge.gold   { background: rgba(251,191,36,0.15); color: #fbbf24; }
.rank-badge.silver { background: rgba(148,163,184,0.15); color: #94a3b8; }
.rank-badge.bronze { background: rgba(180,83,9,0.15); color: #f97316; }

.stn-id   { font-size: 13px; font-weight: 600; color: #e2e8f0; }
.stn-name { font-size: 11px; color: #475569; margin-top: 1px; }
.cell-dbm { font-weight: 600; font-variant-numeric: tabular-nums; }
.cell-dbm-med { color: #64748b; font-variant-numeric: tabular-nums; }
.cell-frames  { color: #475569; }

.select-btn {
  padding: 3px 10px; border-radius: 6px; font-size: 11px;
  border: 1px solid #1e293b; background: transparent; color: #64748b;
  cursor: pointer; transition: all .12s;
}
.select-btn:hover, .select-btn.active { border-color: #38bdf8; color: #38bdf8; }

/* ── Chart ── */
.chart-card {
  background: #0a0f1e;
  border: 1px solid #1e293b;
  border-radius: 14px;
  overflow: hidden;
}
.chart-topbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px 12px; border-bottom: 1px solid #1e293b;
}
.chart-title   { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #e2e8f0; }
.chart-sname   { font-weight: 400; color: #64748b; }
.chart-actions { display: flex; align-items: center; gap: 12px; }
.chart-meta    { font-size: 12px; color: #475569; }
.zoom-badge    {
  font-size: 11px; padding: 2px 8px; border-radius: 6px;
  background: rgba(251,191,36,0.1); border: 1px solid rgba(251,191,36,0.3); color: #fbbf24;
}
.action-btn {
  padding: 4px 12px; border-radius: 7px;
  border: 1px solid #334155; background: transparent; color: #64748b;
  font-size: 12px; cursor: pointer; transition: all .15s;
}
.action-btn:hover { border-color: #38bdf8; color: #38bdf8; }
.chart-area { width: 100%; height: 400px; }
</style>
