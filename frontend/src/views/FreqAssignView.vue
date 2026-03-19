<template>
  <div class="freqassign-page">
    <div class="page-header mb24">
      <div>
        <h2 class="page-title">频率指配</h2>
        <p class="page-sub">输入频段与信道参数，自动识别空闲信道</p>
      </div>
      <button class="dual-toggle" :class="{ active: dualBand }" @click="dualBand = !dualBand">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <rect x="2" y="4" width="9" height="16" rx="2"/>
          <rect x="13" y="4" width="9" height="16" rx="2"/>
        </svg>
        {{ dualBand ? '单频段' : '双频段' }}
      </button>
    </div>

    <!-- ── Form ── -->
    <div class="form-card mb24">
      <div class="form-grid">
        <!-- Station -->
        <div class="form-group">
          <label class="label">站点</label>
          <select v-model="form.station_id" class="select-input">
            <option value="">-- 选择站点 --</option>
            <option v-for="s in stations" :key="s.station_id" :value="s.station_id">
              {{ s.name || s.station_id }}
              <template v-if="s.online"> ●</template>
            </option>
          </select>
        </div>

        <!-- Band 1: Freq range -->
        <div class="form-group">
          <label class="label">{{ dualBand ? '频段1 起始 (MHz)' : '起始频率 (MHz)' }}</label>
          <input v-model.number="form.start_mhz" class="num-input" type="number" step="0.001" placeholder="e.g. 136" />
        </div>
        <div class="form-group">
          <label class="label">{{ dualBand ? '频段1 截止 (MHz)' : '截止频率 (MHz)' }}</label>
          <input v-model.number="form.stop_mhz" class="num-input" type="number" step="0.001" placeholder="e.g. 174" />
        </div>

        <!-- Band 2: Freq range (only in dual mode) -->
        <template v-if="dualBand">
          <div class="form-group">
            <label class="label">频段2 起始 (MHz)</label>
            <input v-model.number="form2.start_mhz" class="num-input" type="number" step="0.001" placeholder="e.g. 410" />
          </div>
          <div class="form-group">
            <label class="label">频段2 截止 (MHz)</label>
            <input v-model.number="form2.stop_mhz" class="num-input" type="number" step="0.001" placeholder="e.g. 430" />
          </div>
        </template>

        <!-- Channel BW -->
        <div class="form-group">
          <label class="label">信道带宽 (kHz)</label>
          <div class="input-with-presets">
            <input v-model.number="form.channel_bw_khz" class="num-input" type="number" step="1" placeholder="25" />
            <div class="bw-presets">
              <button v-for="bw in BW_PRESETS" :key="bw"
                class="bw-btn"
                :class="{ active: form.channel_bw_khz === bw }"
                @click="form.channel_bw_khz = bw">{{ bw }}</button>
            </div>
          </div>
        </div>

        <!-- Threshold -->
        <div class="form-group">
          <label class="label">占用阈值 (dBm)</label>
          <div class="slider-wrap">
            <input v-model.number="form.threshold_dbm" type="range" min="-120" max="-40" step="1" class="dbm-slider" />
            <span class="dbm-val">{{ form.threshold_dbm }} dBm</span>
          </div>
        </div>

        <!-- Lookback -->
        <div class="form-group">
          <label class="label">观测窗口</label>
          <select v-model.number="form.lookback_s" class="select-input">
            <option :value="1800">30 分钟</option>
            <option :value="3600">1 小时</option>
            <option :value="21600">6 小时</option>
            <option :value="86400">24 小时</option>
            <option :value="259200">3 天</option>
          </select>
        </div>
      </div>

      <div class="form-footer">
        <div class="channel-preview" v-if="form.start_mhz && form.stop_mhz && form.channel_bw_khz">
          频段1: {{ channelCount }} 个信道
          <template v-if="dualBand && form2.start_mhz && form2.stop_mhz">
            · 频段2: {{ channelCount2 }} 个信道
          </template>
        </div>
        <button class="run-btn" :disabled="loading || !canRun" @click="run">
          <span v-if="loading" class="spinner" />
          <span v-else>计算空闲信道</span>
        </button>
      </div>
    </div>

    <!-- ── Error ── -->
    <div v-if="error" class="error-bar mb20">⚠ {{ error }}</div>

    <!-- ── Results ── -->
    <template v-if="result">
      <!-- Summary row -->
      <div class="summary-row mb20">
        <div class="stat-box">
          <div class="stat-num">{{ result.total_channels }}</div>
          <div class="stat-label">{{ dualBand ? '频段1 总数' : '信道总数' }}</div>
        </div>
        <div class="stat-box">
          <div class="stat-num text-green">{{ result.free_channels }}</div>
          <div class="stat-label">{{ dualBand ? '频段1 空闲' : '空闲信道' }}</div>
        </div>
        <div class="stat-box">
          <div class="stat-num text-red">{{ result.total_channels - result.free_channels }}</div>
          <div class="stat-label">{{ dualBand ? '频段1 占用' : '占用信道' }}</div>
        </div>
        <template v-if="dualBand && result2">
          <div class="stat-divider" />
          <div class="stat-box">
            <div class="stat-num">{{ result2.total_channels }}</div>
            <div class="stat-label">频段2 总数</div>
          </div>
          <div class="stat-box">
            <div class="stat-num text-green">{{ result2.free_channels }}</div>
            <div class="stat-label">频段2 空闲</div>
          </div>
          <div class="stat-box">
            <div class="stat-num text-red">{{ result2.total_channels - result2.free_channels }}</div>
            <div class="stat-label">频段2 占用</div>
          </div>
        </template>
        <div class="stat-box">
          <div class="stat-num text-blue">{{ freeRate }}%</div>
          <div class="stat-label">空闲率</div>
        </div>
        <div class="stat-box-right">
          <button class="export-btn" @click="exportCsv">导出 CSV</button>
        </div>
      </div>

      <!-- Chart hint -->
      <div class="chart-hint mb8">拖动图表中的黄色虚线可调整占用阈值</div>

      <!-- Band 1 occupancy chart -->
      <div class="chart-card mb16">
        <div class="chart-header">{{ dualBand ? '频段1' : '信道占用概览' }} · {{ (form.start_mhz).toFixed(3) }}–{{ (form.stop_mhz).toFixed(3) }} MHz</div>
        <div ref="chartEl" class="chart-area" />
      </div>

      <!-- Band 2 chart (dual mode only) -->
      <div v-if="dualBand && result2" class="chart-card mb24">
        <div class="chart-header">频段2 · {{ (form2.start_mhz).toFixed(3) }}–{{ (form2.stop_mhz).toFixed(3) }} MHz</div>
        <div ref="chartEl2" class="chart-area" />
      </div>

      <!-- Filter toolbar -->
      <div class="filter-bar mb16">
        <div class="filter-tabs">
          <button
            v-for="f in FILTERS"
            :key="f.value"
            class="filter-tab"
            :class="{ active: filter === f.value }"
            @click="filter = f.value"
          >{{ f.label }} ({{ filterCount(f.value) }})</button>
        </div>
        <input v-model="searchHz" class="search-input" placeholder="搜索中心频率 (MHz) …" />
      </div>

      <!-- Channel table -->
      <div class="table-card">
        <table class="chan-table">
          <thead>
            <tr>
              <th>#</th>
              <th>中心频率</th>
              <th>信道范围</th>
              <th>最大电平</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ch in filteredChannels" :key="ch.channel_idx" class="chan-row">
              <td class="cell-idx">{{ ch.channel_idx + 1 }}</td>
              <td class="cell-center">{{ (ch.center_hz / 1e6).toFixed(4) }} MHz</td>
              <td class="cell-range">
                {{ (ch.start_hz / 1e6).toFixed(4) }} – {{ (ch.stop_hz / 1e6).toFixed(4) }}
              </td>
              <td class="cell-dbm" :style="dbmStyle(ch.max_dbm)">
                {{ ch.max_dbm !== null ? ch.max_dbm.toFixed(1) + ' dBm' : '—' }}
              </td>
              <td class="cell-status">
                <span class="status-badge" :class="ch.free ? 'badge-free' : 'badge-busy'">
                  {{ ch.free ? '空闲' : '占用' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="filteredChannels.length === 0" class="table-empty">无匹配信道</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useTheme } from '../composables/useTheme.js'
import { getStations, computeFreqAssign } from '../api/index.js'

const { isDark, chartColors } = useTheme()

const CHART_GROUP = 'freq-assign-group'
const FLOOR_DBM   = -120   // base of all bars
const BW_PRESETS  = [12.5, 25, 50, 200]
const FILTERS     = [
  { label: '全部',   value: 'all'    },
  { label: '空闲',   value: 'free'   },
  { label: '占用',   value: 'busy'   },
  { label: '无数据', value: 'nodata' },
]

const stations  = ref([])
const dualBand  = ref(false)
const form      = ref({
  station_id: '',
  start_mhz: 136,
  stop_mhz: 174,
  channel_bw_khz: 25,
  threshold_dbm: -90,
  lookback_s: 3600,
})
const form2     = ref({ start_mhz: 410, stop_mhz: 430 })
const loading   = ref(false)
const error     = ref('')
const result    = ref(null)
const result2   = ref(null)
const filter    = ref('all')
const searchHz  = ref('')
const chartEl   = ref(null)
const chartEl2  = ref(null)
let chart  = null
let chart2 = null

// Track threshold dragging state
let threshDragging = false

// ── Derived ───────────────────────────────────────────────────────────────────

const canRun = computed(() => {
  const f = form.value
  const ok1 = f.station_id && f.start_mhz && f.stop_mhz && f.channel_bw_khz > 0 && f.stop_mhz > f.start_mhz
  if (!dualBand.value) return ok1
  const f2 = form2.value
  return ok1 && f2.start_mhz && f2.stop_mhz && f2.stop_mhz > f2.start_mhz
})

const channelCount = computed(() => {
  const { start_mhz, stop_mhz, channel_bw_khz } = form.value
  if (!start_mhz || !stop_mhz || !channel_bw_khz) return 0
  return Math.max(1, Math.floor((stop_mhz - start_mhz) * 1000 / channel_bw_khz))
})

const channelCount2 = computed(() => {
  const { start_mhz, stop_mhz } = form2.value
  if (!start_mhz || !stop_mhz) return 0
  return Math.max(1, Math.floor((stop_mhz - start_mhz) * 1000 / form.value.channel_bw_khz))
})

const freeRate = computed(() => {
  if (!result.value || result.value.total_channels === 0) return 0
  return Math.round(result.value.free_channels / result.value.total_channels * 100)
})

const filteredChannels = computed(() => {
  if (!result.value) return []
  let list = result.value.channels
  if (filter.value === 'free')   list = list.filter(c => c.free)
  if (filter.value === 'busy')   list = list.filter(c => !c.free && c.max_dbm !== null)
  if (filter.value === 'nodata') list = list.filter(c => c.max_dbm === null)
  if (searchHz.value) {
    const q = parseFloat(searchHz.value)
    if (!isNaN(q)) {
      const qHz = q * 1e6
      const margin = (form.value.channel_bw_khz * 1e3) / 2
      list = list.filter(c => Math.abs(c.center_hz - qHz) <= margin * 10)
    }
  }
  return list
})

function filterCount(f) {
  if (!result.value) return 0
  const ch = result.value.channels
  if (f === 'all')    return ch.length
  if (f === 'free')   return ch.filter(c => c.free).length
  if (f === 'busy')   return ch.filter(c => !c.free && c.max_dbm !== null).length
  if (f === 'nodata') return ch.filter(c => c.max_dbm === null).length
  return 0
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function run() {
  loading.value = true
  error.value = ''
  try {
    const f = form.value
    const base = {
      station_id:    f.station_id,
      channel_bw_hz: f.channel_bw_khz * 1e3,
      threshold_dbm: f.threshold_dbm,
      lookback_s:    f.lookback_s,
    }
    const tasks = [
      computeFreqAssign({ ...base, start_hz: f.start_mhz * 1e6, stop_hz: f.stop_mhz * 1e6 }),
    ]
    if (dualBand.value) {
      tasks.push(computeFreqAssign({ ...base, start_hz: form2.value.start_mhz * 1e6, stop_hz: form2.value.stop_mhz * 1e6 }))
    }
    const results = await Promise.all(tasks)
    result.value  = results[0]
    result2.value = results[1] ?? null
    filter.value = 'all'
  } catch (e) {
    error.value = '查询失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  if (!result.value) return
  const hdr = '#,中心频率(MHz),起始(MHz),截止(MHz),最大电平(dBm),状态\n'
  const rows = result.value.channels.map(c =>
    `${c.channel_idx + 1},${(c.center_hz/1e6).toFixed(4)},${(c.start_hz/1e6).toFixed(4)},${(c.stop_hz/1e6).toFixed(4)},${c.max_dbm ?? ''},${c.free ? '空闲' : '占用'}`
  ).join('\n')
  const blob = new Blob(['\uFEFF' + hdr + rows], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `freq-assign-${result.value.station_id}-${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── Chart ─────────────────────────────────────────────────────────────────────

function buildBarData(channels, thresh) {
  return channels.map(c => ({
    // [x, yBase, yTop] — bars from FLOOR_DBM up to max_dbm
    value: [c.channel_idx, FLOOR_DBM, c.max_dbm !== null ? c.max_dbm : FLOOR_DBM + 3],
    itemStyle: {
      color: c.max_dbm === null
        ? 'rgba(51,65,85,0.4)'
        : c.max_dbm < thresh
          ? '#4ade80'   // free (green)
          : '#f87171',  // occupied (red)
    },
  }))
}

function buildChartOption(channels, thresh, colors) {
  return {
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 60, right: 16, top: 16, bottom: 44 },
    tooltip: {
      formatter: (p) => {
        const ch = channels[p.data.value[0]]
        if (!ch) return ''
        const dbm = ch.max_dbm !== null ? ch.max_dbm.toFixed(1) + ' dBm' : '无数据'
        const free = ch.max_dbm === null || ch.max_dbm < thresh
        return `<span style="color:${colors.tooltipMuted};font-size:11px">Ch ${ch.channel_idx + 1} · ${(ch.center_hz/1e6).toFixed(4)} MHz</span><br/><b>${dbm}</b><br/><span style="color:${free?'#4ade80':'#f87171'}">${free?'空闲':'占用'}</span>`
      },
      backgroundColor: colors.tooltipBg, borderColor: colors.tooltipBorder, borderWidth: 1,
      textStyle: { color: colors.tooltipText, fontSize: 12 },
    },
    xAxis: {
      type: 'value',
      min: 0, max: channels.length - 1,
      axisLabel: {
        color: colors.axisLabel, fontSize: 10,
        formatter: (v) => {
          const ch = channels[Math.round(v)]
          return ch ? (ch.center_hz / 1e6).toFixed(2) : ''
        },
        interval: Math.floor(channels.length / 12),
      },
      axisLine: { lineStyle: { color: colors.axisLine } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      min: FLOOR_DBM, max: -30,
      name: 'dBm', nameTextStyle: { color: colors.axisLabel, fontSize: 11 },
      axisLabel: { color: colors.axisLabel, fontSize: 10 },
      axisLine: { lineStyle: { color: colors.axisLine } },
      splitLine: { lineStyle: { color: colors.splitLine, type: 'dashed' } },
    },
    series: [{
      type: 'bar',
      data: buildBarData(channels, thresh),
      encode: { x: 0, y: [1, 2] },
      barWidth: Math.max(1, Math.floor(700 / channels.length)),
      markLine: {
        symbol: ['none', 'none'],
        data: [{ yAxis: thresh }],
        lineStyle: { color: '#fbbf24', type: 'dashed', width: 1.5 },
        label: { formatter: `${thresh} dBm`, color: '#fbbf24', fontSize: 10, position: 'insideEndTop' },
      },
    }],
    dataZoom: [
      { type: 'inside', xAxisIndex: 0 },
      { type: 'slider', xAxisIndex: 0, bottom: 4, height: 22,
        fillerColor: colors.dzFiller, borderColor: colors.dzBg,
        handleStyle: { color: colors.accent, borderColor: colors.accent },
        textStyle: { color: colors.axisLabel, fontSize: 9 },
      },
    ],
  }
}

function initChart(el, group) {
  const c = echarts.init(el, chartColors.value.ecTheme)
  c.group = group
  echarts.connect(group)
  return c
}

function setupThreshDrag(c) {
  if (!c) return
  const zr = c.getZr()

  zr.on('mousedown', (e) => {
    if (!result.value) return
    const yDbm = c.convertFromPixel({ yAxisIndex: 0 }, e.offsetY)
    if (Math.abs(yDbm - form.value.threshold_dbm) < 3) {
      threshDragging = true
    }
  })

  zr.on('mousemove', (e) => {
    if (!threshDragging || !result.value) return
    const raw = c.convertFromPixel({ yAxisIndex: 0 }, e.offsetY)
    const newDbm = Math.max(-120, Math.min(-40, Math.round(raw)))
    form.value.threshold_dbm = newDbm
    // Update both charts' markLine and bar colors
    const newData1 = buildBarData(result.value.channels, newDbm)
    chart?.setOption({ series: [{ data: newData1, markLine: { data: [{ yAxis: newDbm }], label: { formatter: `${newDbm} dBm` } } }] })
    if (result2.value) {
      const newData2 = buildBarData(result2.value.channels, newDbm)
      chart2?.setOption({ series: [{ data: newData2, markLine: { data: [{ yAxis: newDbm }], label: { formatter: `${newDbm} dBm` } } }] })
    }
  })

  const stopDrag = () => { threshDragging = false }
  zr.on('mouseup',    stopDrag)
  zr.on('globalout',  stopDrag)
}

async function renderCharts() {
  if (!result.value) return
  await nextTick()

  const thresh  = form.value.threshold_dbm
  const colors  = chartColors.value

  // Chart 1
  if (!chart && chartEl.value) {
    chart = initChart(chartEl.value, CHART_GROUP)
    setupThreshDrag(chart)
  }
  if (chart) {
    chart.setOption(buildChartOption(result.value.channels, thresh, colors), true)
  }

  // Chart 2 (dual band)
  if (result2.value && chartEl2.value) {
    if (!chart2) {
      chart2 = initChart(chartEl2.value, CHART_GROUP)
      setupThreshDrag(chart2)
    }
    chart2.setOption(buildChartOption(result2.value.channels, thresh, colors), true)
  }
}

// Re-render when threshold slider changes (not during drag — drag handles it inline)
watch(() => form.value.threshold_dbm, (newDbm) => {
  if (threshDragging) return
  if (!result.value) return
  const newData1 = buildBarData(result.value.channels, newDbm)
  chart?.setOption({ series: [{ data: newData1, markLine: { data: [{ yAxis: newDbm }], label: { formatter: `${newDbm} dBm` } } }] })
  if (result2.value) {
    const newData2 = buildBarData(result2.value.channels, newDbm)
    chart2?.setOption({ series: [{ data: newData2, markLine: { data: [{ yAxis: newDbm }], label: { formatter: `${newDbm} dBm` } } }] })
  }
})

watch(result, renderCharts)

watch(isDark, async () => {
  if (!result.value) return
  await nextTick()
  if (chart)  { chart.dispose();  chart  = null }
  if (chart2) { chart2.dispose(); chart2 = null }
  renderCharts()
})

function onResize() {
  chart?.resize()
  chart2?.resize()
}

onMounted(async () => {
  window.addEventListener('resize', onResize)
  try {
    const data = await getStations()
    stations.value = data
    if (data.length === 1) form.value.station_id = data[0].station_id
  } catch (_) {}
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart2?.dispose()
})

// ── Helpers ───────────────────────────────────────────────────────────────────

function dbmStyle(dbm) {
  if (dbm === null) return { color: '#334155' }
  const t = Math.max(0, Math.min(1, (dbm + 120) / 100))
  if (t > 0.7) return { color: '#f87171' }
  if (t > 0.4) return { color: '#fb923c' }
  if (t > 0.2) return { color: '#38bdf8' }
  return { color: '#475569' }
}
</script>

<style scoped>
.freqassign-page { padding-bottom: 32px; transition: background 0.2s, border-color 0.2s, color 0.2s; }
.mb8  { margin-bottom: 8px; }
.mb16 { margin-bottom: 16px; }
.mb20 { margin-bottom: 20px; }
.mb24 { margin-bottom: 24px; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; }
.page-title  { font-size: 24px; font-weight: 700; color: var(--c-text); letter-spacing: -0.3px; }
.page-sub    { font-size: 13px; color: var(--c-text-dim); margin-top: 3px; }

.dual-toggle {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: 9px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-dim);
  cursor: pointer; transition: all .15s;
}
.dual-toggle:hover  { border-color: var(--c-accent); color: var(--c-accent); }
.dual-toggle.active { background: var(--c-accent-bgx); border-color: var(--c-accent); color: var(--c-accent); }

/* ── Form ── */
.form-card {
  background: var(--c-card-2); border: 1px solid var(--c-border); border-radius: 14px; padding: 20px 22px;
}
.form-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px 20px;
}
.form-group { display: flex; flex-direction: column; gap: 6px; }
.label { font-size: 11px; font-weight: 600; color: var(--c-text-dim); text-transform: uppercase; letter-spacing: .4px; }

.select-input, .num-input {
  background: var(--c-bg); border: 1px solid var(--c-border); border-radius: 8px;
  color: var(--c-text-2); font-size: 13px; padding: 7px 10px; outline: none;
  transition: border-color .15s;
}
.select-input:focus, .num-input:focus { border-color: var(--c-border-str); }
.num-input::-webkit-inner-spin-button { opacity: .4; }

.input-with-presets { display: flex; flex-direction: column; gap: 6px; }
.bw-presets { display: flex; gap: 4px; flex-wrap: wrap; }
.bw-btn {
  padding: 3px 8px; border-radius: 6px; font-size: 11px;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-faint); cursor: pointer;
}
.bw-btn:hover  { border-color: var(--c-border-str); color: var(--c-text-muted); }
.bw-btn.active { background: var(--c-accent-bgx); border-color: var(--c-accent); color: var(--c-accent); }

.slider-wrap   { display: flex; align-items: center; gap: 10px; }
.dbm-slider    { flex: 1; accent-color: var(--c-accent); }
.dbm-val       { font-size: 12px; color: var(--c-text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }

.form-footer {
  display: flex; justify-content: flex-end; align-items: center; gap: 16px;
  margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--c-raised);
}
.channel-preview { font-size: 12px; color: var(--c-text-faint); }
.run-btn {
  padding: 9px 22px; border-radius: 9px;
  background: var(--c-accent-bgx); border: 1px solid var(--c-accent-bd); color: var(--c-accent);
  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 8px;
}
.run-btn:hover:not(:disabled) { background: var(--c-accent-bgh); }
.run-btn:disabled { opacity: .5; cursor: not-allowed; }
.spinner {
  width: 14px; height: 14px; border: 2px solid var(--c-border); border-top-color: var(--c-accent);
  border-radius: 50%; animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Error ── */
.error-bar {
  background: var(--c-red-bg); border: 1px solid var(--c-red-bd);
  border-radius: 10px; padding: 10px 16px; color: var(--c-red); font-size: 13px;
}

/* ── Summary ── */
.summary-row {
  display: flex; gap: 12px; align-items: stretch; flex-wrap: wrap;
}
.stat-box {
  background: var(--c-card); border: 1px solid var(--c-border); border-radius: 12px;
  padding: 14px 20px; text-align: center; min-width: 90px;
}
.stat-divider {
  width: 1px; background: var(--c-border); margin: 4px 0; flex-shrink: 0;
}
.stat-num   { font-size: 26px; font-weight: 700; color: var(--c-text-2); line-height: 1; }
.stat-label { font-size: 11px; color: var(--c-text-faint); margin-top: 4px; }
.text-green { color: var(--c-green) !important; }
.text-red   { color: var(--c-red)   !important; }
.text-blue  { color: var(--c-accent) !important; }
.stat-box-right { flex: 1; display: flex; align-items: center; justify-content: flex-end; }
.export-btn {
  padding: 8px 16px; border-radius: 8px;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-dim);
  font-size: 12px; cursor: pointer; transition: all .15s;
}
.export-btn:hover { border-color: var(--c-accent); color: var(--c-accent); }

/* ── Chart ── */
.chart-hint {
  font-size: 11px; color: var(--c-text-ghost);
}
.chart-card {
  background: var(--c-card-2); border: 1px solid var(--c-border); border-radius: 14px; overflow: hidden;
}
.chart-header {
  padding: 12px 18px; font-size: 13px; color: var(--c-text-dim); font-weight: 500;
  border-bottom: 1px solid var(--c-border);
}
.chart-area { width: 100%; height: 240px; cursor: ns-resize; }

/* ── Filter bar ── */
.filter-bar  { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.filter-tabs { display: flex; gap: 4px; }
.filter-tab {
  padding: 5px 12px; border-radius: 8px; font-size: 12px;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-faint); cursor: pointer;
}
.filter-tab:hover  { border-color: var(--c-border-str); color: var(--c-text-muted); }
.filter-tab.active { background: var(--c-accent-bg); border-color: var(--c-accent); color: var(--c-accent); }
.search-input {
  background: var(--c-bg); border: 1px solid var(--c-border); border-radius: 8px;
  color: var(--c-text-2); font-size: 12px; padding: 5px 10px; outline: none; min-width: 170px;
}

/* ── Channel table ── */
.table-card {
  background: var(--c-card); border: 1px solid var(--c-border); border-radius: 14px; overflow: hidden;
}
.chan-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.chan-table th {
  background: var(--c-bg); padding: 9px 16px;
  text-align: left; font-size: 11px; font-weight: 600;
  color: var(--c-text-faint); text-transform: uppercase; letter-spacing: .4px;
  border-bottom: 1px solid var(--c-border);
}
.chan-table td { padding: 9px 16px; border-bottom: 1px solid var(--c-border-sub); color: var(--c-text-muted); }
.chan-row:last-child td { border-bottom: none; }
.chan-row:hover td { background: rgba(255,255,255,0.01); }

.cell-idx    { color: var(--c-text-faint); font-size: 12px; }
.cell-center { font-weight: 600; color: var(--c-text-2); font-variant-numeric: tabular-nums; }
.cell-range  { font-size: 11px; color: var(--c-text-faint); font-variant-numeric: tabular-nums; }
.cell-dbm    { font-weight: 600; font-variant-numeric: tabular-nums; }

.status-badge {
  display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 11px; font-weight: 600;
  border: 1px solid;
}
.badge-free { background: var(--c-green-bg); border-color: var(--c-green-bd); color: var(--c-green); }
.badge-busy { background: var(--c-red-bg);   border-color: var(--c-red-bd);   color: var(--c-red);   }

.table-empty { padding: 24px; text-align: center; color: var(--c-text-ghost); font-size: 13px; }
</style>
