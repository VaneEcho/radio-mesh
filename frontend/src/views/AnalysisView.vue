<template>
  <div class="av-view">

    <!-- ── Header ── -->
    <div class="av-header">
      <div>
        <h1 class="page-title">信号分析</h1>
        <p class="page-sub">对历史频谱帧执行信号检测，可选接入 AI 后端生成解读报告</p>
      </div>
      <button class="btn btn-primary" @click="showForm = !showForm">
        {{ showForm ? '收起' : '+ 新建分析' }}
      </button>
    </div>

    <!-- ── New analysis form ── -->
    <div v-if="showForm" class="form-card card">
      <div class="form-title">新建分析任务</div>
      <div class="form-row">
        <div class="form-group">
          <label>站点</label>
          <select v-model="form.station_id" class="sel">
            <option value="" disabled>-- 选择站点 --</option>
            <option v-for="s in stations" :key="s.station_id" :value="s.station_id">
              {{ s.name || s.station_id }}
            </option>
          </select>
        </div>
        <div class="form-group">
          <label>Frame ID（可选，不填则用时间范围）</label>
          <input type="number" v-model.number="form.frame_id" class="inp" placeholder="留空则用时间范围" />
        </div>
        <div class="form-group">
          <label>检测阈值 (dBm)</label>
          <input type="number" v-model.number="form.threshold_dbm" class="inp" step="1" />
        </div>
      </div>

      <div class="form-row" v-if="!form.frame_id">
        <div class="form-group">
          <label>开始时间</label>
          <input type="datetime-local" v-model="form.startDt" class="inp dt" />
        </div>
        <div class="form-group">
          <label>结束时间</label>
          <input type="datetime-local" v-model="form.endDt" class="inp dt" />
        </div>
        <div class="form-group">
          <label>起始频率 (MHz，可选)</label>
          <input type="number" v-model.number="form.freq_start_mhz" class="inp" placeholder="全频段" />
        </div>
        <div class="form-group">
          <label>截止频率 (MHz，可选)</label>
          <input type="number" v-model.number="form.freq_stop_mhz" class="inp" placeholder="全频段" />
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>AI 后端（可选）</label>
          <select v-model="form.ai_backend" class="sel">
            <option value="">仅本地检测</option>
            <option value="local">本地描述</option>
            <option value="claude">Claude API</option>
            <option value="openai">OpenAI API</option>
          </select>
        </div>
        <div class="form-group" v-if="form.ai_backend && form.ai_backend !== 'local'">
          <label>API Key</label>
          <input type="password" v-model="form.ai_api_key" class="inp" placeholder="sk-..." />
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-primary" :disabled="submitting || !form.station_id" @click="submitAnalysis">
          {{ submitting ? '分析中…' : '开始分析' }}
        </button>
      </div>
    </div>

    <!-- ── Analysis list ── -->
    <div class="list-card card">
      <div class="list-toolbar">
        <span class="list-title">分析记录</span>
        <div class="filter-row">
          <select v-model="filterStation" class="sel-sm">
            <option value="">全部站点</option>
            <option v-for="s in stations" :key="s.station_id" :value="s.station_id">
              {{ s.name || s.station_id }}
            </option>
          </select>
          <button class="btn btn-sm" @click="loadAnalyses">刷新</button>
        </div>
      </div>

      <div v-if="analyses.length === 0" class="empty">暂无分析记录</div>

      <div v-else class="analysis-table-wrap">
        <table class="atbl">
          <thead>
            <tr>
              <th>ID</th>
              <th>站点</th>
              <th>时间</th>
              <th>频段</th>
              <th>信号数</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="a in filteredAnalyses"
              :key="a.analysis_id"
              class="arow"
              :class="{ 'arow-active': selectedAnalysis?.analysis_id === a.analysis_id }"
              @click="selectAnalysis(a)"
            >
              <td class="mono">#{{ a.analysis_id }}</td>
              <td>{{ a.station_id }}</td>
              <td class="mono">{{ fmtDate(a.created_at) }}</td>
              <td class="mono">{{ (a.freq_start_hz/1e6).toFixed(1) }}–{{ (a.freq_stop_hz/1e6).toFixed(1) }} MHz</td>
              <td>
                <span class="badge" :class="a.detections.length > 0 ? 'badge-warn' : 'badge-ok'">
                  {{ a.detections.length }}
                </span>
              </td>
              <td>
                <span class="status-chip" :class="`status-${a.status}`">{{ statusLabel(a.status) }}</span>
              </td>
              <td class="actions">
                <button class="btn-link" @click.stop="setStatus(a, 'confirmed')">确认</button>
                <button class="btn-link red" @click.stop="setStatus(a, 'dismissed')">驳回</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Detail panel ── -->
    <div v-if="selectedAnalysis" class="detail-card card">
      <div class="detail-header">
        <span class="detail-title">分析详情 #{{ selectedAnalysis.analysis_id }}</span>
        <button class="btn-icon" @click="selectedAnalysis = null">✕</button>
      </div>

      <!-- Signal detection table -->
      <div v-if="selectedAnalysis.detections.length > 0">
        <div class="section-label">检测到的信号（{{ selectedAnalysis.detections.length }} 个）</div>
        <table class="dtbl">
          <thead>
            <tr>
              <th>中心频率</th>
              <th>频段范围</th>
              <th>带宽</th>
              <th>峰值电平</th>
              <th>频段归属</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(d, i) in selectedAnalysis.detections" :key="i">
              <td class="mono">{{ (d.freq_center_hz/1e6).toFixed(4) }} MHz</td>
              <td class="mono">{{ (d.freq_start_hz/1e6).toFixed(3) }}–{{ (d.freq_stop_hz/1e6).toFixed(3) }} MHz</td>
              <td class="mono">{{ fmtBw(d.bandwidth_hz) }}</td>
              <td class="mono" :class="d.peak_dbm > -70 ? 'strong' : ''">{{ d.peak_dbm.toFixed(1) }} dBm</td>
              <td>{{ d.band_name || '未知' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="no-signals">该频段内未检测到高于阈值的信号</div>

      <!-- AI summary -->
      <div v-if="selectedAnalysis.ai_summary" class="ai-section">
        <div class="section-label">
          AI 解读
          <span class="ai-backend-tag">{{ selectedAnalysis.ai_backend }}</span>
        </div>
        <div class="ai-text">{{ selectedAnalysis.ai_summary }}</div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getStations, runAnalysis, listAnalyses, updateAnalysisStatus } from '../api/index.js'

// ── Stations ───────────────────────────────────────────────────────────────

const stations = ref([])
onMounted(async () => {
  try { stations.value = await getStations() } catch { /* ignore */ }
  await loadAnalyses()
})

// ── Form ───────────────────────────────────────────────────────────────────

const showForm = ref(false)
const submitting = ref(false)

function defaultDt(offsetMs = 0) {
  const d = new Date(Date.now() + offsetMs)
  d.setSeconds(0, 0)
  return d.toISOString().slice(0, 16)
}

const form = ref({
  station_id: '',
  frame_id: null,
  threshold_dbm: -90,
  startDt: defaultDt(-3600_000),
  endDt: defaultDt(),
  freq_start_mhz: null,
  freq_stop_mhz: null,
  ai_backend: '',
  ai_api_key: '',
})

async function submitAnalysis() {
  submitting.value = true
  try {
    const req = {
      station_id: form.value.station_id,
      threshold_dbm: form.value.threshold_dbm,
    }
    if (form.value.frame_id) {
      req.frame_id = form.value.frame_id
    } else {
      req.period_start_ms = new Date(form.value.startDt).getTime()
      req.period_end_ms   = new Date(form.value.endDt).getTime()
      if (form.value.freq_start_mhz) req.freq_start_hz = form.value.freq_start_mhz * 1e6
      if (form.value.freq_stop_mhz)  req.freq_stop_hz  = form.value.freq_stop_mhz  * 1e6
    }
    if (form.value.ai_backend) {
      req.ai_backend = form.value.ai_backend
      req.ai_api_key = form.value.ai_api_key || undefined
    }
    const result = await runAnalysis(req)
    showForm.value = false
    await loadAnalyses()
    selectedAnalysis.value = result
  } catch (e) {
    alert('分析失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    submitting.value = false
  }
}

// ── Analyses list ──────────────────────────────────────────────────────────

const analyses = ref([])
const filterStation = ref('')
const selectedAnalysis = ref(null)

const filteredAnalyses = computed(() =>
  filterStation.value
    ? analyses.value.filter(a => a.station_id === filterStation.value)
    : analyses.value
)

async function loadAnalyses() {
  try {
    const res = await listAnalyses(null, 200)
    analyses.value = res.analyses || []
  } catch { /* ignore */ }
}

function selectAnalysis(a) {
  selectedAnalysis.value = selectedAnalysis.value?.analysis_id === a.analysis_id ? null : a
}

async function setStatus(a, status) {
  try {
    await updateAnalysisStatus(a.analysis_id, status)
    a.status = status
    if (selectedAnalysis.value?.analysis_id === a.analysis_id) {
      selectedAnalysis.value = { ...selectedAnalysis.value, status }
    }
  } catch (e) {
    alert('操作失败：' + e.message)
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(s) {
  if (!s) return '--'
  return new Date(s).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function fmtBw(hz) {
  if (!hz) return '--'
  if (hz >= 1e6) return (hz / 1e6).toFixed(2) + ' MHz'
  if (hz >= 1e3) return (hz / 1e3).toFixed(1) + ' kHz'
  return hz.toFixed(0) + ' Hz'
}

function statusLabel(s) {
  return { new: '待审核', confirmed: '已确认', dismissed: '已驳回' }[s] || s
}
</script>

<style scoped>
.av-view { display: flex; flex-direction: column; gap: 18px; }

.av-header { display: flex; align-items: flex-start; justify-content: space-between; }
.av-header h1 { font-size: 22px; font-weight: 700; color: #f1f5f9; }
.av-header .page-sub { font-size: 13px; color: #475569; margin-top: 4px; }

.card { background: #0a1628; border: 1px solid #1e293b; border-radius: 10px; padding: 18px; }

.form-card .form-title { font-size: 14px; font-weight: 600; color: #94a3b8; margin-bottom: 14px; }
.form-row { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 12px; }
.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-group label { font-size: 12px; color: #64748b; }
.inp { background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; color: #e2e8f0; padding: 7px 10px; font-size: 13px; min-width: 160px; }
.inp.dt { min-width: 190px; }
.sel { background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; color: #e2e8f0; padding: 7px 10px; font-size: 13px; min-width: 160px; }
.form-actions { margin-top: 6px; }

.btn { padding: 7px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: none; }
.btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-primary { background: #0ea5e9; color: #fff; }
.btn-sm { padding: 5px 12px; font-size: 12px; background: #1e293b; color: #94a3b8; }
.sel-sm { background: #0f172a; border: 1px solid #1e293b; border-radius: 5px; color: #e2e8f0; padding: 5px 8px; font-size: 12px; }

.list-card { padding: 0; overflow: hidden; }
.list-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid #1e293b; }
.list-title { font-size: 14px; font-weight: 600; color: #94a3b8; }
.filter-row { display: flex; gap: 8px; align-items: center; }

.analysis-table-wrap { overflow-x: auto; }
.atbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.atbl th { padding: 9px 14px; text-align: left; font-size: 11px; color: #475569; border-bottom: 1px solid #1e293b; white-space: nowrap; }
.atbl td { padding: 9px 14px; border-bottom: 1px solid #0f172a; }
.arow { cursor: pointer; transition: background .1s; }
.arow:hover { background: rgba(255,255,255,0.02); }
.arow-active { background: rgba(56,189,248,0.05); }
.mono { font-family: 'JetBrains Mono', monospace; font-size: 12px; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 700; }
.badge-warn { background: rgba(251,191,36,0.15); color: #fbbf24; }
.badge-ok { background: rgba(34,197,94,0.12); color: #22c55e; }

.status-chip { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.status-new { background: rgba(56,189,248,0.12); color: #38bdf8; }
.status-confirmed { background: rgba(34,197,94,0.12); color: #22c55e; }
.status-dismissed { background: rgba(100,116,139,0.15); color: #64748b; }

.actions { display: flex; gap: 10px; }
.btn-link { background: none; border: none; cursor: pointer; font-size: 12px; color: #38bdf8; padding: 0; }
.btn-link.red { color: #f87171; }

.empty { padding: 40px; text-align: center; color: #334155; }

/* Detail panel */
.detail-card { margin-top: 0; }
.detail-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.detail-title { font-size: 14px; font-weight: 600; color: #94a3b8; }
.btn-icon { background: none; border: none; color: #475569; cursor: pointer; font-size: 16px; }
.section-label { font-size: 12px; color: #64748b; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.ai-backend-tag { background: #1e293b; padding: 1px 7px; border-radius: 4px; font-size: 11px; color: #94a3b8; }

.dtbl { width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 16px; }
.dtbl th { padding: 7px 12px; text-align: left; font-size: 11px; color: #475569; border-bottom: 1px solid #1e293b; }
.dtbl td { padding: 7px 12px; border-bottom: 1px solid #0f172a; }
.strong { color: #fb923c; }

.no-signals { color: #475569; font-size: 13px; padding: 10px 0; }

.ai-section { margin-top: 14px; }
.ai-text {
  background: #0d1b32; border: 1px solid #1e293b; border-radius: 8px;
  padding: 14px; font-size: 13px; color: #94a3b8; line-height: 1.7;
  white-space: pre-wrap;
}
</style>
