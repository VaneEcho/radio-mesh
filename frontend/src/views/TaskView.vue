<template>
  <div class="task-page">
    <div class="page-header mb24">
      <div>
        <h2 class="page-title">任务下发</h2>
        <p class="page-sub">向边缘站点下发专项扫描任务，实时跟踪执行进度</p>
      </div>
      <button class="new-btn" @click="openCreateDialog">+ 新建任务</button>
    </div>

    <!-- ── Task list ── -->
    <div class="table-card">
      <div class="table-topbar">
        <span class="table-title">历史任务</span>
        <button class="refresh-btn" :class="{ spinning: listLoading }" @click="fetchList">↻</button>
      </div>
      <div v-if="listLoading && tasks.length === 0" class="loading-row">加载中…</div>
      <div v-if="!listLoading && tasks.length === 0" class="empty-row">暂无任务记录</div>

      <table v-if="tasks.length > 0" class="task-table">
        <thead>
          <tr>
            <th>任务 ID</th>
            <th>类型</th>
            <th>状态</th>
            <th>站点</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="t in tasks" :key="t.task_id">
            <tr class="task-row" @click="toggleDetail(t.task_id)">
              <td class="cell-id">{{ t.task_id }}</td>
              <td><span class="type-badge">{{ t.type }}</span></td>
              <td><span class="status-dot" :class="t.status" />{{ statusLabel(t.status) }}</td>
              <td class="cell-stations">
                {{ t.completed_count }}/{{ t.station_count }} 完成
              </td>
              <td class="cell-ts">{{ fmtTime(t.created_at) }}</td>
              <td class="cell-action">
                <button class="expand-btn" :class="{ open: expanded === t.task_id }">▾</button>
              </td>
            </tr>
            <!-- Expanded detail row -->
            <tr v-if="expanded === t.task_id" class="detail-row">
              <td colspan="6">
                <div class="detail-panel">
                  <div v-if="detailLoading" class="detail-loading">加载中…</div>
                  <template v-else-if="detail">
                    <div class="detail-params">
                      <span class="dp-label">参数：</span>
                      <code class="dp-val">{{ detail.params }}</code>
                    </div>
                    <div class="station-list">
                      <div v-for="s in detail.stations" :key="s.station_id" class="station-item">
                        <div class="si-header">
                          <span class="si-id">{{ s.station_id }}</span>
                          <span class="si-status" :class="s.status">{{ statusLabel(s.status) }}</span>
                          <span v-if="s.finished_at" class="si-ts">{{ fmtTime(s.finished_at) }}</span>
                        </div>
                        <div v-if="s.error" class="si-error">⚠ {{ s.error }}</div>
                        <div v-if="s.result_meta" class="si-meta">{{ s.result_meta }}</div>
                        <!-- Spectrum preview chart -->
                        <div v-if="s.result_b64" class="si-chart-wrap">
                          <SpectrumMini :b64="s.result_b64" :meta="parseJson(s.result_meta)" />
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- ── Create task dialog ── -->
    <div v-if="showCreate" class="dialog-backdrop" @click.self="showCreate = false">
      <div class="dialog">
        <div class="dialog-header">
          <h3>新建扫描任务</h3>
          <button class="close-btn" @click="showCreate = false">✕</button>
        </div>
        <div class="dialog-body">

          <!-- Task type -->
          <div class="field">
            <label class="field-label">任务类型</label>
            <div class="type-tabs">
              <button v-for="tp in TASK_TYPES" :key="tp.value"
                class="type-tab"
                :class="{ active: newTask.type === tp.value }"
                @click="newTask.type = tp.value">
                {{ tp.label }}
              </button>
            </div>
          </div>

          <!-- Target stations -->
          <div class="field">
            <label class="field-label">目标站点 <span class="req">*</span></label>
            <div class="station-checks">
              <label v-for="s in stations" :key="s.station_id" class="stn-check">
                <input type="checkbox" :value="s.station_id" v-model="newTask.station_ids" />
                <span :class="s.online ? 'online' : 'offline'">● </span>
                {{ s.name || s.station_id }}
              </label>
            </div>
          </div>

          <!-- Params (band_scan) -->
          <template v-if="newTask.type === 'band_scan'">
            <div class="field-row">
              <div class="field">
                <label class="field-label">起始频率 (MHz)</label>
                <input v-model.number="p.start_mhz" class="num-input" type="number" step="1" />
              </div>
              <div class="field">
                <label class="field-label">截止频率 (MHz)</label>
                <input v-model.number="p.stop_mhz" class="num-input" type="number" step="1" />
              </div>
              <div class="field">
                <label class="field-label">步进 (kHz)</label>
                <input v-model.number="p.step_khz" class="num-input" type="number" step="1" />
              </div>
            </div>
          </template>

          <!-- Params (channel_scan) -->
          <template v-if="newTask.type === 'channel_scan'">
            <div class="field-row">
              <div class="field">
                <label class="field-label">起始频率 (MHz)</label>
                <input v-model.number="p.start_mhz" class="num-input" type="number" step="1" />
              </div>
              <div class="field">
                <label class="field-label">截止频率 (MHz)</label>
                <input v-model.number="p.stop_mhz" class="num-input" type="number" step="1" />
              </div>
              <div class="field">
                <label class="field-label">信道间距 (kHz)</label>
                <input v-model.number="p.step_khz" class="num-input" type="number" step="1" />
              </div>
              <div class="field">
                <label class="field-label">驻留时间 (ms)</label>
                <input v-model.number="p.dwell_ms" class="num-input" type="number" step="1" />
              </div>
            </div>
          </template>

          <!-- Params (if_analysis) -->
          <template v-if="newTask.type === 'if_analysis'">
            <div class="field-row">
              <div class="field">
                <label class="field-label">中心频率 (MHz)</label>
                <input v-model.number="p.center_mhz" class="num-input" type="number" step="0.001" />
              </div>
              <div class="field">
                <label class="field-label">分析带宽 (kHz)</label>
                <input v-model.number="p.span_khz" class="num-input" type="number" step="100" />
              </div>
              <div class="field">
                <label class="field-label">解调带宽 (kHz)</label>
                <input v-model.number="p.demod_bw_khz" class="num-input" type="number" step="1" />
              </div>
              <div class="field">
                <label class="field-label">解调模式</label>
                <select v-model="p.demod_mode" class="num-input">
                  <option>FM</option><option>AM</option><option>USB</option><option>LSB</option>
                </select>
              </div>
            </div>
          </template>

          <div v-if="createError" class="create-error">⚠ {{ createError }}</div>
        </div>
        <div class="dialog-footer">
          <button class="cancel-btn" @click="showCreate = false">取消</button>
          <button class="submit-btn" :disabled="createLoading || !canCreate" @click="submitTask">
            <span v-if="createLoading" class="spinner" />
            <span v-else>下发任务</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, defineComponent, h } from 'vue'
import * as echarts from 'echarts'
import { getStations, listTasks, createTask, getTask } from '../api/index.js'

const TASK_TYPES = [
  { label: '全频段扫描', value: 'band_scan'    },
  { label: '信道扫描',   value: 'channel_scan' },
  { label: 'IF 分析',    value: 'if_analysis'  },
]

const tasks       = ref([])
const listLoading = ref(false)
const expanded    = ref(null)
const detail      = ref(null)
const detailLoading = ref(false)
const stations    = ref([])
const showCreate  = ref(false)
const createLoading = ref(false)
const createError = ref('')

const newTask = ref({ type: 'band_scan', station_ids: [] })
const p       = ref({
  start_mhz: 20, stop_mhz: 3600, step_khz: 25,
  dwell_ms: 50, center_mhz: 100, span_khz: 200, demod_bw_khz: 15, demod_mode: 'FM',
})

const canCreate = computed(() =>
  newTask.value.station_ids.length > 0
)

// ── Data fetching ─────────────────────────────────────────────────────────────

async function fetchList() {
  listLoading.value = true
  try {
    const data = await listTasks()
    tasks.value = data.tasks
  } catch (_) {} finally {
    listLoading.value = false
  }
}

async function toggleDetail(taskId) {
  if (expanded.value === taskId) { expanded.value = null; detail.value = null; return }
  expanded.value = taskId
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = await getTask(taskId)
  } finally {
    detailLoading.value = false
  }
}

let refreshTimer = null
onMounted(async () => {
  fetchList()
  const data = await getStations()
  stations.value = data
  refreshTimer = setInterval(fetchList, 10_000)
})
onUnmounted(() => clearInterval(refreshTimer))

// ── Create task ───────────────────────────────────────────────────────────────

function openCreateDialog() {
  newTask.value = { type: 'band_scan', station_ids: [] }
  createError.value = ''
  showCreate.value = true
}

function buildParams() {
  const pp = p.value
  const t = newTask.value.type
  if (t === 'band_scan') return {
    start_hz: pp.start_mhz * 1e6,
    stop_hz:  pp.stop_mhz  * 1e6,
    step_hz:  pp.step_khz  * 1e3,
  }
  if (t === 'channel_scan') return {
    start_hz: pp.start_mhz * 1e6,
    stop_hz:  pp.stop_mhz  * 1e6,
    step_hz:  pp.step_khz  * 1e3,
    dwell_s:  pp.dwell_ms  / 1000,
  }
  if (t === 'if_analysis') return {
    center_hz:    pp.center_mhz  * 1e6,
    span_hz:      pp.span_khz    * 1e3,
    demod_bw_hz:  pp.demod_bw_khz* 1e3,
    demod_mode:   pp.demod_mode,
  }
}

async function submitTask() {
  createLoading.value = true
  createError.value = ''
  try {
    const resp = await createTask({
      type: newTask.value.type,
      params: buildParams(),
      station_ids: newTask.value.station_ids,
      stream_fps: 0,
    })
    showCreate.value = false
    await fetchList()
    // Auto-expand the new task
    expanded.value = resp.task_id
    detailLoading.value = true
    detail.value = await getTask(resp.task_id)
    detailLoading.value = false
  } catch (e) {
    createError.value = e.response?.data?.detail || e.message
  } finally {
    createLoading.value = false
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_LABELS = {
  pending: '待下发', dispatched: '已下发', running: '执行中',
  completed: '已完成', failed: '失败',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }

function fmtTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('zh-CN', { hour12: false })
}

function parseJson(s) {
  try { return JSON.parse(s) } catch { return null }
}

// ── Mini spectrum chart component ─────────────────────────────────────────────

const SpectrumMini = defineComponent({
  props: { b64: String, meta: Object },
  setup(props) {
    const el = ref(null)
    let chart = null

    function render() {
      if (!el.value || !props.b64 || !props.meta) return
      if (chart) chart.dispose()
      chart = echarts.init(el.value, 'dark')

      // Decode base64 + gzip + float32
      const binary = atob(props.b64)
      const bytes  = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

      // Decompress gzip using DecompressionStream
      const ds = new DecompressionStream('gzip')
      const writer = ds.writable.getWriter()
      writer.write(bytes)
      writer.close()
      new Response(ds.readable).arrayBuffer().then(buf => {
        const floats = new Float32Array(buf)
        const step = props.meta.freq_step_hz ?? 25_000
        const f0   = props.meta.freq_start_hz ?? 20e6
        const data = []
        for (let i = 0; i < floats.length; i++) {
          data.push([(f0 + i * step) / 1e6, Math.round(floats[i] * 10) / 10])
        }
        chart.setOption({
          backgroundColor: 'transparent',
          animation: false,
          grid: { left: 52, right: 8, top: 4, bottom: 24 },
          xAxis: {
            type: 'value', min: 'dataMin', max: 'dataMax',
            axisLabel: { color: '#64748b', fontSize: 9, formatter: v => v.toFixed(0) + '' },
            axisLine: { lineStyle: { color: '#1e293b' } },
            splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          },
          yAxis: {
            type: 'value',
            axisLabel: { color: '#64748b', fontSize: 9 },
            axisLine: { lineStyle: { color: '#1e293b' } },
            splitLine: { lineStyle: { color: '#1e293b', type: 'dashed' } },
          },
          series: [{
            type: 'line', data,
            symbol: 'none', sampling: 'lttb',
            lineStyle: { color: '#38bdf8', width: 1 },
            areaStyle: {
              color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(56,189,248,0.18)' },
                  { offset: 1, color: 'rgba(56,189,248,0)' },
                ]},
            },
          }],
        }, true)
      })
    }

    return () => h('div', { ref: el, style: 'width:100%;height:160px', onVnodeMounted: render })
  },
})
</script>

<style scoped>
.task-page { padding-bottom: 32px; }
.mb24 { margin-bottom: 24px; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; }
.page-title  { font-size: 24px; font-weight: 700; color: #f1f5f9; }
.page-sub    { font-size: 13px; color: #64748b; margin-top: 3px; }

.new-btn {
  padding: 9px 18px; border-radius: 9px;
  background: rgba(56,189,248,0.12); border: 1px solid rgba(56,189,248,0.4); color: #38bdf8;
  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
}
.new-btn:hover { background: rgba(56,189,248,0.2); }

/* ── Table ── */
.table-card { background: #080e1c; border: 1px solid #1e293b; border-radius: 14px; overflow: hidden; }
.table-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 18px; border-bottom: 1px solid #1e293b;
}
.table-title  { font-size: 13px; color: #64748b; font-weight: 500; }
.refresh-btn  {
  background: none; border: none; color: #475569; font-size: 16px; cursor: pointer;
  transition: transform .3s; line-height: 1;
}
.refresh-btn.spinning { animation: spin .6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.loading-row, .empty-row { padding: 32px; text-align: center; color: #334155; font-size: 13px; }

.task-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.task-table th {
  background: #060c18; padding: 9px 16px;
  text-align: left; font-size: 11px; font-weight: 600;
  color: #475569; text-transform: uppercase; letter-spacing: .4px;
  border-bottom: 1px solid #1e293b;
}
.task-table td { padding: 11px 16px; border-bottom: 1px solid #0a1224; color: #94a3b8; }
.task-row { cursor: pointer; transition: background .1s; }
.task-row:hover td { background: rgba(255,255,255,0.015); }

.type-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 6px; font-weight: 500;
  background: rgba(99,102,241,0.1); border: 1px solid rgba(99,102,241,0.3); color: #818cf8;
}

.status-dot {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  margin-right: 6px; background: #334155;
}
.status-dot.pending    { background: #475569; }
.status-dot.dispatched { background: #fbbf24; }
.status-dot.running    { background: #38bdf8; animation: pulse .9s infinite; }
.status-dot.completed  { background: #4ade80; }
.status-dot.failed     { background: #f87171; }
@keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.4 } }

.cell-id        { font-family: monospace; font-size: 12px; color: #64748b; }
.cell-ts        { font-size: 11px; color: #475569; }
.expand-btn     {
  background: none; border: none; color: #475569; cursor: pointer;
  font-size: 16px; transition: transform .2s;
}
.expand-btn.open { transform: rotate(180deg); }

/* ── Detail panel ── */
.detail-row td { background: #040810 !important; border-bottom: 1px solid #1e293b; }
.detail-panel { padding: 16px 20px; }
.detail-loading { color: #475569; font-size: 13px; }
.detail-params { margin-bottom: 14px; font-size: 12px; }
.dp-label { color: #475569; }
.dp-val   { color: #94a3b8; background: #060c18; padding: 2px 8px; border-radius: 5px; }

.station-list { display: flex; flex-direction: column; gap: 12px; }
.station-item {
  background: #080e1c; border: 1px solid #1e293b; border-radius: 10px; padding: 12px 16px;
}
.si-header { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.si-id     { font-size: 13px; font-weight: 600; color: #e2e8f0; }
.si-status {
  font-size: 11px; padding: 1px 7px; border-radius: 5px;
  background: #1e293b; color: #64748b;
}
.si-status.completed { background: rgba(74,222,128,0.1); color: #4ade80; }
.si-status.failed    { background: rgba(248,113,113,0.1); color: #f87171; }
.si-status.running   { background: rgba(56,189,248,0.1);  color: #38bdf8; }
.si-ts     { font-size: 11px; color: #334155; margin-left: auto; }
.si-error  { font-size: 12px; color: #f87171; padding: 4px 0; }
.si-meta   { font-size: 11px; color: #475569; font-family: monospace; }
.si-chart-wrap { margin-top: 10px; border-radius: 8px; overflow: hidden; background: #040810; }

/* ── Create dialog ── */
.dialog-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,.6); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.dialog {
  background: #0a0f1e; border: 1px solid #1e293b; border-radius: 16px;
  width: 600px; max-width: 95vw; max-height: 90vh; overflow-y: auto;
  display: flex; flex-direction: column;
}
.dialog-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 18px 22px; border-bottom: 1px solid #1e293b;
}
.dialog-header h3 { font-size: 16px; font-weight: 600; color: #e2e8f0; }
.close-btn { background: none; border: none; color: #475569; cursor: pointer; font-size: 16px; }
.close-btn:hover { color: #94a3b8; }
.dialog-body   { padding: 20px 22px; display: flex; flex-direction: column; gap: 18px; }
.dialog-footer {
  padding: 14px 22px; border-top: 1px solid #1e293b;
  display: flex; justify-content: flex-end; gap: 10px;
}

.field       { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .4px; }
.req         { color: #f87171; }
.field-row   { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 12px; }

.type-tabs { display: flex; gap: 6px; }
.type-tab {
  padding: 7px 14px; border-radius: 8px; font-size: 13px;
  border: 1px solid #1e293b; background: transparent; color: #64748b; cursor: pointer;
}
.type-tab:hover  { border-color: #334155; color: #94a3b8; }
.type-tab.active { background: rgba(56,189,248,0.1); border-color: #38bdf8; color: #38bdf8; }

.station-checks { display: flex; flex-wrap: wrap; gap: 8px; }
.stn-check { display: flex; align-items: center; gap: 5px; font-size: 13px; color: #94a3b8; cursor: pointer; }
.stn-check input { accent-color: #38bdf8; }
.online  { color: #4ade80; }
.offline { color: #334155; }

.num-input, select.num-input {
  background: #060c18; border: 1px solid #1e293b; border-radius: 8px;
  color: #e2e8f0; font-size: 13px; padding: 7px 10px; outline: none;
}

.create-error { color: #f87171; font-size: 12px; padding: 8px 12px; background: rgba(239,68,68,0.07); border-radius: 8px; }
.cancel-btn {
  padding: 8px 18px; border-radius: 8px; background: transparent;
  border: 1px solid #1e293b; color: #64748b; cursor: pointer;
}
.submit-btn {
  padding: 8px 20px; border-radius: 8px;
  background: rgba(56,189,248,0.12); border: 1px solid rgba(56,189,248,0.4); color: #38bdf8;
  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 8px;
}
.submit-btn:hover:not(:disabled) { background: rgba(56,189,248,0.2); }
.submit-btn:disabled { opacity: .5; cursor: not-allowed; }
.spinner {
  width: 13px; height: 13px; border: 2px solid #1e293b; border-top-color: #38bdf8;
  border-radius: 50%; animation: spin .7s linear infinite; display: inline-block;
}
</style>
