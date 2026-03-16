/**
 * charts.js - 天璇监听阵 图表组件层 v2
 * 修复：鼠标悬停坐标、right-click不再触发闪烁
 */

'use strict';

const RFCharts = (() => {

  const THEME = {
    bg:          '#0A0E1A',
    gridLine:    'rgba(0,229,255,0.07)',
    gridText:    'rgba(0,229,255,0.45)',
    axisLine:    'rgba(0,229,255,0.25)',
    signalLine:  '#1E88E5',
    signalFill:  'rgba(30,136,229,0.12)',
    maxHold:     '#FFD600',
    maxHoldFill: 'rgba(255,214,0,0.08)',
    markLine:    'rgba(255,82,82,0.9)',
    markText:    '#FF5252',
    crosshair:   'rgba(0,229,255,0.5)',
    panelBg:     'rgba(10,14,26,0.95)',
    border:      'rgba(0,229,255,0.15)',
  };

  const PADDING = { top: 18, right: 20, bottom: 36, left: 58 };

  // ─────────────────────────────────────────────
  // SpectrumCanvas
  // ─────────────────────────────────────────────
  class SpectrumCanvas {
    constructor(canvas, opts = {}) {
      this.canvas      = canvas;
      this.ctx         = canvas.getContext('2d');
      this.startMHz    = opts.startMHz    ?? 150;
      this.endMHz      = opts.endMHz      ?? 174;
      this.minDb       = opts.minDb       ?? -110;
      this.maxDb       = opts.maxDb       ?? -20;
      this.siteId      = opts.siteId      ?? 1;
      this.maxHoldKey  = opts.maxHoldKey  ?? `mh_${this.siteId}_${this.startMHz}`;
      this.showMaxHold = opts.showMaxHold !== false;
      this.label       = opts.label       ?? '';
      this.marks       = [];
      this._lastSpectrum  = null;
      this._lastMaxHold   = null;
      this._animFrame     = null;
      this._running       = false;
      this._staticSpectrum = null;
      // 鼠标悬停位置
      this._mouseX = -1;
      this._mouseY = -1;

      // ── 右键：不触发重绘，直接调用回调 ──
      canvas.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const x = (e.clientX - rect.left) * (canvas.width / rect.width);
        const freq = this._xToFreq(x);
        if (opts.onRightClick) opts.onRightClick(freq);
        // 不调用 stop/start，避免闪烁
      });

      // ── 鼠标移动：记录位置，触发下一帧重绘（不额外开新循环） ──
      canvas.addEventListener('mousemove', (e) => {
        const rect = canvas.getBoundingClientRect();
        this._mouseX = (e.clientX - rect.left) * (canvas.width / rect.width);
        this._mouseY = (e.clientY - rect.top)  * (canvas.height / rect.height);
        // 静态模式下需要手动触发重绘
        if (!this._running) this._redrawWithCrosshair();
      });
      canvas.addEventListener('mouseleave', () => {
        this._mouseX = -1;
        this._mouseY = -1;
        if (!this._running) this._redrawWithCrosshair();
      });

      this._resizeObserver = new ResizeObserver(() => this._resize());
      this._resizeObserver.observe(canvas.parentElement || canvas);
      this._resize();
    }

    _resize() {
      const parent = this.canvas.parentElement;
      if (!parent) return;
      const w = parent.clientWidth;
      const h = parent.clientHeight || 200;
      if (this.canvas.width !== w || this.canvas.height !== h) {
        this.canvas.width  = w;
        this.canvas.height = h;
        if (!this._running) this._redrawWithCrosshair();
      }
    }

    get _plotW() { return this.canvas.width  - PADDING.left - PADDING.right; }
    get _plotH() { return this.canvas.height - PADDING.top  - PADDING.bottom; }

    _freqToX(f)  { return PADDING.left + (f - this.startMHz) / (this.endMHz - this.startMHz) * this._plotW; }
    _xToFreq(x)  { return this.startMHz + (x - PADDING.left) / this._plotW * (this.endMHz - this.startMHz); }
    _dbToY(db)   { return PADDING.top + (1 - (db - this.minDb) / (this.maxDb - this.minDb)) * this._plotH; }
    _yToDb(y)    { return this.minDb + (1 - (y - PADDING.top) / this._plotH) * (this.maxDb - this.minDb); }

    setRange(startMHz, endMHz) { this.startMHz = startMHz; this.endMHz = endMHz; }

    setStaticSpectrum(spectrum, startMHz, endMHz) {
      this._staticSpectrum = { spectrum, startMHz, endMHz };
      if (!this._running) this._drawStatic();
    }

    start() {
      if (this._running) return;
      this._running = true;
      this._tick();
    }

    stop() {
      this._running = false;
      if (this._animFrame) cancelAnimationFrame(this._animFrame);
    }

    _tick() {
      if (!this._running) return;
      const POINTS = Math.max(128, Math.min(1024, this._plotW));
      const snap   = RFData.getSpectrumSnapshot(this.siteId, this.startMHz, this.endMHz, POINTS);
      const mh     = RFData.updateMaxHold(this.maxHoldKey, snap);
      this._lastSpectrum = snap;
      this._lastMaxHold  = mh;
      this._draw(snap, mh);
      this._animFrame = requestAnimationFrame(() =>
        setTimeout(() => this._tick(), 800 + Math.random() * 400));
    }

    _drawStatic() {
      if (!this._staticSpectrum) return;
      const { spectrum, startMHz, endMHz } = this._staticSpectrum;
      const saved = [this.startMHz, this.endMHz];
      this.startMHz = startMHz; this.endMHz = endMHz;
      this._draw(null, spectrum);
      [this.startMHz, this.endMHz] = saved;
    }

    // 静态模式下叠加十字线重绘
    _redrawWithCrosshair() {
      if (this._staticSpectrum) {
        const { spectrum, startMHz, endMHz } = this._staticSpectrum;
        const saved = [this.startMHz, this.endMHz];
        this.startMHz = startMHz; this.endMHz = endMHz;
        this._draw(null, spectrum);
        [this.startMHz, this.endMHz] = saved;
      } else if (this._lastSpectrum || this._lastMaxHold) {
        this._draw(this._lastSpectrum, this._lastMaxHold);
      }
    }

    _draw(spectrum, maxHold) {
      const ctx = this.ctx;
      const W = this.canvas.width, H = this.canvas.height;
      if (W < 10 || H < 10) return;

      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = THEME.bg;
      ctx.fillRect(0, 0, W, H);

      this._drawGrid(ctx);
      if (this.showMaxHold && maxHold)  this._drawCurve(ctx, maxHold,  THEME.maxHold,   THEME.maxHoldFill, 1.8);
      if (spectrum)                      this._drawCurve(ctx, spectrum, THEME.signalLine, THEME.signalFill,  1.2);
      this._drawMarks(ctx);
      this._drawAxes(ctx);
      if (this.label) this._drawLabel(ctx);

      // ── 鼠标十字线 + 坐标读数 ──────────────
      if (this._mouseX >= PADDING.left && this._mouseX <= PADDING.left + this._plotW) {
        this._drawCrosshair(ctx);
      }
    }

    _drawCrosshair(ctx) {
      const x    = this._mouseX;
      const freq = this._xToFreq(x);
      const db   = this._yToDb(this._mouseY);

      // 竖线
      ctx.save();
      ctx.strokeStyle = THEME.crosshair;
      ctx.lineWidth   = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, PADDING.top);
      ctx.lineTo(x, PADDING.top + this._plotH);
      ctx.stroke();

      // 横线
      if (this._mouseY >= PADDING.top && this._mouseY <= PADDING.top + this._plotH) {
        ctx.beginPath();
        ctx.moveTo(PADDING.left, this._mouseY);
        ctx.lineTo(PADDING.left + this._plotW, this._mouseY);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // 坐标标注框
      const freqLabel = this._formatFreq(freq);
      const dbLabel   = db.toFixed(1) + ' dBm';
      const text      = `${freqLabel}  ${dbLabel}`;
      ctx.font        = '11px "JetBrains Mono", monospace';
      const tw        = ctx.measureText(text).width;
      let bx = x + 8;
      if (bx + tw + 12 > PADDING.left + this._plotW) bx = x - tw - 20;
      const by = Math.max(PADDING.top + 4, Math.min(this._mouseY - 20, PADDING.top + this._plotH - 20));

      ctx.fillStyle   = 'rgba(0,229,255,0.12)';
      ctx.strokeStyle = 'rgba(0,229,255,0.4)';
      ctx.lineWidth   = 1;
      ctx.beginPath();
      ctx.roundRect(bx - 4, by - 12, tw + 16, 18, 3);
      ctx.fill(); ctx.stroke();

      ctx.fillStyle = '#00E5FF';
      ctx.textAlign = 'left';
      ctx.fillText(text, bx + 4, by);
      ctx.restore();
    }

    _drawGrid(ctx) {
      ctx.strokeStyle = THEME.gridLine;
      ctx.lineWidth   = 1;
      ctx.setLineDash([3, 5]);
      for (let db = Math.ceil(this.minDb / 10) * 10; db <= this.maxDb; db += 10) {
        const y = this._dbToY(db);
        ctx.beginPath(); ctx.moveTo(PADDING.left, y); ctx.lineTo(PADDING.left + this._plotW, y); ctx.stroke();
      }
      const step = this._niceFreqStep(this.endMHz - this.startMHz);
      for (let f = Math.ceil(this.startMHz / step) * step; f <= this.endMHz + step * 0.01; f = parseFloat((f + step).toFixed(6))) {
        const x = this._freqToX(Math.min(f, this.endMHz));
        ctx.beginPath(); ctx.moveTo(x, PADDING.top); ctx.lineTo(x, PADDING.top + this._plotH); ctx.stroke();
      }
      ctx.setLineDash([]);
    }

    _niceFreqStep(r) {
      const raw = r / 6;
      const mag = Math.pow(10, Math.floor(Math.log10(raw)));
      const res = raw / mag;
      if (res < 1.5) return mag;
      if (res < 3.5) return 2 * mag;
      if (res < 7.5) return 5 * mag;
      return 10 * mag;
    }

    _drawCurve(ctx, data, strokeColor, fillColor, lw) {
      const n = data.length;
      if (n === 0) return;
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = PADDING.left + (i / (n - 1)) * this._plotW;
        const y = this._dbToY(data[i]);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth   = lw;
      ctx.stroke();
      if (fillColor) {
        ctx.lineTo(PADDING.left + this._plotW, this._dbToY(this.minDb));
        ctx.lineTo(PADDING.left, this._dbToY(this.minDb));
        ctx.closePath();
        ctx.fillStyle = fillColor;
        ctx.fill();
      }
    }

    _drawAxes(ctx) {
      ctx.fillStyle = THEME.gridText;
      ctx.font      = '11px "JetBrains Mono", "Courier New", monospace';
      for (let db = Math.ceil(this.minDb / 10) * 10; db <= this.maxDb; db += 10) {
        ctx.textAlign = 'right';
        ctx.fillText(`${db}`, PADDING.left - 5, this._dbToY(db) + 4);
      }
      const step = this._niceFreqStep(this.endMHz - this.startMHz);
      ctx.textAlign = 'center';
      for (let f = Math.ceil(this.startMHz / step) * step; f <= this.endMHz + step * 0.01; f = parseFloat((f + step).toFixed(6))) {
        ctx.fillText(this._formatFreq(f), this._freqToX(Math.min(f, this.endMHz)), PADDING.top + this._plotH + 16);
      }
      ctx.strokeStyle = THEME.axisLine; ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(PADDING.left, PADDING.top);
      ctx.lineTo(PADDING.left, PADDING.top + this._plotH);
      ctx.lineTo(PADDING.left + this._plotW, PADDING.top + this._plotH);
      ctx.stroke();
      ctx.save();
      ctx.translate(12, PADDING.top + this._plotH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.fillStyle = THEME.axisLine;
      ctx.font = '10px monospace';
      ctx.fillText('dBm', 0, 0);
      ctx.restore();
    }

    _formatFreq(mhz) {
      if (mhz >= 1000) return `${(mhz / 1000).toFixed(mhz % 1000 === 0 ? 1 : 2)}G`;
      if (mhz >= 1)    return `${Number(mhz.toFixed(3))}M`;
      return `${(mhz * 1000).toFixed(0)}k`;
    }

    _drawMarks(ctx) {
      this.marks.forEach((m, idx) => {
        const x = this._freqToX(m.freqMHz);
        if (x < PADDING.left || x > PADDING.left + this._plotW) return;
        ctx.strokeStyle = THEME.markLine;
        ctx.lineWidth   = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.beginPath(); ctx.moveTo(x, PADDING.top); ctx.lineTo(x, PADDING.top + this._plotH); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = THEME.markLine;
        ctx.font      = 'bold 11px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(`M${idx + 1}`, x, PADDING.top + 12);
      });
    }

    _drawLabel(ctx) {
      ctx.fillStyle = 'rgba(0,229,255,0.6)';
      ctx.font      = '11px monospace';
      ctx.textAlign = 'left';
      ctx.fillText(this.label, PADDING.left + 6, PADDING.top + 14);
    }

    setMarks(marks) {
      this.marks = marks;
      // 静态模式下立刻刷新（不重启动画循环）
      if (!this._running) this._redrawWithCrosshair();
    }

    destroy() {
      this.stop();
      if (this._resizeObserver) this._resizeObserver.disconnect();
    }
  }

  // ─────────────────────────────────────────────
  // EChartsTimelineChart
  // ─────────────────────────────────────────────
  class EChartsTimelineChart {
    constructor(container, opts = {}) {
      this.container  = container;
      this.color      = opts.color    || '#00E5FF';
      this.maxPoints  = opts.maxPoints || 2000;
      this._data      = [];
      this._chart     = null;
      this._init(opts.title || '');
    }

    _init(title) {
      if (typeof echarts === 'undefined') return;
      this._chart = echarts.init(this.container, null, { renderer: 'canvas' });
      this._chart.setOption({
        backgroundColor: 'transparent',
        grid: { top: 36, right: 24, bottom: 48, left: 62 },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(10,14,26,0.95)',
          borderColor: 'rgba(0,229,255,0.3)',
          textStyle: { color: '#E0F4FF', fontSize: 12, fontFamily: 'monospace' },
          formatter: (params) => {
            const p = params[0];
            if (!p) return '';
            const d = new Date(p.value[0]);
            return `${d.toLocaleTimeString()}<br/><span style="color:${this.color}">${Number(p.value[1]).toFixed(1)} dBm</span>`;
          },
        },
        xAxis: {
          type: 'time',
          axisLine:  { lineStyle: { color: 'rgba(0,229,255,0.2)' } },
          axisLabel: {
            color: 'rgba(0,229,255,0.5)', fontFamily: 'monospace', fontSize: 11,
            formatter: (val) => {
              const d = new Date(val);
              return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
            },
          },
          splitLine: { lineStyle: { color: 'rgba(0,229,255,0.05)' } },
        },
        yAxis: {
          type: 'value', name: 'dBm',
          nameTextStyle: { color: 'rgba(0,229,255,0.4)', fontSize: 10 },
          min: -140, max: -20,
          axisLine:  { lineStyle: { color: 'rgba(0,229,255,0.2)' } },
          axisLabel: { color: 'rgba(0,229,255,0.5)', fontFamily: 'monospace', fontSize: 11 },
          splitLine: { lineStyle: { color: 'rgba(0,229,255,0.05)' } },
        },
        dataZoom: [
          { type: 'inside',  xAxisIndex: 0, filterMode: 'none' },
          {
            type: 'slider', xAxisIndex: 0, height: 16, bottom: 4,
            borderColor: 'rgba(0,229,255,0.2)',
            fillerColor: 'rgba(0,229,255,0.08)',
            handleStyle: { color: '#00E5FF' },
            textStyle:   { color: 'rgba(0,229,255,0.4)', fontSize: 10 },
            filterMode: 'none',
          },
        ],
        series: [{
          type: 'line', data: [],
          sampling: 'max', large: true, largeThreshold: 300,
          symbol: 'none',
          lineStyle: { color: this.color, width: 1.5 },
          areaStyle: { color: `${this.color}18` },
          emphasis: { disabled: true },
        }],
        ...(title ? {
          title: {
            text: title,
            textStyle: { color: 'rgba(0,229,255,0.7)', fontSize: 12, fontFamily: 'monospace', fontWeight: 'normal' },
            left: 'center', top: 4,
          }
        } : {}),
      });
    }

    setData(points) {
      this._data = [...points];
      this._refresh();
    }

    appendPoint(t, level) {
      // 避免重复追加同一时刻
      if (this._data.length > 0 && this._data[this._data.length - 1].t === t) return;
      this._data.push({ t, level });
      if (this._data.length > this.maxPoints) this._data.shift();
      this._refresh();
    }

    _refresh() {
      if (!this._chart) return;
      const ecData = this._data.map(p => [p.t, parseFloat(p.level.toFixed(2))]);
      this._chart.setOption({ series: [{ data: ecData }] }, { replaceMerge: ['series'] });
    }

    resize() { if (this._chart) this._chart.resize(); }
    dispose() { if (this._chart) { this._chart.dispose(); this._chart = null; } }
  }

  // ─────────────────────────────────────────────
  // SiteMap
  // ─────────────────────────────────────────────
  class SiteMap {
    constructor(canvas, opts = {}) {
      this.canvas = canvas;
      this.ctx    = canvas.getContext('2d');
      this.opts   = opts;
      this._pulse = 0;
      this._animFrame = null;

      canvas.addEventListener('click', (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = (e.clientX - rect.left) / rect.width;
        const my = (e.clientY - rect.top)  / rect.height;
        for (const site of RFData.SITES) {
          const dx = mx - site.x, dy = my - site.y;
          if (dx * dx + dy * dy < 0.002) {
            if (opts.onSiteClick) opts.onSiteClick(site);
            break;
          }
        }
      });

      this._resizeObserver = new ResizeObserver(() => this._resize());
      this._resizeObserver.observe(canvas.parentElement || canvas);
      this._resize();
      this._tick();
    }

    _resize() {
      const p = this.canvas.parentElement;
      if (!p) return;
      this.canvas.width  = p.clientWidth;
      this.canvas.height = p.clientHeight || 300;
    }

    _tick() {
      this._pulse = (this._pulse + 0.02) % (Math.PI * 2);
      this._draw();
      this._animFrame = requestAnimationFrame(() => setTimeout(() => this._tick(), 50));
    }

    _draw() {
      const ctx = this.ctx;
      const W = this.canvas.width, H = this.canvas.height;
      if (W < 10 || H < 10) return;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = 'transparent';
      ctx.strokeStyle = 'rgba(0,229,255,0.04)'; ctx.lineWidth = 1;
      const gs = 40;
      for (let x = 0; x < W; x += gs) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
      for (let y = 0; y < H; y += gs) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }

      const grid9 = RFData.SITES.slice(0, 9);
      [[0,1],[1,2],[3,4],[4,5],[6,7],[7,8],[0,3],[3,6],[1,4],[4,7],[2,5],[5,8]].forEach(([a,b]) => {
        const sa = grid9[a], sb = grid9[b];
        ctx.strokeStyle = 'rgba(0,229,255,0.06)'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(sa.x*W, sa.y*H); ctx.lineTo(sb.x*W, sb.y*H); ctx.stroke();
      });

      const alertIds  = this.opts.alertSiteIds  || new Set();
      const activeIds = this.opts.activeSiteIds || new Set();
      RFData.SITES.forEach((site) => {
        const sx = site.x*W, sy = site.y*H;
        const isAlert  = alertIds.has(site.id);
        const isActive = activeIds.has(site.id);
        const color    = isAlert ? '#FF5252' : isActive ? '#00E5FF' : 'rgba(0,229,255,0.6)';
        if (isAlert || isActive) {
          const pr = 18 + Math.sin(this._pulse) * 6;
          ctx.beginPath(); ctx.arc(sx,sy,pr,0,Math.PI*2);
          ctx.strokeStyle = color+'40'; ctx.lineWidth = 1.5; ctx.stroke();
        }
        ctx.beginPath(); ctx.arc(sx,sy,12,0,Math.PI*2);
        ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
        ctx.fillStyle = isAlert ? 'rgba(255,82,82,0.15)' : 'rgba(0,229,255,0.08)'; ctx.fill();
        ctx.beginPath(); ctx.arc(sx,sy,3.5,0,Math.PI*2);
        ctx.fillStyle = color; ctx.fill();
        ctx.fillStyle = color; ctx.font = '11px "JetBrains Mono", monospace';
        ctx.textAlign = 'center'; ctx.fillText(site.shortName, sx, sy+26);
      });
    }

    setAlertSites(ids)  { this.opts.alertSiteIds  = new Set(ids); }
    setActiveSites(ids) { this.opts.activeSiteIds = new Set(ids); }
    destroy() { if (this._animFrame) cancelAnimationFrame(this._animFrame); if (this._resizeObserver) this._resizeObserver.disconnect(); }
  }

  // ─────────────────────────────────────────────
  // 工具函数
  // ─────────────────────────────────────────────
  function levelToColor(db, minDb=-110, maxDb=-20) {
    const t = Math.max(0, Math.min(1, (db-minDb)/(maxDb-minDb)));
    if (t < 0.25) return `rgba(0,${Math.round(t/0.25*200)},255,0.9)`;
    if (t < 0.5)  { const r=(t-0.25)/0.25; return `rgba(0,${Math.round(200+r*55)},${Math.round(255-r*255)},0.9)`; }
    if (t < 0.75) { const r=(t-0.5)/0.25;  return `rgba(${Math.round(r*255)},255,0,0.9)`; }
    const r=(t-0.75)/0.25; return `rgba(255,${Math.round(255-r*155)},0,0.9)`;
  }

  function levelToBadgeClass(db) {
    if (db > -50) return 'level-high';
    if (db > -70) return 'level-mid';
    if (db > -90) return 'level-low';
    return 'level-noise';
  }

  return { THEME, SpectrumCanvas, EChartsTimelineChart, SiteMap, levelToColor, levelToBadgeClass };
})();
