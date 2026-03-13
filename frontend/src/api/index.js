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
