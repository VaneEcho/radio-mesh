<template>
  <div class="freqassign-page">
    <div class="page-header mb24">
      <div>
        <h2 class="page-title">频率指配</h2>
        <p class="page-sub">输入频段与信道参数，自动识别空闲信道</p>
      </div>
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

        <!-- Freq range -->
        <div class="form-group">
          <label class="label">起始频率 (MHz)</label>
          <input v-model.number="form.start_mhz" class="num-input" type="number" step="0.001" placeholder="e.g. 136" />
        </div>
        <div class="form-group">
          <label class="label">截止频率 (MHz)</label>
          <input v-model.number="form.stop_mhz" class="num-input" type="number" step="0.001" placeholder="e.g. 174" />
        </div>

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
          预计 {{ channelCount }} 个信道
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
          <div class="stat-label">信道总数</div>
        </div>
        <div class="stat-box stat-free">
          <div class="stat-num text-green">{{ result.free_channels }}</div>
          <div class="stat-label">空闲信道</div>
        </div>
        <div class="stat-box stat-busy">
          <div class="stat-num text-red">{{ result.total_channels - result.free_channels }}</div>
          <div class="stat-label">占用信道</div>
        </div>
        <div class="stat-box">
          <div class="stat-num text-blue">{{ freeRate }}%</div>
          <div class="stat-label">空闲率</div>
        </div>
        <div class="stat-box-right">
          <button class="export-btn" @click="exportCsv">导出 CSV</button>
        </div>
      </div>

      <!-- Occupancy bar chart (ECharts overview) -->
      <div class="chart-card mb24">
        <div class="chart-header">信道占用概览</div>
        <div ref="chartEl" class="chart-area" />
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
import { getStations, computeFreqAssign } from '../api/index.js'

const BW_PRESETS = [12.5, 25, 50, 200]
const FILTERS = [
  { label: '全部',   value: 'all'  },
  { label: '空闲',   value: 'free' },
  { label: '占用',   value: 'busy' },
  { label: '无数据', value: 'nodata' },
]

const stations  = ref([])
const form      = ref({
  station_id: '',
  start_mhz: 136,
  stop_mhz: 174,
  channel_bw_khz: 25,
  threshold_dbm: -90,
  lookback_s: 3600,
})
const loading   = ref(false)
const error     = ref('')
const result    = ref(null)
const filter    = ref('all')
const searchHz  = ref('')
const chartEl   = ref(null)
let chart = null

// ── Derived ───────────────────────────────────────────────────────────────────

const canRun = computed(() => {
  const f = form.value
  return f.station_id && f.start_mhz && f.stop_mhz && f.channel_bw_khz > 0
    && f.stop_mhz > f.start_mhz
})

const channelCount = computed(() => {
  const { start_mhz, stop_mhz, channel_bw_khz } = form.value
  if (!start_mhz || !stop_mhz || !channel_bw_khz) return 0
  return Math.max(1, Math.floor((stop_mhz - start_mhz) * 1000 / channel_bw_khz))
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
    result.value = await computeFreqAssign({
      station_id:    f.station_id,
      start_hz:      f.start_mhz * 1e6,
      stop_hz:       f.stop_mhz  * 1e6,
      channel_bw_hz: f.channel_bw_khz * 1e3,
      threshold_dbm: f.threshold_dbm,
      lookback_s:    f.lookback_s,
    })
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

function buildChart() {
  if (!chartEl.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartEl.value, 'dark')
}

function renderChart(channels) {
  if (!chart) return
  const thresh = form.value.threshold_dbm

  const data = channels.map(c => ({
    value: [c.channel_idx, c.max_dbm ?? (thresh - 30)],
    itemStyle: {
      color: c.max_dbm === null
        ? '#334155'
        : c.free ? '#4ade80' : '#f87171',
    },
  }))

  chart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 60, right: 16, top: 16, bottom: 44 },
    tooltip: {
      formatter: (p) => {
        const ch = channels[p.data.value[0]]
        const dbm = ch.max_dbm !== null ? ch.max_dbm.toFixed(1) + ' dBm' : '无数据'
        return `<span style="color:#94a3b8;font-size:11px">Ch ${ch.channel_idx + 1} · ${(ch.center_hz/1e6).toFixed(4)} MHz</span><br/><b>${dbm}</b><br/><span style="color:${ch.free?'#4ade80':'#f87171'}">${ch.free?'空闲':'占用'}</span>`
      },
      backgroundColor: '#0f172a', borderColor: '#334155', borderWidth: 1,
      textStyle: { color: '#e2e8f0', fontSize: 12 },
    },
    xAxis: {
      type: 'value',
      min: 0, max: channels.length - 1,
      axisLabel: {
        color: '#64748b', fontSize: 10,
        formatter: (v) => {
          const ch = channels[Math.round(v)]
          if (!ch) return ''
          return (ch.center_hz / 1e6).toFixed(2)
        },
        interval: Math.floor(channels.length / 12),
      },
      axisLine: { lineStyle: { color: '#1e293b' } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: 'dBm', nameTextStyle: { color: '#64748b', fontSize: 11 },
      axisLabel: { color: '#64748b', fontSize: 10 },
      axisLine: { lineStyle: { color: '#1e293b' } },
      splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
    },
    series: [{
      type: 'bar',
      data,
      barWidth: Math.max(1, Math.floor(700 / channels.length)),
      barGap: '10%',
      markLine: {
        symbol: ['none', 'none'],
        data: [{ yAxis: thresh }],
        lineStyle: { color: '#fbbf24', type: 'dashed', width: 1.5 },
        label: {
          formatter: `阈值 ${thresh} dBm`,
          color: '#fbbf24', fontSize: 10,
        },
      },
    }],
    dataZoom: [
      { type: 'inside', xAxisIndex: 0 },
      { type: 'slider', xAxisIndex: 0, bottom: 4, height: 22,
        fillerColor: 'rgba(56,189,248,0.08)', borderColor: '#1e293b',
        handleStyle: { color: '#38bdf8', borderColor: '#38bdf8' },
        textStyle: { color: '#64748b', fontSize: 9 },
      },
    ],
  }, true)
}

watch(result, async (r) => {
  if (!r) return
  await nextTick()
  if (!chart) buildChart()
  renderChart(r.channels)
})

function onResize() { chart?.resize() }
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
.freqassign-page { padding-bottom: 32px; }
.mb16 { margin-bottom: 16px; }
.mb20 { margin-bottom: 20px; }
.mb24 { margin-bottom: 24px; }

.page-header { display: flex; align-items: flex-start; }
.page-title  { font-size: 24px; font-weight: 700; color: #f1f5f9; letter-spacing: -0.3px; }
.page-sub    { font-size: 13px; color: #64748b; margin-top: 3px; }

/* ── Form ── */
.form-card {
  background: #0a0f1e; border: 1px solid #1e293b; border-radius: 14px; padding: 20px 22px;
}
.form-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px 20px;
}
.form-group { display: flex; flex-direction: column; gap: 6px; }
.label { font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .4px; }

.select-input, .num-input {
  background: #060c18; border: 1px solid #1e293b; border-radius: 8px;
  color: #e2e8f0; font-size: 13px; padding: 7px 10px; outline: none;
  transition: border-color .15s;
}
.select-input:focus, .num-input:focus { border-color: #334155; }
.num-input::-webkit-inner-spin-button { opacity: .4; }

.input-with-presets { display: flex; flex-direction: column; gap: 6px; }
.bw-presets { display: flex; gap: 4px; flex-wrap: wrap; }
.bw-btn {
  padding: 3px 8px; border-radius: 6px; font-size: 11px;
  border: 1px solid #1e293b; background: transparent; color: #475569; cursor: pointer;
}
.bw-btn:hover  { border-color: #334155; color: #94a3b8; }
.bw-btn.active { background: rgba(56,189,248,0.1); border-color: #38bdf8; color: #38bdf8; }

.slider-wrap   { display: flex; align-items: center; gap: 10px; }
.dbm-slider    { flex: 1; accent-color: #38bdf8; }
.dbm-val       { font-size: 12px; color: #94a3b8; font-variant-numeric: tabular-nums; white-space: nowrap; }

.form-footer {
  display: flex; justify-content: flex-end; align-items: center; gap: 16px;
  margin-top: 18px; padding-top: 16px; border-top: 1px solid #0f172a;
}
.channel-preview { font-size: 12px; color: #475569; }
.run-btn {
  padding: 9px 22px; border-radius: 9px;
  background: rgba(56,189,248,0.12); border: 1px solid rgba(56,189,248,0.4); color: #38bdf8;
  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 8px;
}
.run-btn:hover:not(:disabled) { background: rgba(56,189,248,0.22); }
.run-btn:disabled { opacity: .5; cursor: not-allowed; }
.spinner {
  width: 14px; height: 14px; border: 2px solid #1e293b; border-top-color: #38bdf8;
  border-radius: 50%; animation: spin .7s linear infinite; display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Error ── */
.error-bar {
  background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25);
  border-radius: 10px; padding: 10px 16px; color: #f87171; font-size: 13px;
}

/* ── Summary ── */
.summary-row {
  display: flex; gap: 12px; align-items: stretch; flex-wrap: wrap;
}
.stat-box {
  background: #080e1c; border: 1px solid #1e293b; border-radius: 12px;
  padding: 14px 20px; text-align: center; min-width: 90px;
}
.stat-num   { font-size: 26px; font-weight: 700; color: #e2e8f0; line-height: 1; }
.stat-label { font-size: 11px; color: #475569; margin-top: 4px; }
.text-green { color: #4ade80 !important; }
.text-red   { color: #f87171 !important; }
.text-blue  { color: #38bdf8 !important; }
.stat-box-right { flex: 1; display: flex; align-items: center; justify-content: flex-end; }
.export-btn {
  padding: 8px 16px; border-radius: 8px;
  border: 1px solid #1e293b; background: transparent; color: #64748b;
  font-size: 12px; cursor: pointer; transition: all .15s;
}
.export-btn:hover { border-color: #38bdf8; color: #38bdf8; }

/* ── Chart ── */
.chart-card {
  background: #0a0f1e; border: 1px solid #1e293b; border-radius: 14px; overflow: hidden;
}
.chart-header {
  padding: 12px 18px; font-size: 13px; color: #64748b; font-weight: 500;
  border-bottom: 1px solid #1e293b;
}
.chart-area { width: 100%; height: 240px; }

/* ── Filter bar ── */
.filter-bar  { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.filter-tabs { display: flex; gap: 4px; }
.filter-tab {
  padding: 5px 12px; border-radius: 8px; font-size: 12px;
  border: 1px solid #1e293b; background: transparent; color: #475569; cursor: pointer;
}
.filter-tab:hover  { border-color: #334155; color: #94a3b8; }
.filter-tab.active { background: rgba(56,189,248,0.08); border-color: #38bdf8; color: #38bdf8; }
.search-input {
  background: #060c18; border: 1px solid #1e293b; border-radius: 8px;
  color: #e2e8f0; font-size: 12px; padding: 5px 10px; outline: none; min-width: 170px;
}

/* ── Channel table ── */
.table-card {
  background: #080e1c; border: 1px solid #1e293b; border-radius: 14px; overflow: hidden;
}
.chan-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.chan-table th {
  background: #060c18; padding: 9px 16px;
  text-align: left; font-size: 11px; font-weight: 600;
  color: #475569; text-transform: uppercase; letter-spacing: .4px;
  border-bottom: 1px solid #1e293b;
}
.chan-table td { padding: 9px 16px; border-bottom: 1px solid #0f172a; color: #94a3b8; }
.chan-row:last-child td { border-bottom: none; }
.chan-row:hover td { background: rgba(255,255,255,0.01); }

.cell-idx    { color: #475569; font-size: 12px; }
.cell-center { font-weight: 600; color: #e2e8f0; font-variant-numeric: tabular-nums; }
.cell-range  { font-size: 11px; color: #475569; font-variant-numeric: tabular-nums; }
.cell-dbm    { font-weight: 600; font-variant-numeric: tabular-nums; }

.status-badge {
  display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 11px; font-weight: 600;
  border: 1px solid;
}
.badge-free { background: rgba(74,222,128,0.08); border-color: rgba(74,222,128,0.3); color: #4ade80; }
.badge-busy { background: rgba(248,113,113,0.08); border-color: rgba(248,113,113,0.3); color: #f87171; }

.table-empty { padding: 24px; text-align: center; color: #334155; font-size: 13px; }
</style>
