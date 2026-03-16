/**
 * RF·MESH API client.
 *
 * All functions return the response data directly (not the Axios response).
 * Errors propagate as-is so the caller can handle them with try/catch or
 * ElMessage.error.
 */
import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 15_000,
})

// ── Stations ──────────────────────────────────────────────────────────────────

/** @returns {Promise<Array<{station_id,name,online,last_seen_ms}>>} */
export function getStations() {
  return http.get('/stations').then(r => r.data)
}

// ── Spectrum ──────────────────────────────────────────────────────────────────

/**
 * Query stored spectrum frames.
 * @param {string} stationId
 * @param {number} startMs  Unix timestamp ms
 * @param {number} endMs    Unix timestamp ms
 * @param {number} [limit=200]
 * @returns {Promise<{rows: Array, total: number}>}
 */
export function querySpectrum(stationId, startMs, endMs, limit = 200) {
  return http.get('/spectrum/query', {
    params: { station_id: stationId, start_ms: startMs, end_ms: endMs, limit },
  }).then(r => r.data)
}

// ── Band rules ─────────────────────────────────────────────────────────────

/** @returns {Promise<{rules: Array, total: number}>} */
export function getBandRules() {
  return http.get('/band-rules').then(r => r.data)
}

/** @param {object} rule */
export function createBandRule(rule) {
  return http.post('/band-rules', rule).then(r => r.data)
}

/** @param {number} ruleId  @param {object} updates */
export function updateBandRule(ruleId, updates) {
  return http.put(`/band-rules/${ruleId}`, updates).then(r => r.data)
}

/** @param {number} ruleId */
export function deleteBandRule(ruleId) {
  return http.delete(`/band-rules/${ruleId}`).then(r => r.data)
}

// ── Freq timeseries ────────────────────────────────────────────────────────

/**
 * Query power levels at a single frequency across all stations.
 * @param {number} freqHz       Frequency in Hz
 * @param {number} startMs      Window start (Unix ms)
 * @param {number} endMs        Window end (Unix ms)
 * @param {string[]} [stationIds]  Filter to specific stations (optional)
 * @returns {Promise<{freq_hz, start_ms, end_ms, stations: Array}>}
 */
export function queryFreqTimeseries(freqHz, startMs, endMs, stationIds = []) {
  return http.get('/spectrum/freq-timeseries', {
    params: {
      freq_hz: freqHz,
      start_ms: startMs,
      end_ms: endMs,
      station_ids: stationIds.join(','),
    },
    timeout: 30_000,   // may need extra time for large time ranges
  }).then(r => r.data)
}

// ── Tasks ──────────────────────────────────────────────────────────────────

/** @returns {Promise<{tasks: Array, total: number}>} */
export function listTasks() {
  return http.get('/tasks').then(r => r.data)
}

/**
 * @param {object} task  { type, params, station_ids, stream_fps }
 * @returns {Promise<{task_id, dispatched, not_connected}>}
 */
export function createTask(task) {
  return http.post('/tasks', task).then(r => r.data)
}

/** @param {string} taskId */
export function getTask(taskId) {
  return http.get(`/tasks/${taskId}`).then(r => r.data)
}

// ── Freq assign ────────────────────────────────────────────────────────────

/**
 * Compute free channel list from stored spectrum data.
 * @param {object} req  { station_id, start_hz, stop_hz, channel_bw_hz, threshold_dbm, lookback_s }
 * @returns {Promise<{total_channels, free_channels, channels: Array}>}
 */
export function computeFreqAssign(req) {
  return http.post('/freq-assign', req, { timeout: 60_000 }).then(r => r.data)
}

// ── Snapshots (Phase 7: historical playback) ───────────────────────────────

/**
 * List available spectrum frame metadata for a station in a time window.
 * @param {string} stationId
 * @param {number} startMs
 * @param {number} endMs
 * @param {number} [limit=1000]
 * @returns {Promise<{snapshots: Array, total: number}>}
 */
export function listSnapshots(stationId, startMs, endMs, limit = 1000) {
  return http.get('/spectrum/snapshots', {
    params: { station_id: stationId, start_ms: startMs, end_ms: endMs, limit },
  }).then(r => r.data)
}

/**
 * Fetch a single spectrum frame (with data blob) by frame_id.
 * @param {number} frameId
 * @returns {Promise<{frame_id, levels_dbm_b64, freq_start_hz, freq_step_hz, num_points, ...}>}
 */
export function getSnapshot(frameId) {
  return http.get(`/spectrum/snapshots/${frameId}`).then(r => r.data)
}

// ── Signal analysis (Phase 6) ─────────────────────────────────────────────

/**
 * Run signal detection on a spectrum frame or time range.
 * @param {object} req  { station_id, frame_id?, freq_start_hz?, freq_stop_hz?,
 *                        period_start_ms?, period_end_ms?, threshold_dbm,
 *                        ai_backend?, ai_api_key? }
 */
export function runAnalysis(req) {
  return http.post('/analysis', req, { timeout: 60_000 }).then(r => r.data)
}

/** @param {string} [stationId]  @param {number} [limit=100] */
export function listAnalyses(stationId = null, limit = 100) {
  return http.get('/analysis', {
    params: { station_id: stationId || undefined, limit },
  }).then(r => r.data)
}

/** @param {number} analysisId */
export function getAnalysis(analysisId) {
  return http.get(`/analysis/${analysisId}`).then(r => r.data)
}

/**
 * Update analysis status.
 * @param {number} analysisId
 * @param {string} status  'confirmed' | 'dismissed' | 'new'
 */
export function updateAnalysisStatus(analysisId, status) {
  return http.patch(`/analysis/${analysisId}`, { status }).then(r => r.data)
}

// ── Signal library (Phase 8) ──────────────────────────────────────────────

/** @param {string} [status]  @param {number} [limit=200] */
export function listSignals(status = null, limit = 200) {
  return http.get('/signals', {
    params: { status: status || undefined, limit },
  }).then(r => r.data)
}

/**
 * @param {object} record  { name, freq_center_hz, bandwidth_hz?, modulation?,
 *                           service?, authority?, station_id?, notes?, ... }
 */
export function createSignal(record) {
  return http.post('/signals', record).then(r => r.data)
}

/** @param {number} signalId  @param {object} updates */
export function updateSignal(signalId, updates) {
  return http.put(`/signals/${signalId}`, updates).then(r => r.data)
}

/** @param {number} signalId */
export function archiveSignal(signalId) {
  return http.patch(`/signals/${signalId}/archive`).then(r => r.data)
}

/** @param {number} signalId */
export function deleteSignal(signalId) {
  return http.delete(`/signals/${signalId}`).then(r => r.data)
}
