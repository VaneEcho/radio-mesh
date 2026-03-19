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
      <div class="bw-input-wrap">
        <input
          v-model.number="bandwidthKhz"
          class="bw-input"
          type="number"
          step="1"
          min="1"
          placeholder="分析带宽"
        />
        <span class="bw-unit">kHz</span>
      </div>
      <div class="bw-presets">
        <button v-for="bw in BW_PRESETS" :key="bw.value"
          class="bw-btn" :class="{ active: bandwidthKhz === bw.value }"
          @click="bandwidthKhz = bw.value">{{ bw.label }}</button>
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
        <span class="meta-chip chip-bw">BW {{ (result.bandwidth_hz / 1e3).toFixed(1) }} kHz</span>
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
import { useTheme } from '../composables/useTheme.js'

const PRESETS = [
  { label: '1 小时', value: '1h' },
  { label: '6 小时', value: '6h' },
  { label: '24 小时', value: '24h' },
  { label: '7 天',   value: '7d' },
  { label: '自定义', value: 'custom' },
]

const BW_PRESETS = [
  { label: '12.5K', value: 12.5 },
  { label: '25K',   value: 25 },
  { label: '100K',  value: 100 },
  { label: '200K',  value: 200 },
]

const { isDark, chartColors } = useTheme()

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
const bandwidthKhz = ref(25)

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
  if (preset.value === 'custom') {
    if (!customStart.value || !customEnd.value) {
      error.value = '请先选择自定义时间范围'
      return
    }
    if (Number(customEnd.value) <= Number(customStart.value)) {
      error.value = '结束时间必须晚于开始时间'
      return
    }
  }

  loading.value = true
  error.value = ''
  try {
    const [start, end] = timeRange()
    result.value = await queryFreqTimeseries(mhz * 1e6, start, end, [], bandwidthKhz.value * 1000)
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
  if (n <= target) {
    const out = new Array(n)
    for (let i = 0; i < n; i++) out[i] = [series[i].t, series[i].dbm]
    return out
  }
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
  chart = echarts.init(chartEl.value, chartColors.value.ecTheme)
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
      backgroundColor: chartColors.value.tooltipBg,
      borderColor: chartColors.value.tooltipBorder,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: chartColors.value.tooltipText, fontSize: 12 },
    },
    xAxis: {
      type: 'time',
      axisLabel: {
        color: chartColors.value.axisLabel, fontSize: 11,
        formatter: (v) => {
          const d = new Date(v)
          return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
        },
      },
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
      sampling: null,
      smooth: false,
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

  chart.off('datazoom')
  chart.on('datazoom', (e) => {
    const ev = e.batch?.[0] ?? e
    // For time-axis dataZoom, startValue/endValue are Unix ms timestamps.
    const startMs = ev.startValue
    const endMs   = ev.endValue
    if (startMs == null || endMs == null || series.length === 0) return

    const totalMs  = series[series.length - 1].t - series[0].t
    const startPct = totalMs > 0 ? (startMs - series[0].t) / totalMs * 100 : 0
    const endPct   = totalMs > 0 ? (endMs   - series[0].t) / totalMs * 100 : 100

    isZoomed.value = startPct > 0.5 || endPct < 99.5

    if (!isZoomed.value) {
      isShowingRaw.value = false
      chart.setOption({ series: [{ data: overviewData, smooth: false }] })
      return
    }

    // Find index bounds by timestamp
    let lo = 0
    while (lo < series.length - 1 && series[lo].t < startMs) lo++
    lo = Math.max(0, lo - 1)
    let hi = series.length
    while (hi > 1 && series[hi - 1].t > endMs) hi--
    hi = Math.min(series.length, hi + 1)

    const { data, raw } = buildSeriesData(series, lo, hi, TARGET_PTS)
    isShowingRaw.value = raw
    chart.setOption({ series: [{ data, smooth: raw }] })
  })
}

watch(activeStation, async (s) => {
  if (!s) {
    // v-if will destroy the DOM element; dispose chart to avoid stale instance
    if (chart) { chart.dispose(); chart = null }
    return
  }
  await nextTick()
  // Always rebuild: v-if may have recreated the DOM element since last render
  buildChart()
  renderStationChart(s)
})

watch(isDark, async () => {
  if (!chart || !activeStation.value) return
  await nextTick()
  buildChart()
  renderStationChart(activeStation.value)
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
.page-title  { font-size: 24px; font-weight: 700; color: var(--c-text); letter-spacing: -0.3px; }
.page-sub    { font-size: 13px; color: var(--c-text-dim); margin-top: 3px; }

/* ── Search bar ── */
.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background: var(--c-card-2);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 14px 18px;
}

.freq-input-wrap {
  display: flex;
  align-items: center;
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: 9px;
  overflow: hidden;
}
.freq-input {
  background: transparent;
  border: none;
  color: var(--c-text-2);
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
  color: var(--c-text-faint);
}

.bw-input-wrap {
  display: flex;
  align-items: center;
  background: var(--c-deep);
  border: 1px solid var(--c-border);
  border-radius: 9px;
  overflow: hidden;
}
.bw-input {
  background: transparent;
  border: none;
  color: var(--c-text-2);
  font-size: 14px;
  font-weight: 600;
  padding: 8px 10px;
  width: 100px;
  outline: none;
  font-variant-numeric: tabular-nums;
}
.bw-input::-webkit-inner-spin-button { opacity: 0; }
.bw-unit {
  padding: 0 10px 0 0;
  font-size: 12px;
  color: var(--c-text-faint);
}
.bw-presets {
  display: flex;
  gap: 4px;
}
.bw-btn {
  padding: 5px 10px;
  border-radius: 7px;
  border: 1px solid var(--c-border);
  background: transparent;
  color: var(--c-text-dim);
  font-size: 11px;
  cursor: pointer;
  transition: all .15s;
}
.bw-btn:hover  { border-color: var(--c-border-str); color: var(--c-text-muted); }
.bw-btn.active { background: var(--c-accent-bgx); border-color: var(--c-accent); color: var(--c-accent); }

.time-presets { display: flex; gap: 5px; }
.preset-btn {
  padding: 6px 12px; border-radius: 8px;
  border: 1px solid var(--c-border); background: transparent;
  color: var(--c-text-dim); font-size: 12px; cursor: pointer; transition: all .15s;
}
.preset-btn:hover  { border-color: var(--c-border-str); color: var(--c-text-muted); }
.preset-btn.active { background: var(--c-accent-bgx); border-color: var(--c-accent); color: var(--c-accent); }

.custom-range { display: flex; align-items: center; gap: 8px; }

.query-btn {
  padding: 8px 20px; border-radius: 9px;
  background: var(--c-accent-bgh); border: 1px solid var(--c-accent-bd); color: var(--c-accent);
  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 8px; min-width: 60px; justify-content: center;
}
.query-btn:hover:not(:disabled) { background: var(--c-accent-bds); }
.query-btn:disabled { opacity: .5; cursor: not-allowed; }
.spinner {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid var(--c-border); border-top-color: var(--c-accent);
  border-radius: 50%; animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Error / empty ── */
.error-bar {
  background: var(--c-red-bg); border: 1px solid var(--c-red-bd);
  border-radius: 10px; padding: 10px 16px; color: var(--c-red); font-size: 13px;
}
.empty-state { text-align: center; padding: 80px 0; }
.empty-icon  { font-size: 48px; opacity: .3; margin-bottom: 12px; }
.empty-text  { font-size: 15px; color: var(--c-text-faint); }
.empty-hint  { font-size: 12px; color: var(--c-border-str); margin-top: 4px; }

/* ── Result meta chips ── */
.result-meta { display: flex; gap: 8px; flex-wrap: wrap; }
.meta-chip {
  font-size: 11px; font-weight: 500; padding: 3px 10px; border-radius: 20px;
  border: 1px solid;
}
.chip-freq    { background: var(--c-accent-bgx); border-color: var(--c-accent-bds); color: var(--c-accent); }
.chip-range   { background: var(--c-indigo-bg); border-color: var(--c-indigo-bd); color: var(--c-indigo); }
.chip-stations{ background: var(--c-green-bg); border-color: var(--c-green-bd); color: var(--c-green); }
.chip-bw      { background: var(--c-gold-bg); border-color: var(--c-gold-bd); color: var(--c-gold); }

/* ── Rank table ── */
.table-card {
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  overflow: hidden;
}
.table-header {
  padding: 12px 18px; font-size: 13px; color: var(--c-text-dim); font-weight: 500;
  border-bottom: 1px solid var(--c-border);
}
.table-header .sub { color: var(--c-border-str); font-weight: 400; margin-left: 6px; }

.rank-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.rank-table th {
  background: var(--c-bg); padding: 9px 16px;
  text-align: left; font-size: 11px; font-weight: 600;
  color: var(--c-text-faint); text-transform: uppercase; letter-spacing: .4px;
  border-bottom: 1px solid var(--c-border);
}
.rank-table td { padding: 10px 16px; border-bottom: 1px solid var(--c-raised); color: var(--c-text-muted); }
.rank-row:last-child td { border-bottom: none; }
.rank-row { cursor: pointer; transition: background .1s; }
.rank-row:hover td { background: rgba(255,255,255,0.015); }
.rank-row.selected td { background: rgba(56,189,248,0.05); }

.rank-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%;
  font-size: 11px; font-weight: 700;
  background: var(--c-border); color: var(--c-text-faint);
}
.rank-badge.gold   { background: rgba(251,191,36,0.15); color: var(--c-gold); }
.rank-badge.silver { background: rgba(148,163,184,0.15); color: var(--c-text-muted); }
.rank-badge.bronze { background: rgba(180,83,9,0.15); color: #f97316; }

.stn-id   { font-size: 13px; font-weight: 600; color: var(--c-text-2); }
.stn-name { font-size: 11px; color: var(--c-text-faint); margin-top: 1px; }
.cell-dbm { font-weight: 600; font-variant-numeric: tabular-nums; }
.cell-dbm-med { color: var(--c-text-dim); font-variant-numeric: tabular-nums; }
.cell-frames  { color: var(--c-text-faint); }

.select-btn {
  padding: 3px 10px; border-radius: 6px; font-size: 11px;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-dim);
  cursor: pointer; transition: all .12s;
}
.select-btn:hover, .select-btn.active { border-color: var(--c-accent); color: var(--c-accent); }

/* ── Chart ── */
.chart-card {
  background: var(--c-card-2);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  overflow: hidden;
}
.chart-topbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px 12px; border-bottom: 1px solid var(--c-border);
}
.chart-title   { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: var(--c-text-2); }
.chart-sname   { font-weight: 400; color: var(--c-text-dim); }
.chart-actions { display: flex; align-items: center; gap: 12px; }
.chart-meta    { font-size: 12px; color: var(--c-text-faint); }
.zoom-badge    {
  font-size: 11px; padding: 2px 8px; border-radius: 6px;
  background: var(--c-gold-bg); border: 1px solid var(--c-gold-bd); color: var(--c-gold);
}
.action-btn {
  padding: 4px 12px; border-radius: 7px;
  border: 1px solid var(--c-border-str); background: transparent; color: var(--c-text-dim);
  font-size: 12px; cursor: pointer; transition: all .15s;
}
.action-btn:hover { border-color: var(--c-accent); color: var(--c-accent); }
.chart-area { width: 100%; height: 400px; }
</style>
