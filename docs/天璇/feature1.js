/**
 * feature1.js - 天璇监听阵
 * 功能一：频率指配助手
 */

'use strict';

const Feature1 = (() => {

  let _container = null;
  let _upCanvas   = null, _downCanvas = null;
  let _upChart    = null, _downChart  = null;
  let _marks      = []; // [{id, freqMHz, upLevel, downLevel}]
  let _markIdSeq  = 1;
  let _params     = { upStart: 150, downStart: 460, spanMHz: 5, stepKHz: 25 };
  let _siteId     = 1; // 当前站点（功能一固定用站点1作为示例）

  // ─────────────────────────────────────────────
  // 渲染主界面
  // ─────────────────────────────────────────────
  function render(container) {
    _container = container;
    container.innerHTML = `
      <div class="f1-wrap">
        <!-- 顶部参数区 -->
        <div class="f1-params panel-card">
          <div class="param-title">频率指配助手 <span class="tag-badge">对讲机双频组网</span></div>
          <div class="param-row">
            <label>上行起始频率 <span class="unit">MHz</span>
              <input type="number" id="f1-up-start" value="${_params.upStart}" step="0.025" min="20" max="8000" />
            </label>
            <label>下行起始频率 <span class="unit">MHz</span>
              <input type="number" id="f1-down-start" value="${_params.downStart}" step="0.025" min="20" max="8000" />
            </label>
            <label>频段宽度 <span class="unit">MHz</span>
              <input type="number" id="f1-span" value="${_params.spanMHz}" step="0.1" min="0.1" max="50" />
            </label>
            <label>信道步进
              <select id="f1-step">
                <option value="25" ${_params.stepKHz===25?'selected':''}>25 kHz</option>
                <option value="12.5" ${_params.stepKHz===12.5?'selected':''}>12.5 kHz</option>
              </select>
            </label>
            <label>参考站点
              <select id="f1-site">
                ${RFData.SITES.map(s => `<option value="${s.id}">${s.name}</option>`).join('')}
              </select>
            </label>
            <button class="btn-primary" id="f1-apply">应用</button>
            <button class="btn-ghost" id="f1-clear-marks">清除Mark</button>
          </div>
        </div>

        <!-- 频谱图区域 -->
        <div class="f1-spectra">
          <div class="spectrum-panel">
            <div class="sp-label">上行频段
              <span class="sp-range" id="f1-up-range"></span>
              <span class="sp-hint">右键添加 Mark</span>
            </div>
            <div class="sp-canvas-wrap" id="f1-up-wrap">
              <canvas id="f1-up-canvas"></canvas>
            </div>
          </div>
          <div class="spectrum-panel">
            <div class="sp-label">下行频段
              <span class="sp-range" id="f1-down-range"></span>
              <span class="sp-hint">右键添加 Mark</span>
            </div>
            <div class="sp-canvas-wrap" id="f1-down-wrap">
              <canvas id="f1-down-canvas"></canvas>
            </div>
          </div>
        </div>

        <!-- Mark信息表 -->
        <div class="f1-marks panel-card">
          <div class="param-title">Mark 点信息
            <span class="mark-legend">
              <span class="dot mh-color"></span>Max Hold
              <span class="dot sig-color"></span>实时
            </span>
          </div>
          <div class="mark-table-wrap">
            <table class="mark-table" id="f1-mark-table">
              <thead>
                <tr>
                  <th>编号</th>
                  <th>上行频率</th>
                  <th>下行频率</th>
                  <th>上行电平</th>
                  <th>下行电平</th>
                  <th>建议</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody id="f1-mark-tbody">
                <tr class="mark-empty"><td colspan="7">右键点击频谱图添加 Mark</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    _bindParams();
    _initCharts();
    _updateRangeLabels();
  }

  function _bindParams() {
    document.getElementById('f1-apply').addEventListener('click', _applyParams);
    document.getElementById('f1-clear-marks').addEventListener('click', _clearMarks);

    // 回车也触发
    ['f1-up-start','f1-down-start','f1-span','f1-step','f1-site'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('change', _applyParams);
    });
  }

  function _applyParams() {
    _params.upStart   = parseFloat(document.getElementById('f1-up-start').value)   || 150;
    _params.downStart = parseFloat(document.getElementById('f1-down-start').value)  || 460;
    _params.spanMHz   = parseFloat(document.getElementById('f1-span').value)        || 5;
    _params.stepKHz   = parseFloat(document.getElementById('f1-step').value)        || 25;
    _siteId           = parseInt(document.getElementById('f1-site').value)          || 1;

    const upEnd   = _params.upStart   + _params.spanMHz;
    const downEnd = _params.downStart + _params.spanMHz;

    if (_upChart) {
      _upChart.stop();
      _upChart.setRange(_params.upStart, upEnd);
      _upChart.maxHoldKey = `mh_f1_up_${_siteId}`;
      RFData.clearMaxHold(_upChart.maxHoldKey);
      _upChart.siteId = _siteId;
      _upChart.start();
    }
    if (_downChart) {
      _downChart.stop();
      _downChart.setRange(_params.downStart, downEnd);
      _downChart.maxHoldKey = `mh_f1_down_${_siteId}`;
      RFData.clearMaxHold(_downChart.maxHoldKey);
      _downChart.siteId = _siteId;
      _downChart.start();
    }

    // 更新现有Mark的频率偏移（清除后重建）
    _marks = [];
    _renderMarkTable();
    _syncMarksToCharts();
    _updateRangeLabels();
  }

  function _updateRangeLabels() {
    const upEnd   = (_params.upStart   + _params.spanMHz).toFixed(3);
    const downEnd = (_params.downStart + _params.spanMHz).toFixed(3);
    const upEl   = document.getElementById('f1-up-range');
    const downEl = document.getElementById('f1-down-range');
    if (upEl)   upEl.textContent   = `${_params.upStart} – ${upEnd} MHz`;
    if (downEl) downEl.textContent = `${_params.downStart} – ${downEnd} MHz`;
  }

  function _initCharts() {
    const upCanvas   = document.getElementById('f1-up-canvas');
    const downCanvas = document.getElementById('f1-down-canvas');
    if (!upCanvas || !downCanvas) return;

    const upEnd   = _params.upStart   + _params.spanMHz;
    const downEnd = _params.downStart + _params.spanMHz;

    _upChart = new RFCharts.SpectrumCanvas(upCanvas, {
      startMHz: _params.upStart,
      endMHz:   upEnd,
      minDb: -110, maxDb: -20,
      siteId: _siteId,
      maxHoldKey: `mh_f1_up_${_siteId}`,
      showMaxHold: true,
      label: '上行',
      onRightClick: (freqMHz) => _addMark(freqMHz, 'up'),
    });

    _downChart = new RFCharts.SpectrumCanvas(downCanvas, {
      startMHz: _params.downStart,
      endMHz:   downEnd,
      minDb: -110, maxDb: -20,
      siteId: _siteId,
      maxHoldKey: `mh_f1_down_${_siteId}`,
      showMaxHold: true,
      label: '下行',
      onRightClick: (freqMHz) => _addMark(freqMHz, 'down'),
    });

    _upChart.start();
    _downChart.start();
  }

  // ─────────────────────────────────────────────
  // Mark管理
  // ─────────────────────────────────────────────
  function _addMark(clickedFreq, whichSide) {
    // 对齐到信道步进
    const stepMHz = _params.stepKHz / 1000;
    const offset  = whichSide === 'up'
      ? clickedFreq - _params.upStart
      : clickedFreq - _params.downStart;
    const alignedOffset = Math.round(offset / stepMHz) * stepMHz;

    const upFreq   = _params.upStart   + alignedOffset;
    const downFreq = _params.downStart + alignedOffset;

    // 避免重复
    const exist = _marks.find(m => Math.abs(m.upFreqMHz - upFreq) < stepMHz * 0.5);
    if (exist) return;

    // 读取当前电平
    const upLevel   = RFData.getInstantLevel(_siteId, upFreq);
    const downLevel = RFData.getInstantLevel(_siteId, downFreq);

    // 可用性判断：Max Hold电平低于阈值则建议可用
    const threshold = -75;
    const mhUp   = _getMaxHoldAt(_upChart?.maxHoldKey,   upFreq,   _params.upStart,   _params.upStart   + _params.spanMHz);
    const mhDown = _getMaxHoldAt(_downChart?.maxHoldKey, downFreq, _params.downStart, _params.downStart + _params.spanMHz);
    const available = mhUp < threshold && mhDown < threshold;

    _marks.push({
      id: _markIdSeq++,
      upFreqMHz: upFreq,
      downFreqMHz: downFreq,
      upLevel, downLevel,
      mhUp, mhDown,
      available,
    });

    _renderMarkTable();
    _syncMarksToCharts();
  }

  function _getMaxHoldAt(key, freqMHz, startMHz, endMHz) {
    const mh = RFData.getMaxHold(key);
    if (!mh) return -95;
    const n = mh.length;
    const idx = Math.round((freqMHz - startMHz) / (endMHz - startMHz) * (n - 1));
    const i = Math.max(0, Math.min(n - 1, idx));
    return mh[i];
  }

  function _clearMarks() {
    _marks = [];
    _markIdSeq = 1;
    _renderMarkTable();
    _syncMarksToCharts();
  }

  function _removeMark(id) {
    _marks = _marks.filter(m => m.id !== id);
    _renderMarkTable();
    _syncMarksToCharts();
  }

  function _syncMarksToCharts() {
    if (_upChart) {
      _upChart.setMarks(_marks.map(m => ({ freqMHz: m.upFreqMHz })));
    }
    if (_downChart) {
      _downChart.setMarks(_marks.map(m => ({ freqMHz: m.downFreqMHz })));
    }
  }

  function _renderMarkTable() {
    const tbody = document.getElementById('f1-mark-tbody');
    if (!tbody) return;

    if (_marks.length === 0) {
      tbody.innerHTML = `<tr class="mark-empty"><td colspan="7">右键点击频谱图添加 Mark</td></tr>`;
      return;
    }

    tbody.innerHTML = _marks.map(m => {
      const availClass = m.available ? 'avail-yes' : 'avail-no';
      const availText  = m.available ? '✓ 建议可用' : '✗ 存在占用';
      const upColor    = RFCharts.levelToBadgeClass(m.mhUp);
      const downColor  = RFCharts.levelToBadgeClass(m.mhDown);
      return `
        <tr>
          <td><span class="mark-id">M${m.id}</span></td>
          <td class="freq-cell">${m.upFreqMHz.toFixed(4)} MHz</td>
          <td class="freq-cell">${m.downFreqMHz.toFixed(4)} MHz</td>
          <td><span class="level-badge ${upColor}">${m.mhUp.toFixed(1)} dBm</span></td>
          <td><span class="level-badge ${downColor}">${m.mhDown.toFixed(1)} dBm</span></td>
          <td><span class="avail-badge ${availClass}">${availText}</span></td>
          <td><button class="btn-del" onclick="Feature1._removeMark(${m.id})">×</button></td>
        </tr>`;
    }).join('');
  }

  // ─────────────────────────────────────────────
  // 卸载（切换模块时调用）
  // ─────────────────────────────────────────────
  function destroy() {
    if (_upChart)   { _upChart.destroy();   _upChart   = null; }
    if (_downChart) { _downChart.destroy(); _downChart = null; }
    _container = null;
  }

  return { render, destroy, _removeMark };
})();
