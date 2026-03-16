/**
 * feature3.js - 天璇监听阵
 * 功能三：后台扫描与分析 v2
 * 数据已在 data.js 初始化时预生成，无需手动启动扫描
 */

'use strict';

const Feature3 = (() => {

  let _container   = null;
  let _charts      = {};
  let _liveUnsubs  = {};
  let _queryParams = { freqMHz: 1575.42, bwMHz: 1, rangeMs: 6 * 3600 * 1000 };
  let _scanUnsub   = null;

  // ─────────────────────────────────────────────
  // 渲染
  // ─────────────────────────────────────────────
  function render(container) {
    _container = container;

    container.innerHTML = `
      <div class="f3-wrap">

        <!-- 系统状态栏（替代原来的扫描控制区） -->
        <div class="f3-status-bar panel-card">
          <div class="f3-status-row">
            <div class="f3-status-title">天璇后台扫描系统
              <span class="tag-badge">全频段 20MHz–8GHz · 全天候运行</span>
            </div>
            <div class="f3-status-indicators">
              <div class="f3-indicator">
                <span class="status-dot scanning"></span>
                <span>扫描运行中</span>
              </div>
              <div class="f3-indicator">
                <span class="ind-label">已积累</span>
                <span class="ind-value" id="f3-history-len">—</span>
              </div>
              <div class="f3-indicator">
                <span class="ind-label">模拟当前时间</span>
                <span class="ind-value" id="f3-simtime">—</span>
              </div>
              <div class="f3-indicator">
                <span class="ind-label">统计粒度</span>
                <span class="ind-value">1 min</span>
              </div>
            </div>
          </div>
          <!-- 扫描波形装饰 -->
          <div class="scan-wave-wrap">
            <canvas id="f3-scan-wave" height="36"></canvas>
          </div>
        </div>

        <!-- 分析查询 -->
        <div class="f3-query panel-card">
          <div class="param-title">历史数据分析</div>
          <div class="param-row">
            <label>目标频率 <span class="unit">MHz</span>
              <input type="number" id="f3-freq" value="1575.42" step="0.001" min="20" max="8000" />
            </label>
            <label>分析带宽 <span class="unit">MHz</span>
              <input type="number" id="f3-bw" value="1" step="0.001" min="0.001" max="100" />
            </label>
            <label>时间范围
              <select id="f3-range">
                <option value="21600000" selected>最近6小时</option>
                <option value="86400000">最近24小时</option>
                <option value="259200000">最近72小时</option>
                <option value="604800000">最近1周</option>
                <option value="2592000000">最近1月</option>
                <option value="custom">自定义</option>
              </select>
            </label>
            <div id="f3-custom-range-wrap" style="display:none">
              <label>小时数
                <input type="number" id="f3-custom-hours" value="12" min="1" max="9999" style="width:70px" />
              </label>
            </div>
            <button class="btn-primary" id="f3-query-btn">查询分析</button>
          </div>
          <!-- 快捷频率按钮 -->
          <div class="f3-quick-btns">
            <span class="quick-label">快捷：</span>
            <button class="btn-quick" data-freq="1575.42" data-bw="1">GPS L1</button>
            <button class="btn-quick" data-freq="1561.098" data-bw="1">北斗B1</button>
            <button class="btn-quick" data-freq="460" data-bw="0.025">对讲UHF</button>
            <button class="btn-quick" data-freq="162" data-bw="0.025">对讲VHF</button>
            <button class="btn-quick" data-freq="98" data-bw="5">FM广播</button>
            <button class="btn-quick" data-freq="925" data-bw="35">GSM下行</button>
            <button class="btn-quick" data-freq="3450" data-bw="100">5G n78</button>
          </div>
        </div>

        <!-- 第一层：站点最大值卡片 -->
        <div class="f3-cards-section" id="f3-cards-section" style="display:none">
          <div class="section-title">各站点最大电平
            <span class="section-subtitle" id="f3-cards-subtitle"></span>
          </div>
          <div class="f3-cards-grid" id="f3-cards-grid"></div>
        </div>

        <!-- 第二层：折线图 -->
        <div class="f3-charts-section" id="f3-charts-section" style="display:none">
          <div class="section-title">电平–时间分析
            <span class="section-subtitle">点击卡片展开/收起 · 支持多站对比</span>
          </div>
          <div class="f3-charts-grid" id="f3-charts-grid"></div>
        </div>

      </div>
    `;

    _bindEvents();
    _startWave();
    _updateStatus();

    // 订阅实时更新（刷新状态栏时间显示）
    _scanUnsub = RFData.onScanUpdate(() => {
      _updateStatus();
      _refreshOpenCharts();
    });
  }

  function _updateStatus() {
    const simT = RFData.getScanSimTime();
    const el   = document.getElementById('f3-simtime');
    if (el && simT) {
      const d = new Date(simT);
      el.textContent = d.toLocaleString('zh-CN', { hour12: false });
    }
    // 显示已积累数据量（以第一个站点的第一个频点的历史点数为代表）
    const lenEl = document.getElementById('f3-history-len');
    if (lenEl) {
      // 粗略估算：6小时预生成360点 + 实时追加的点
      const startT = RFData.getScanStartRealTime();
      const nowT   = simT || Date.now();
      if (startT) {
        const mins = Math.round((nowT - startT) / 60000);
        lenEl.textContent = `${Math.max(360, mins)} 分钟`;
      }
    }
  }

  function _bindEvents() {
    document.getElementById('f3-query-btn').addEventListener('click', _runQuery);

    document.getElementById('f3-range').addEventListener('change', (e) => {
      const cw = document.getElementById('f3-custom-range-wrap');
      if (cw) cw.style.display = e.target.value === 'custom' ? 'block' : 'none';
    });

    // 快捷按钮
    document.querySelectorAll('.btn-quick').forEach(btn => {
      btn.addEventListener('click', () => {
        const freq = parseFloat(btn.dataset.freq);
        const bw   = parseFloat(btn.dataset.bw);
        document.getElementById('f3-freq').value = freq;
        document.getElementById('f3-bw').value   = bw;
        _runQuery();
      });
    });
  }

  // ─────────────────────────────────────────────
  // 扫描波形装饰
  // ─────────────────────────────────────────────
  let _waveFrame = null;
  let _wavePhase = 0;

  function _startWave() {
    const canvas = document.getElementById('f3-scan-wave');
    if (!canvas) return;

    function draw() {
      if (!document.getElementById('f3-scan-wave')) { cancelAnimationFrame(_waveFrame); return; }
      const parent = canvas.parentElement;
      canvas.width  = parent ? parent.clientWidth : 600;
      canvas.height = 36;
      const ctx = canvas.getContext('2d'), W = canvas.width;
      ctx.clearRect(0, 0, W, 36);
      const g = ctx.createLinearGradient(0,0,W,0);
      g.addColorStop(0,   'rgba(0,229,255,0)');
      g.addColorStop(0.2, 'rgba(0,229,255,0.5)');
      g.addColorStop(0.8, 'rgba(0,229,255,0.5)');
      g.addColorStop(1,   'rgba(0,229,255,0)');
      ctx.strokeStyle = g; ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let x = 0; x < W; x++) {
        const t  = x / W;
        const y  = 18
          + Math.sin(t * 18 + _wavePhase) * 5
          + Math.sin(t * 6  - _wavePhase * 0.8) * 3
          + Math.sin(t * 45 + _wavePhase * 2) * 1.2;
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
      _wavePhase += 0.07;
      _waveFrame = requestAnimationFrame(draw);
    }
    cancelAnimationFrame(_waveFrame);
    draw();
  }

  // ─────────────────────────────────────────────
  // 查询分析
  // ─────────────────────────────────────────────
  function _runQuery() {
    const freqMHz  = parseFloat(document.getElementById('f3-freq').value) || 1575.42;
    const bwMHz    = parseFloat(document.getElementById('f3-bw').value)   || 1;
    const rangeVal = document.getElementById('f3-range').value;
    let rangeMs;
    if (rangeVal === 'custom') {
      rangeMs = (parseFloat(document.getElementById('f3-custom-hours').value) || 12) * 3600000;
    } else {
      rangeMs = parseInt(rangeVal);
    }

    _queryParams = { freqMHz, bwMHz, rangeMs };
    _closeAllCharts();

    const results = RFData.querySiteMaxLevels(freqMHz, bwMHz, rangeMs);
    _renderCards(results, freqMHz, bwMHz, rangeMs);
  }

  function _renderCards(results, freqMHz, bwMHz, rangeMs) {
    const section  = document.getElementById('f3-cards-section');
    const grid     = document.getElementById('f3-cards-grid');
    const subtitle = document.getElementById('f3-cards-subtitle');
    if (!section || !grid) return;

    section.style.display = 'block';
    subtitle.textContent  = `${freqMHz} MHz ±${(bwMHz/2).toFixed(4)} MHz · ${_fmtRange(rangeMs)}`;

    const hasAny = results.some(r => r.history.length > 0);
    if (!hasAny) {
      grid.innerHTML = '<div class="no-data-hint">该频率无历史数据，请选择其他频率或更大带宽</div>';
      return;
    }

    grid.innerHTML = results.map((r, i) => {
      const lvClass = RFCharts.levelToBadgeClass(r.maxLevel);
      const hasData = r.history.length > 0;
      return `
        <div class="f3-site-card ${lvClass}" id="f3-card-${r.site.id}" onclick="Feature3._toggleChart(${r.site.id})">
          <div class="card-rank">#${i+1}</div>
          <div class="card-site-name">${r.site.name}</div>
          <div class="card-region">${r.site.region}</div>
          <div class="card-level">${hasData ? r.maxLevel.toFixed(1) : '—'}<span class="card-unit"> dBm</span></div>
          <div class="card-pts">${r.history.length} 数据点</div>
          <div class="card-expand-hint">点击展开折线图 ▾</div>
        </div>`;
    }).join('');

    document.getElementById('f3-charts-section').style.display = 'block';
  }

  function _fmtRange(ms) {
    const h = ms / 3600000;
    if (h >= 720) return '最近1月';
    if (h >= 168) return '最近1周';
    if (h >= 72)  return '最近72小时';
    if (h >= 24)  return '最近24小时';
    if (h >= 6)   return '最近6小时';
    return `最近${h.toFixed(0)}小时`;
  }

  // ─────────────────────────────────────────────
  // 折线图展开/收起
  // ─────────────────────────────────────────────
  function _toggleChart(siteId) {
    _charts[siteId] ? _closeChart(siteId) : _openChart(siteId);
  }

  function _openChart(siteId) {
    const site = RFData.SITES.find(s => s.id === siteId);
    if (!site) return;
    const grid = document.getElementById('f3-charts-grid');
    if (!grid) return;

    const hist = RFData.queryScanHistory(
      siteId, _queryParams.freqMHz, _queryParams.bwMHz, _queryParams.rangeMs
    );

    if (hist.length === 0) {
      // 显示无数据提示但不阻止展开
    }

    const colors = ['#00E5FF','#FFD600','#00FF9D','#FF6B35','#C77DFF','#FF5252','#4ECDC4','#6BCB77','#A8E6CF','#FFB347'];
    const color  = colors[(siteId - 1) % colors.length];

    const wrap = document.createElement('div');
    wrap.id        = `f3-chart-${siteId}`;
    wrap.className = 'f3-chart-wrap panel-card';
    wrap.innerHTML = `
      <div class="f3-chart-header">
        <span style="color:${color};font-weight:700">${site.name}</span>
        <span class="f3-chart-region">${site.region}</span>
        <span class="f3-chart-pts">${hist.length} pts</span>
        <button class="btn-ghost btn-sm" onclick="Feature3._closeChart(${siteId})">✕ 关闭</button>
      </div>
      <div class="f3-chart-inner" id="f3-chartinner-${siteId}" style="height:220px"></div>
    `;
    grid.appendChild(wrap);

    const el    = document.getElementById(`f3-chartinner-${siteId}`);
    const chart = new RFCharts.EChartsTimelineChart(el, {
      title:     `${site.shortName} · ${_queryParams.freqMHz} MHz`,
      color,
      maxPoints: 3000,
    });

    if (hist.length > 0) chart.setData(hist);
    _charts[siteId] = chart;

    const card = document.getElementById(`f3-card-${siteId}`);
    if (card) card.classList.add('expanded');

    // 订阅实时追加
    _liveUnsubs[siteId] = RFData.onScanUpdate(() => {
      const latest = RFData.queryScanHistory(
        siteId, _queryParams.freqMHz, _queryParams.bwMHz, _queryParams.rangeMs
      );
      if (latest.length > 0) {
        const last = latest[latest.length - 1];
        if (_charts[siteId]) _charts[siteId].appendPoint(last.t, last.level);
      }
    });
  }

  function _closeChart(siteId) {
    if (_liveUnsubs[siteId]) { _liveUnsubs[siteId](); delete _liveUnsubs[siteId]; }
    if (_charts[siteId])     { _charts[siteId].dispose(); delete _charts[siteId]; }
    const el = document.getElementById(`f3-chart-${siteId}`);
    if (el) el.remove();
    const card = document.getElementById(`f3-card-${siteId}`);
    if (card) card.classList.remove('expanded');
  }

  function _closeAllCharts() {
    Object.keys(_charts).forEach(id => _closeChart(parseInt(id)));
  }

  function _refreshOpenCharts() {
    // 各图表通过订阅独立更新，此处仅刷新状态显示
    _updateStatus();
  }

  function destroy() {
    cancelAnimationFrame(_waveFrame);
    _closeAllCharts();
    if (_scanUnsub) { _scanUnsub(); _scanUnsub = null; }
    _container = null;
  }

  return { render, destroy, _toggleChart, _closeChart };
})();
