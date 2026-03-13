<template>
  <div>
    <div class="page-header mb24">
      <div>
        <h2 class="page-title">频段规则</h2>
        <p class="page-sub">基于《无线电频率划分规定》（工信部令第 62 号）的频段定义</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openAdd">新增规则</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon closable class="mb24" />

    <el-card shadow="never">
      <el-table
        :data="rules"
        v-loading="loading"
        stripe
        size="small"
        :row-style="{ background: 'transparent' }"
        style="width:100%; background: transparent"
      >
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="起始频率" width="130">
          <template #default="{ row }">{{ mhz(row.freq_start_hz) }} MHz</template>
        </el-table-column>
        <el-table-column label="截止频率" width="130">
          <template #default="{ row }">{{ mhz(row.freq_stop_hz) }} MHz</template>
        </el-table-column>
        <el-table-column prop="service" label="业务类型" min-width="120" />
        <el-table-column prop="authority" label="主管部门" width="120">
          <template #default="{ row }">{{ row.authority || '—' }}</template>
        </el-table-column>
        <el-table-column prop="notes" label="备注" min-width="160">
          <template #default="{ row }">{{ row.notes || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确认删除此规则？" @confirm="remove(row.rule_id)">
              <template #reference>
                <el-button size="small" text type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ── Add / Edit dialog ── -->
    <el-dialog v-model="dialogVisible" :title="editTarget ? '编辑规则' : '新增规则'"
      width="480px" align-center>
      <el-form :model="form" label-width="90px" size="default">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="FM 广播" />
        </el-form-item>
        <el-form-item label="起始 (MHz)">
          <el-input-number v-model="form.freq_start_mhz" :precision="3" :step="0.1" style="width:100%" />
        </el-form-item>
        <el-form-item label="截止 (MHz)">
          <el-input-number v-model="form.freq_stop_mhz"  :precision="3" :step="0.1" style="width:100%" />
        </el-form-item>
        <el-form-item label="业务类型">
          <el-input v-model="form.service" placeholder="广播" />
        </el-form-item>
        <el-form-item label="主管部门">
          <el-input v-model="form.authority" placeholder="国家广播电视总局" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getBandRules, createBandRule, updateBandRule, deleteBandRule } from '../api/index.js'

const rules   = ref([])
const loading = ref(false)
const error   = ref('')
const saving  = ref(false)

const dialogVisible = ref(false)
const editTarget    = ref(null)
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
      ElMessage.success('已更新')
    } else {
      await createBandRule(payload)
      ElMessage.success('已新增')
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function remove(ruleId) {
  try {
    await deleteBandRule(ruleId)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error('删除失败：' + e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.mb24 { margin-bottom: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; }
.page-title  { font-size: 22px; font-weight: 600; color: #e2e8f0; }
.page-sub    { font-size: 13px; color: #718096; margin-top: 4px; }

:deep(.el-card) {
  background: #1a1f2e;
  border-color: #2d3748;
  --el-card-bg-color: #1a1f2e;
}
:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: #141824;
  --el-table-border-color: #2d3748;
  --el-table-text-color: #a0aec0;
  --el-table-header-text-color: #718096;
  --el-table-row-hover-bg-color: #252b3b;
}
:deep(.el-table__inner-wrapper::before) { display: none; }
</style>
