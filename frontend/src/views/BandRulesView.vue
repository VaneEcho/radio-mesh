<template>
  <div class="bandrules-page">
    <div class="page-header mb28">
      <div>
        <h2 class="page-title">频段规则</h2>
        <p class="page-sub">基于《无线电频率划分规定》（工信部令第 62 号）的频段定义</p>
      </div>
      <button class="add-btn" @click="openAdd">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="14" height="14">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        新增规则
      </button>
    </div>

    <div v-if="error" class="error-bar mb20">⚠ {{ error }}</div>

    <div class="table-card">
      <div v-if="loading" class="loading-overlay">
        <span class="spinner" />
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>起始频率</th>
            <th>截止频率</th>
            <th>业务类型</th>
            <th>主管部门</th>
            <th>备注</th>
            <th style="width:100px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="rules.length === 0 && !loading">
            <td colspan="7" class="empty-row">暂无频段规则</td>
          </tr>
          <tr v-for="row in rules" :key="row.rule_id" class="data-row">
            <td class="cell-name">{{ row.name }}</td>
            <td class="cell-freq">{{ mhz(row.freq_start_hz) }} <span class="unit">MHz</span></td>
            <td class="cell-freq">{{ mhz(row.freq_stop_hz) }} <span class="unit">MHz</span></td>
            <td>{{ row.service }}</td>
            <td class="cell-muted">{{ row.authority || '—' }}</td>
            <td class="cell-muted">{{ row.notes || '—' }}</td>
            <td class="cell-actions">
              <button class="tbl-btn edit-btn" @click="openEdit(row)">编辑</button>
              <button class="tbl-btn del-btn" @click="confirmDelete(row)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ── Add / Edit dialog ── -->
    <div v-if="dialogVisible" class="dialog-overlay" @click.self="dialogVisible = false">
      <div class="dialog-box">
        <div class="dialog-header">
          <span>{{ editTarget ? '编辑规则' : '新增规则' }}</span>
          <button class="dialog-close" @click="dialogVisible = false">×</button>
        </div>
        <div class="dialog-body">
          <div class="form-row">
            <label>名称</label>
            <input v-model="form.name" class="form-input" placeholder="FM 广播" />
          </div>
          <div class="form-row two-col">
            <div>
              <label>起始 (MHz)</label>
              <input v-model.number="form.freq_start_mhz" type="number" step="0.001" class="form-input" />
            </div>
            <div>
              <label>截止 (MHz)</label>
              <input v-model.number="form.freq_stop_mhz" type="number" step="0.001" class="form-input" />
            </div>
          </div>
          <div class="form-row">
            <label>业务类型</label>
            <input v-model="form.service" class="form-input" placeholder="广播" />
          </div>
          <div class="form-row">
            <label>主管部门</label>
            <input v-model="form.authority" class="form-input" placeholder="国家广播电视总局" />
          </div>
          <div class="form-row">
            <label>备注</label>
            <textarea v-model="form.notes" class="form-input form-textarea" rows="2" />
          </div>
        </div>
        <div class="dialog-footer">
          <button class="dlg-btn cancel-btn" @click="dialogVisible = false">取消</button>
          <button class="dlg-btn save-btn" :disabled="saving" @click="save">
            <span v-if="saving" class="spinner-sm" />
            保存
          </button>
        </div>
      </div>
    </div>

    <!-- ── Delete confirm dialog ── -->
    <div v-if="deleteTarget" class="dialog-overlay" @click.self="deleteTarget = null">
      <div class="dialog-box" style="max-width:360px">
        <div class="dialog-header">
          <span>确认删除</span>
          <button class="dialog-close" @click="deleteTarget = null">×</button>
        </div>
        <div class="dialog-body">
          <p style="color:#94a3b8">确认删除规则 <strong style="color:#e2e8f0">{{ deleteTarget.name }}</strong>？此操作不可撤销。</p>
        </div>
        <div class="dialog-footer">
          <button class="dlg-btn cancel-btn" @click="deleteTarget = null">取消</button>
          <button class="dlg-btn danger-btn" @click="remove">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getBandRules, createBandRule, updateBandRule, deleteBandRule } from '../api/index.js'

const rules   = ref([])
const loading = ref(false)
const error   = ref('')
const saving  = ref(false)

const dialogVisible = ref(false)
const editTarget    = ref(null)
const deleteTarget  = ref(null)
const form = ref(emptyForm())

function emptyForm() {
  return { name: '', freq_start_mhz: 0, freq_stop_mhz: 0, service: '', authority: '', notes: '' }
}
function mhz(hz) { return (hz / 1e6).toFixed(3) }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getBandRules()
    rules.value = res.rules
  } catch (e) {
    error.value = '加载失败：' + e.message
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editTarget.value = null
  form.value = emptyForm()
  dialogVisible.value = true
}
function openEdit(row) {
  editTarget.value = row
  form.value = {
    name:           row.name,
    freq_start_mhz: row.freq_start_hz / 1e6,
    freq_stop_mhz:  row.freq_stop_hz  / 1e6,
    service:        row.service,
    authority:      row.authority || '',
    notes:          row.notes || '',
  }
  dialogVisible.value = true
}
function confirmDelete(row) {
  deleteTarget.value = row
}

async function save() {
  saving.value = true
  try {
    const payload = {
      name:          form.value.name,
      freq_start_hz: form.value.freq_start_mhz * 1e6,
      freq_stop_hz:  form.value.freq_stop_mhz  * 1e6,
      service:       form.value.service,
      authority:     form.value.authority || null,
      notes:         form.value.notes     || null,
    }
    if (editTarget.value) {
      await updateBandRule(editTarget.value.rule_id, payload)
    } else {
      await createBandRule(payload)
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    error.value = '保存失败：' + (e.response?.data?.detail || e.message)
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    await deleteBandRule(deleteTarget.value.rule_id)
    deleteTarget.value = null
    await load()
  } catch (e) {
    error.value = '删除失败：' + e.message
    deleteTarget.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.bandrules-page {}
.mb20 { margin-bottom: 20px; }
.mb28 { margin-bottom: 28px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.page-title { font-size: 24px; font-weight: 700; color: #f1f5f9; letter-spacing: -0.3px; }
.page-sub   { font-size: 13px; color: #64748b; margin-top: 3px; }

.add-btn {
  display: flex; align-items: center; gap: 7px;
  padding: 8px 16px; border-radius: 9px;
  background: rgba(56,189,248,0.1);
  border: 1px solid rgba(56,189,248,0.3);
  color: #38bdf8;
  font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .15s;
}
.add-btn:hover { background: rgba(56,189,248,0.18); }

.error-bar {
  background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25);
  border-radius: 10px; padding: 10px 16px; color: #f87171; font-size: 13px;
}

/* ── Table ── */
.table-card {
  background: #080e1c;
  border: 1px solid #1e293b;
  border-radius: 14px;
  overflow: hidden;
  position: relative;
}
.loading-overlay {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(6,12,24,0.7); z-index: 2; border-radius: 14px;
}
.spinner {
  display: inline-block;
  width: 20px; height: 20px;
  border: 2px solid #1e293b;
  border-top-color: #38bdf8;
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.data-table {
  width: 100%; border-collapse: collapse;
  font-size: 13px;
}
.data-table th {
  background: #060c18;
  padding: 11px 16px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: .5px;
  border-bottom: 1px solid #1e293b;
}
.data-table td {
  padding: 11px 16px;
  color: #94a3b8;
  border-bottom: 1px solid #0f172a;
}
.data-row:hover td { background: rgba(255,255,255,0.015); }
.data-row:last-child td { border-bottom: none; }

.cell-name  { color: #e2e8f0; font-weight: 500; }
.cell-freq  { color: #e2e8f0; font-weight: 500; font-variant-numeric: tabular-nums; }
.unit       { color: #475569; font-size: 11px; font-weight: 400; }
.cell-muted { color: #475569; }

.empty-row  { text-align: center; color: #334155; padding: 40px !important; }

.cell-actions { display: flex; gap: 8px; }
.tbl-btn {
  padding: 3px 10px; border-radius: 6px; font-size: 12px;
  cursor: pointer; border: 1px solid; transition: all .12s;
}
.edit-btn { background: transparent; border-color: #1e293b; color: #64748b; }
.edit-btn:hover { border-color: #38bdf8; color: #38bdf8; }
.del-btn  { background: transparent; border-color: #1e293b; color: #64748b; }
.del-btn:hover { border-color: rgba(239,68,68,0.5); color: #f87171; }

/* ── Dialog ── */
.dialog-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.7);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
}
.dialog-box {
  background: #0a111f;
  border: 1px solid #1e293b;
  border-radius: 16px;
  width: 100%; max-width: 480px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.6);
}
.dialog-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 18px 22px;
  border-bottom: 1px solid #1e293b;
  font-size: 15px; font-weight: 600; color: #e2e8f0;
}
.dialog-close {
  background: none; border: none; color: #475569; font-size: 22px;
  cursor: pointer; line-height: 1; transition: color .12s;
}
.dialog-close:hover { color: #94a3b8; }
.dialog-body { padding: 20px 22px; display: flex; flex-direction: column; gap: 14px; }
.form-row    { display: flex; flex-direction: column; gap: 5px; }
.form-row label { font-size: 12px; color: #64748b; font-weight: 500; }
.form-row.two-col { flex-direction: row; gap: 12px; }
.form-row.two-col > div { flex: 1; display: flex; flex-direction: column; gap: 5px; }
.form-input {
  background: #0f172a; border: 1px solid #1e293b;
  border-radius: 8px; padding: 8px 12px;
  color: #e2e8f0; font-size: 13px;
  outline: none; width: 100%;
  transition: border-color .12s;
}
.form-input:focus { border-color: #38bdf8; }
.form-textarea { resize: vertical; font-family: inherit; }
.dialog-footer {
  display: flex; justify-content: flex-end; gap: 10px;
  padding: 14px 22px;
  border-top: 1px solid #1e293b;
}
.dlg-btn {
  padding: 7px 18px; border-radius: 8px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .15s; border: 1px solid; display: flex; align-items: center; gap: 7px;
}
.cancel-btn { background: transparent; border-color: #1e293b; color: #64748b; }
.cancel-btn:hover { border-color: #334155; color: #94a3b8; }
.save-btn {
  background: rgba(56,189,248,0.12); border-color: rgba(56,189,248,0.4); color: #38bdf8;
}
.save-btn:hover:not(:disabled) { background: rgba(56,189,248,0.2); }
.save-btn:disabled { opacity: .5; cursor: not-allowed; }
.danger-btn {
  background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.4); color: #f87171;
}
.danger-btn:hover { background: rgba(239,68,68,0.18); }
.spinner-sm {
  display: inline-block; width: 12px; height: 12px;
  border: 2px solid rgba(56,189,248,0.3); border-top-color: #38bdf8;
  border-radius: 50%; animation: spin .7s linear infinite;
}
</style>
