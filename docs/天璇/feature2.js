/**
 * feature2.js - 天璇监听阵
 * 功能二：站点批量调用
 */

'use strict';

const Feature2 = (() => {

  let _container    = null;
  let _results      = [];      // 采集结果（按电平排序）
  let _cancelCollect = null;   // 取消采集函数
  let _panels       = {};      // { siteId: { chart, liveInterval, isLive } }

  // ─────────────────────────────────────────────
  // 渲染主界面
  // ─────────────────────────────────────────────
  function render(container) {
    _container = container;
    container.innerHTML = `
      <div class="f2-wrap">
        <!-- 顶部参数区 -->
        <div class="f2-params panel-card">
          <div class="param-title">站点批量调用 <span class="tag-badge">全站同步采集</span></div>
          <div class="param-row">
            <label>中心频点 <span class="unit">MHz</span>
              <input type="number" id="f2-center" value="460" step="0.025" min="20" max="8000" />
            </label>
            <label>跨距 <span class="unit">MHz</span>
              <input type="number" id="f2-span" value="10" step="0.1" min="0.1" max="100" />
            </label>
            <label>解调带宽 <span class="unit">kHz</span>
              <input type="number" id="f2-bw" value="25" step="1" min="1" max="10000" />
            </label>
            <label>采集时长 <span class="unit">秒</span>
              <input type="number" id="f2-dur" value="8" step="1" min="2" max="60" />
            </label>
            <button class="btn-primary" id="f2-start">开始采集</button>
          </div>
          <!-- 进度条 -->
          <div class="f2-progress-wrap" id="f2-progress-wrap" style="display:none">
            <div class="f2-progress-bar">
              <div class="f2-progress-fill" id="f2-progress-fill"></div>
            </div>
            <span class="f2-progress-text" id="f2-progress-text">采集中…</span>
          </div>
        </div>

        <!-- 主体：左侧排名 + 右侧面板区 -->
        <div class="f2-body">
          <!-- 左侧站点排名 -->
          <div class="f2-sidebar panel-card">
            <div class="sidebar-title">站点排名
              <span class="sidebar-hint" id="f2-sidebar-hint">等待采集</span>
            </div>
            <div class="f2-site-list" id="f2-site-list">
              ${RFData.SITES.map(s => `
                <div class="f2-site-item idle" id="f2-item-${s.id}" data-id="${s.id}">
                  <span class="site-rank">—</span>
                  <span class="site-name">${s.name}</span>
                  <span class="site-level">—</span>
                </div>
              `).join('')}
            </div>
          </div>

          <!-- 右侧面板区 -->
          <div class="f2-panels-area" id="f2-panels-area">
            <div class="f2-empty-hint" id="f2-panels-hint">
              <div class="hint-icon">◈</div>
              <div>完成采集后，点击左侧站点展开频谱面板</div>
            </div>
          </div>
        </div>
      </div>
    `;

    document.getElementById('f2-start').addEventListener('click', _startCollect);
  }

  // ─────────────────────────────────────────────
  // 开始采集
  // ─────────────────────────────────────────────
  function _startCollect() {
    if (_cancelCollect) {
      _cancelCollect();
      _cancelCollect = null;
    }

    const centerMHz = parseFloat(document.getElementById('f2-center').value) || 460;
    const spanMHz   = parseFloat(document.getElementById('f2-span').value)   || 10;
    const bwKHz     = parseFloat(document.getElementById('f2-bw').value)     || 25;
    const durSec    = parseFloat(document.getElementById('f2-dur').value)    || 8;

    // 关闭所有已展开面板
    _closeAllPanels();
    _results = [];
    _updateSidebarIdle();

    // 进度条显示
    const pgWrap = document.getElementById('f2-progress-wrap');
    const pgFill = document.getElementById('f2-progress-fill');
    const pgText = document.getElementById('f2-progress-text');
    pgWrap.style.display = 'block';
    pgFill.style.width = '0%';
    pgText.textContent = '采集中…';

    document.getElementById('f2-start').disabled = true;
    document.getElementById('f2-sidebar-hint').textContent = '采集中…';

    _cancelCollect = RFData.collectSiteResults(
      centerMHz, spanMHz, bwKHz, durSec,
      // 进度回调
      (progress) => {
        pgFill.style.width = `${(progress * 100).toFixed(0)}%`;
        pgText.textContent = `采集中 ${(progress * 100).toFixed(0)}%`;
      },
      // 完成回调
      (results) => {
        _results = results;
        pgWrap.style.display = 'none';
        document.getElementById('f2-start').disabled = false;
        document.getElementById('f2-sidebar-hint').textContent = `已排序 · ${results.length} 站`;
        _renderSidebar(results, centerMHz, spanMHz, bwKHz);
      }
    );
  }

  function _updateSidebarIdle() {
    RFData.SITES.forEach(s => {
      const el = document.getElementById(`f2-item-${s.id}`);
      if (!el) return;
      el.className = 'f2-site-item idle';
      el.querySelector('.site-rank').textContent = '—';
      el.querySelector('.site-level').textContent = '—';
      el.onclick = null;
    });
  }

  function _renderSidebar(results, centerMHz, spanMHz, bwKHz) {
    // 先解绑所有旧的onclick
    results.forEach((r, idx) => {
      const el = document.getElementById(`f2-item-${r.site.id}`);
      if (!el) return;
      el.className = `f2-site-item ${RFCharts.levelToBadgeClass(r.maxLevel)}`;
      el.querySelector('.site-rank').textContent = `#${idx + 1}`;
      el.querySelector('.site-level').textContent = `${r.maxLevel.toFixed(1)} dBm`;
      el.onclick = () => _togglePanel(r, centerMHz, spanMHz, bwKHz);
    });

    // 空提示隐藏
    const hint = document.getElementById('f2-panels-hint');
    if (hint) hint.style.display = 'none';
  }

  // ─────────────────────────────────────────────
  // 面板管理
  // ─────────────────────────────────────────────
  function _togglePanel(result, centerMHz, spanMHz, bwKHz) {
    const { site } = result;
    if (_panels[site.id]) {
      _closePanel(site.id);
    } else {
      _openPanel(result, centerMHz, spanMHz, bwKHz);
    }
  }

  function _openPanel(result, centerMHz, spanMHz, bwKHz) {
    const { site } = result;
    const area = document.getElementById('f2-panels-area');
    const hint = document.getElementById('f2-panels-hint');
    if (hint) hint.style.display = 'none';

    const startMHz = centerMHz - spanMHz / 2;
    const endMHz   = centerMHz + spanMHz / 2;

    const panelId = `f2-panel-${site.id}`;
    const div = document.createElement('div');
    div.className = 'f2-spectrum-panel panel-card';
    div.id = panelId;
    div.innerHTML = `
      <div class="f2-panel-header">
        <span class="f2-panel-title">${site.name}
          <span class="f2-panel-region">${site.region}</span>
        </span>
        <span class="f2-panel-level ${RFCharts.levelToBadgeClass(result.maxLevel)}">${result.maxLevel.toFixed(1)} dBm</span>
        <div class="f2-panel-actions">
          <button class="btn-toggle-live" id="live-btn-${site.id}">▶ 实时监看</button>
          <button class="btn-ghost btn-sm" onclick="Feature2._closePanel(${site.id})">✕ 关闭</button>
        </div>
      </div>
      <div class="f2-canvas-wrap">
        <canvas id="f2-canvas-${site.id}"></canvas>
      </div>
    `;
    area.appendChild(div);

    // 初始化频谱图（静态Max Hold）
    const canvas = document.getElementById(`f2-canvas-${site.id}`);
    const chart = new RFCharts.SpectrumCanvas(canvas, {
      startMHz, endMHz,
      minDb: -110, maxDb: -20,
      siteId: site.id,
      maxHoldKey: `mh_f2_${site.id}`,
      showMaxHold: true,
      label: site.shortName,
      onRightClick: () => {},
    });

    // 展示静态Max Hold结果
    chart.setStaticSpectrum(result.spectrum, startMHz, endMHz);

    _panels[site.id] = { chart, liveInterval: null, isLive: false, startMHz, endMHz };

    // 实时监看按钮
    document.getElementById(`live-btn-${site.id}`).addEventListener('click', () => {
      _toggleLive(site.id);
    });

    // 高亮侧边栏条目
    const el = document.getElementById(`f2-item-${site.id}`);
    if (el) el.classList.add('active');
  }

  function _toggleLive(siteId) {
    const p = _panels[siteId];
    if (!p) return;
    const btn = document.getElementById(`live-btn-${siteId}`);

    if (p.isLive) {
      // 关闭实时
      p.chart.stop();
      p.isLive = false;
      if (btn) { btn.textContent = '▶ 实时监看'; btn.classList.remove('active'); }
    } else {
      // 开启实时
      RFData.clearMaxHold(`mh_f2_${siteId}`);
      p.chart.siteId = siteId;
      p.chart.maxHoldKey = `mh_f2_${siteId}`;
      p.chart.setRange(p.startMHz, p.endMHz);
      p.chart.start();
      p.isLive = true;
      if (btn) { btn.textContent = '⏹ 停止实时'; btn.classList.add('active'); }
    }
  }

  function _closePanel(siteId) {
    const p = _panels[siteId];
    if (!p) return;
    p.chart.stop();
    p.chart.destroy();
    const panelEl = document.getElementById(`f2-panel-${siteId}`);
    if (panelEl) panelEl.remove();
    delete _panels[siteId];

    // 取消侧边栏高亮
    const el = document.getElementById(`f2-item-${siteId}`);
    if (el) el.classList.remove('active');

    // 若无面板，显示提示
    const area = document.getElementById('f2-panels-area');
    const hint = document.getElementById('f2-panels-hint');
    if (area && hint && area.querySelectorAll('.f2-spectrum-panel').length === 0) {
      hint.style.display = 'flex';
    }
  }

  function _closeAllPanels() {
    Object.keys(_panels).forEach(id => _closePanel(parseInt(id)));
  }

  function destroy() {
    if (_cancelCollect) { _cancelCollect(); _cancelCollect = null; }
    _closeAllPanels();
    _container = null;
  }

  return { render, destroy, _closePanel };
})();
