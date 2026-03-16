<template>
  <div class="sl-view">

    <!-- ── Header ── -->
    <div class="sl-header">
      <div>
        <h1 class="page-title">信号库</h1>
        <p class="page-sub">管理已识别/登记的无线电信号，支持按频率检索</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">+ 添加信号</button>
    </div>

    <!-- ── Filter bar ── -->
    <div class="filter-bar card">
      <input v-model="search" class="inp-search" placeholder="搜索名称 / 业务 / 调制方式…" />
      <select v-model="filterStatus" class="sel-sm">
        <option value="">全部状态</option>
        <option value="active">有效</option>
        <option value="archived">已归档</option>
      </select>
      <button class="btn btn-sm" @click="loadSignals">刷新</button>
      <span class="count-hint">共 {{ filtered.length }} 条</span>
    </div>

    <!-- ── Signal table ── -->
    <div class="table-card card">
      <div v-if="filtered.length === 0" class="empty">暂无信号记录</div>

      <div v-else class="tbl-wrap">
        <table class="stbl">
          <thead>
            <tr>
              <th>ID</th>
              <th>名称</th>
              <th>中心频率</th>
              <th>带宽</th>
              <th>调制</th>
              <th>业务</th>
              <th>站点</th>
              <th>最大电平</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in paginated" :key="r.signal_id" class="srow">
              <td class="mono">#{{ r.signal_id }}</td>
              <td class="name-cell">{{ r.name }}</td>
              <td class="mono">{{ (r.freq_center_hz / 1e6).toFixed(4) }} MHz</td>
              <td class="mono">{{ fmtBw(r.bandwidth_hz) }}</td>
              <td>{{ r.modulation || '--' }}</td>
              <td>{{ r.service || '--' }}</td>
              <td>{{ r.station_id || '--' }}</td>
              <td class="mono" :class="r.max_dbm != null && r.max_dbm > -70 ? 'strong' : ''">
                {{ r.max_dbm != null ? r.max_dbm.toFixed(1) + ' dBm' : '--' }}
              </td>
              <td>
                <span class="status-chip" :class="`sc-${r.status}`">
                  {{ r.status === 'active' ? '有效' : '归档' }}
                </span>
              </td>
              <td class="row-actions">
                <button class="btn-link" @click="openEdit(r)">编辑</button>
                <button class="btn-link" v-if="r.status === 'active'" @click="doArchive(r)">归档</button>
                <button class="btn-link red" @click="doDelete(r)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="pagination" v-if="totalPages > 1">
        <button class="btn btn-sm" :disabled="page <= 1" @click="page--">上一页</button>
        <span class="page-info">{{ page }} / {{ totalPages }}</span>
        <button class="btn btn-sm" :disabled="page >= totalPages" @click="page++">下一页</button>
      </div>
    </div>

    <!-- ── Create / Edit dialog ── -->
    <div v-if="dialog.open" class="dialog-overlay" @click.self="dialog.open = false">
      <div class="dialog card">
        <div class="dialog-title">{{ dialog.mode === 'create' ? '添加信号' : '编辑信号' }}</div>

        <div class="form-grid">
          <div class="fg">
            <label>名称 *</label>
            <input v-model="dialog.form.name" class="inp" />
          </div>
          <div class="fg">
            <label>中心频率 (MHz) *</label>
            <input type="number" v-model.number="dialog.form.freq_center_mhz" class="inp" step="0.001" />
          </div>
          <div class="fg">
            <label>带宽 (kHz)</label>
            <input type="number" v-model.number="dialog.form.bandwidth_khz" class="inp" step="0.1" />
          </div>
          <div class="fg">
            <label>调制方式</label>
            <input v-model="dialog.form.modulation" class="inp" placeholder="AM / FM / SSB / CW / OFDM…" />
          </div>
          <div class="fg">
            <label>业务类型</label>
            <input v-model="dialog.form.service" class="inp" placeholder="FM 广播 / 航空 VHF…" />
          </div>
          <div class="fg">
            <label>管理机构</label>
            <input v-model="dialog.form.authority" class="inp" />
          </div>
          <div class="fg">
            <label>关联站点</label>
            <select v-model="dialog.form.station_id" class="inp">
              <option value="">不关联</option>
              <option v-for="s in stations" :key="s.station_id" :value="s.station_id">
                {{ s.name || s.station_id }}
              </option>
            </select>
          </div>
          <div class="fg">
            <label>最大电平 (dBm)</label>
            <input type="number" v-model.number="dialog.form.max_dbm" class="inp" step="0.1" />
          </div>
          <div class="fg full">
            <label>备注</label>
            <input v-model="dialog.form.notes" class="inp" />
          </div>
        </div>

        <div class="dialog-actions">
          <button class="btn" @click="dialog.open = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveDialog">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  getStations, listSignals, createSignal, updateSignal, archiveSignal, deleteSignal,
} from '../api/index.js'

// ── Load data ──────────────────────────────────────────────────────────────

const stations = ref([])
const signals  = ref([])

onMounted(async () => {
  try { stations.value = await getStations() } catch { /* ignore */ }
  await loadSignals()
})

async function loadSignals() {
  try {
    const res = await listSignals(null, 1000)
    signals.value = res.records || []
  } catch { /* ignore */ }
}

// ── Filtering / pagination ─────────────────────────────────────────────────

const search       = ref('')
const filterStatus = ref('')
const page         = ref(1)
const pageSize     = 20

const filtered = computed(() => {
  let list = signals.value
  if (filterStatus.value) list = list.filter(r => r.status === filterStatus.value)
  const q = search.value.trim().toLowerCase()
  if (q) list = list.filter(r =>
    (r.name || '').toLowerCase().includes(q) ||
    (r.service || '').toLowerCase().includes(q) ||
    (r.modulation || '').toLowerCase().includes(q)
  )
  return list
})

const totalPages = computed(() => Math.ceil(filtered.value.length / pageSize))

const paginated = computed(() => {
  const start = (page.value - 1) * pageSize
  return filtered.value.slice(start, start + pageSize)
})

// ── Dialog ─────────────────────────────────────────────────────────────────

const saving = ref(false)
const dialog = ref({
  open: false,
  mode: 'create',  // 'create' | 'edit'
  editId: null,
  form: emptyForm(),
})

function emptyForm() {
  return {
    name: '',
    freq_center_mhz: null,
    bandwidth_khz: null,
    modulation: '',
    service: '',
    authority: '',
    station_id: '',
    max_dbm: null,
    notes: '',
  }
}

function openCreate() {
  dialog.value = { open: true, mode: 'create', editId: null, form: emptyForm() }
}

function openEdit(r) {
  dialog.value = {
    open: true,
    mode: 'edit',
    editId: r.signal_id,
    form: {
      name: r.name,
      freq_center_mhz: +(r.freq_center_hz / 1e6).toFixed(6),
      bandwidth_khz: r.bandwidth_hz != null ? +(r.bandwidth_hz / 1e3).toFixed(3) : null,
      modulation: r.modulation || '',
      service: r.service || '',
      authority: r.authority || '',
      station_id: r.station_id || '',
      max_dbm: r.max_dbm,
      notes: r.notes || '',
    },
  }
}

async function saveDialog() {
  const f = dialog.value.form
  if (!f.name || !f.freq_center_mhz) {
    alert('名称和中心频率为必填项')
    return
  }
  saving.value = true
  try {
    const body = {
      name: f.name,
      freq_center_hz: f.freq_center_mhz * 1e6,
      bandwidth_hz: f.bandwidth_khz != null ? f.bandwidth_khz * 1e3 : null,
      modulation: f.modulation || null,
      service: f.service || null,
      authority: f.authority || null,
      station_id: f.station_id || null,
      max_dbm: f.max_dbm,
      notes: f.notes || null,
    }
    if (dialog.value.mode === 'create') {
      await createSignal(body)
    } else {
      await updateSignal(dialog.value.editId, body)
    }
    dialog.value.open = false
    await loadSignals()
  } catch (e) {
    alert('保存失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function doArchive(r) {
  if (!confirm(`归档信号「${r.name}」？`)) return
  try {
    await archiveSignal(r.signal_id)
    r.status = 'archived'
  } catch (e) {
    alert('操作失败：' + e.message)
  }
}

async function doDelete(r) {
  if (!confirm(`永久删除信号「${r.name}」？此操作不可撤销。`)) return
  try {
    await deleteSignal(r.signal_id)
    signals.value = signals.value.filter(s => s.signal_id !== r.signal_id)
  } catch (e) {
    alert('删除失败：' + e.message)
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtBw(hz) {
  if (hz == null) return '--'
  if (hz >= 1e6) return (hz / 1e6).toFixed(2) + ' MHz'
  if (hz >= 1e3) return (hz / 1e3).toFixed(1) + ' kHz'
  return hz.toFixed(0) + ' Hz'
}
</script>

<style scoped>
.sl-view { display: flex; flex-direction: column; gap: 18px; }

.sl-header { display: flex; align-items: flex-start; justify-content: space-between; }
.sl-header h1 { font-size: 22px; font-weight: 700; color: #f1f5f9; }
.sl-header .page-sub { font-size: 13px; color: #475569; margin-top: 4px; }

.card { background: #0a1628; border: 1px solid #1e293b; border-radius: 10px; padding: 18px; }

.filter-bar { display: flex; align-items: center; gap: 10px; padding: 12px 16px; }
.inp-search {
  flex: 1; background: #0f172a; border: 1px solid #1e293b; border-radius: 6px;
  color: #e2e8f0; padding: 7px 12px; font-size: 13px;
}
.inp-search::placeholder { color: #334155; }
.sel-sm { background: #0f172a; border: 1px solid #1e293b; border-radius: 5px; color: #e2e8f0; padding: 6px 9px; font-size: 12px; }
.count-hint { font-size: 12px; color: #334155; white-space: nowrap; }

.btn { padding: 7px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid transparent; }
.btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-primary { background: #0ea5e9; color: #fff; border-color: #0ea5e9; }
.btn-sm { padding: 5px 12px; font-size: 12px; background: #1e293b; color: #94a3b8; border-color: #1e293b; }

.table-card { padding: 0; overflow: hidden; }
.tbl-wrap { overflow-x: auto; }
.stbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.stbl th { padding: 9px 14px; text-align: left; font-size: 11px; color: #475569; border-bottom: 1px solid #1e293b; white-space: nowrap; }
.stbl td { padding: 9px 14px; border-bottom: 1px solid #0f172a; white-space: nowrap; }
.srow:hover { background: rgba(255,255,255,0.02); }
.mono { font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.name-cell { font-weight: 500; color: #e2e8f0; }
.strong { color: #fb923c; }
.row-actions { display: flex; gap: 10px; }
.btn-link { background: none; border: none; cursor: pointer; font-size: 12px; color: #38bdf8; padding: 0; }
.btn-link.red { color: #f87171; }

.status-chip { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.sc-active { background: rgba(34,197,94,0.12); color: #22c55e; }
.sc-archived { background: rgba(100,116,139,0.12); color: #64748b; }

.pagination { display: flex; align-items: center; gap: 10px; padding: 12px 18px; border-top: 1px solid #1e293b; }
.page-info { font-size: 12px; color: #475569; }

.empty { padding: 40px; text-align: center; color: #334155; }

/* Dialog */
.dialog-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.dialog { width: 680px; max-width: 95vw; max-height: 90vh; overflow-y: auto; }
.dialog-title { font-size: 15px; font-weight: 600; color: #f1f5f9; margin-bottom: 18px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; }
.fg { display: flex; flex-direction: column; gap: 5px; }
.fg.full { grid-column: 1 / -1; }
.fg label { font-size: 12px; color: #64748b; }
.inp { background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; color: #e2e8f0; padding: 7px 10px; font-size: 13px; width: 100%; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
</style>
