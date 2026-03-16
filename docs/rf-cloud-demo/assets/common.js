/* ============================================================
   common.js — 公共数据、工具函数、Tour引导系统
   ============================================================ */

// ── 站点数据 ────────────────────────────────────────────────
const STATIONS = [
  { id:1,  name:'北区监测站', short:'N-01', lng:116.38, lat:39.98, tasks:['持续扫描 20M–8G'], found:47, status:'scanning' },
  { id:2,  name:'东北站',     short:'NE-02', lng:116.52, lat:39.95, tasks:['执行测向任务'], found:31, status:'dfing' },
  { id:3,  name:'东区站',     short:'E-03',  lng:116.55, lat:39.88, tasks:['持续扫描 20M–8G'], found:38, status:'scanning' },
  { id:4,  name:'东南站',     short:'SE-04', lng:116.50, lat:39.80, tasks:['VHF段精密测向'], found:52, status:'dfing' },
  { id:5,  name:'南区站',     short:'S-05',  lng:116.38, lat:39.76, tasks:['持续扫描 20M–8G'], found:29, status:'scanning' },
  { id:6,  name:'西南站',     short:'SW-06', lng:116.25, lat:39.79, tasks:['执行干扰排查'], found:44, status:'tasked' },
  { id:7,  name:'西区站',     short:'W-07',  lng:116.22, lat:39.87, tasks:['持续扫描 20M–8G'], found:35, status:'scanning' },
  { id:8,  name:'西北站',     short:'NW-08', lng:116.26, lat:39.95, tasks:['执行测向任务'], found:26, status:'dfing' },
  { id:9,  name:'中心站',     short:'C-09',  lng:116.38, lat:39.87, tasks:['综合监测+AI处理'], found:63, status:'scanning' },
  { id:10, name:'郊外远端站', short:'R-10',  lng:116.62, lat:39.72, tasks:['持续扫描 20M–8G'], found:18, status:'scanning' },
];

// ── 信号库数据 ──────────────────────────────────────────────
const SIGNALS = [
  {
    id:'SIG-001', freq:97.4, freqStr:'97.400 MHz', bw:200, mod:'AM/FM', type:'黑广播',
    status:'alert', confidence:97, label:'违规调幅广播',
    firstSeen:'2024-11-01 14:22', lastSeen:'2024-11-08 16:47', count:23,
    stations:[4,5,6,9], bearing:{4:312, 5:28, 6:51, 9:195},
    emitLoc:{lng:116.31, lat:39.77},
    aiConclusion:'97.4 MHz调幅信号，带宽约200 kHz，信号强度稳定，非合规广播频率。语音解调确认含违规内容。',
    tags:['违规广播','语音信号','调幅'],
    alert: { type:'黑广播', transcript:'...（内容已过滤：含违法销售信息，经AI语音识别确认）...', verdict:'违规播出，依据：《无线电管理条例》第四十七条' }
  },
  {
    id:'SIG-002', freq:118.1, freqStr:'118.100 MHz', bw:25, mod:'AM', type:'航空VHF通信',
    status:'alert', confidence:94, label:'干扰源（航空频段）',
    firstSeen:'2024-11-05 09:15', lastSeen:'2024-11-08 17:30', count:8,
    stations:[3,4,9,10], bearing:{3:228, 4:155, 9:162, 10:210},
    emitLoc:{lng:116.46, lat:39.74},
    aiConclusion:'118.1 MHz频段接收到持续AM背景噪声，强度超基线12dB，非航空正常通信特征，判断为无意干扰源。',
    tags:['干扰','航空频段','AM噪声'],
    alert: { type:'航空VHF干扰', transcript:null, verdict:'非法干扰民用航空通信频率，建议立即溯源处置' }
  },
  {
    id:'SIG-003', freq:1575.42, freqStr:'1575.420 MHz', bw:30, mod:'BPSK/DSSS', type:'GPS L1',
    status:'alert', confidence:99, label:'GNSS干扰告警',
    firstSeen:'2024-11-08 11:03', lastSeen:'2024-11-08 14:55', count:3,
    stations:[1,2,3,7,8,9], bearing:{1:162, 2:195, 3:238, 7:108, 8:135, 9:180},
    emitLoc:{lng:116.41, lat:39.91},
    aiConclusion:'GPS L1频段检测到宽带干扰信号，覆盖±15 MHz，扫频速率约2 MHz/s，六站测向交叉定位于辖区东北方向。',
    tags:['GNSS干扰','宽带扫频','L1频段'],
    alert: { type:'GNSS干扰', transcript:null, verdict:'疑似宽带扫频干扰设备，已定位，建议执法介入' }
  },
  {
    id:'SIG-004', freq:460.325, freqStr:'460.325 MHz', bw:12.5, mod:'DMR', type:'数字集群',
    status:'known', confidence:92, label:'数字对讲（DMR）',
    firstSeen:'2024-09-12 08:00', lastSeen:'2024-11-08 18:02', count:412,
    stations:[3,4,9], bearing:{3:185, 4:220, 9:130},
    emitLoc:{lng:116.47, lat:39.83},
    aiConclusion:'460.325 MHz，信道带宽12.5 kHz，DMR制式数字集群通信，Color Code 3，时隙1/2均有业务，疑似建筑工地专网对讲。',
    tags:['DMR','数字集群','专网']
  },
  {
    id:'SIG-005', freq:433.92, freqStr:'433.920 MHz', bw:500, mod:'OOK/FSK', type:'ISM短距离',
    status:'known', confidence:88, label:'ISM设备（门禁/遥控）',
    firstSeen:'2024-10-03 10:30', lastSeen:'2024-11-08 17:15', count:156,
    stations:[9], bearing:{9:45},
    emitLoc:{lng:116.42, lat:39.90},
    aiConclusion:'433.92 MHz ISM频段，OOK调制，脉冲宽度0.3 ms，符合门禁/遥控器特征，属合法短距设备。',
    tags:['ISM','短距离','OOK']
  },
  {
    id:'SIG-006', freq:868.5, freqStr:'868.500 MHz', bw:250, mod:'LoRa', type:'物联网',
    status:'known', confidence:95, label:'LoRa IoT网关',
    firstSeen:'2024-08-20 00:00', lastSeen:'2024-11-08 17:58', count:2341,
    stations:[5,9], bearing:{5:15, 9:210},
    emitLoc:{lng:116.36, lat:39.82},
    aiConclusion:'868.5 MHz，LoRa扩频调制，SF=9，BW=250 kHz，每15分钟周期性出现，判断为城市IoT传感器网关。',
    tags:['LoRa','IoT','周期信号']
  },
  {
    id:'SIG-007', freq:2450.0, freqStr:'2450.000 MHz', bw:80000, mod:'OFDM/DSSS', type:'WiFi/BT共存',
    status:'known', confidence:91, label:'2.4G ISM密集区',
    firstSeen:'2024-07-01 00:00', lastSeen:'2024-11-08 18:05', count:9876,
    stations:[9], bearing:{9:280},
    emitLoc:{lng:116.35, lat:39.88},
    aiConclusion:'2.45 GHz频段高密度信号，含802.11b/g/n多组信道以及BT跳频信号，属居民区典型电磁环境。',
    tags:['WiFi','蓝牙','ISM','2.4G']
  },
  {
    id:'SIG-008', freq:351.225, freqStr:'351.225 MHz', bw:12.5, mod:'未知', type:'未知数字信号',
    status:'unknown', confidence:41, label:'待定性数字信号',
    firstSeen:'2024-11-07 03:14', lastSeen:'2024-11-08 04:38', count:2,
    stations:[1,8], bearing:{1:215, 8:160},
    emitLoc:{lng:116.32, lat:39.92},
    aiConclusion:'351.225 MHz非常规频率，仅凌晨3–5时出现，12.5 kHz信道，数字调制特征明显但帧结构未知，不匹配已知通信标准。建议持续监测。',
    tags:['未知','夜间活动','数字']
  },
  {
    id:'SIG-009', freq:162.55, freqStr:'162.550 MHz', bw:25, mod:'NBFM', type:'气象广播',
    status:'known', confidence:99, label:'气象NOAA广播',
    firstSeen:'2024-06-01 00:00', lastSeen:'2024-11-08 18:00', count:45231,
    stations:[1,9], bearing:{1:270, 9:300},
    emitLoc:{lng:116.15, lat:39.92},
    aiConclusion:'162.55 MHz气象无线电广播，NOAA格式，24小时连续播出，属已知合规固定台站。',
    tags:['气象','广播','合规']
  },
  {
    id:'SIG-010', freq:915.5, freqStr:'915.500 MHz', bw:1000, mod:'未知跳频', type:'未知跳频信号',
    status:'unknown', confidence:33, label:'宽带跳频待定',
    firstSeen:'2024-11-06 16:22', lastSeen:'2024-11-08 16:55', count:4,
    stations:[2,3,10], bearing:{2:180, 3:205, 10:270},
    emitLoc:{lng:116.54, lat:39.80},
    aiConclusion:'915 MHz中心频率，跳频速率约200跳/秒，跳频带宽±20 MHz，不符合已知ISM设备特征，可能为专用数传链路，待深度解析。',
    tags:['跳频','宽带','待解析']
  },
];

// ── 告警记录 ─────────────────────────────────────────────────
const ALERTS = [
  { id:'ALT-001', time:'2024-11-08 16:47', freq:'97.400 MHz', type:'黑广播', status:'处理中', signalId:'SIG-001', severity:'high' },
  { id:'ALT-002', time:'2024-11-08 14:55', freq:'1575.420 MHz', type:'GNSS干扰', status:'待核实', signalId:'SIG-003', severity:'high' },
  { id:'ALT-003', time:'2024-11-08 11:20', freq:'118.100 MHz', type:'航空VHF干扰', status:'处理中', signalId:'SIG-002', severity:'high' },
];

// ── AI任务队列（模拟后台任务）───────────────────────────────
const AI_TASK_TEMPLATES = [
  '正在分析 97.4 MHz 调幅信号音频特征...',
  '对比东南站与西南站测向数据，定位误差修正中...',
  '1575.42 MHz 干扰源功率谱密度计算...',
  '调取信号库 SIG-008 历史频谱数据...',
  '综合6站数据进行GNSS干扰源定位...',
  '351.225 MHz 帧结构深度解析...',
  '生成本日电磁态势日报摘要...',
  '460.325 MHz DMR信令解码，Color Code验证...',
  '执行频段 800–900 MHz 占用度统计...',
  '正在对比新发现信号与历史信号库...',
  '多站信噪比数据融合，优化测向精度...',
  '异常信号 SIG-010 跳频序列重建中...',
  '航空VHF干扰源位置估计，置信区间计算...',
  '自动生成 ALT-002 证据存档包...',
  '868.5 MHz LoRa网关周期性规律分析...',
];

// ── 频段业务注释 ──────────────────────────────────────────── 
const FREQ_BANDS = [
  { start:0.02,   end:0.1,    label:'长中波',         color:'#475569' },
  { start:0.1,    end:30,     label:'短波HF',          color:'#334155' },
  { start:30,     end:88,     label:'VHF低段',         color:'#1e3a5f' },
  { start:87.5,   end:108,    label:'FM广播',          color:'#164e63' },
  { start:108,    end:137,    label:'航空VHF',         color:'#1e3a5f' },
  { start:137,    end:174,    label:'VHF高段/气象',    color:'#1e3a5f' },
  { start:174,    end:230,    label:'DAB广播',         color:'#134e4a' },
  { start:380,    end:400,    label:'PDT警务集群',     color:'#1e3a5f' },
  { start:406,    end:512,    label:'UHF低段',         color:'#1e3a5f' },
  { start:694,    end:790,    label:'4G-B28',          color:'#1a2e4a' },
  { start:824,    end:960,    label:'2G/3G/4G',        color:'#1a2e4a' },
  { start:1164,   end:1215,   label:'GPS L5/GLONASS',  color:'#14532d' },
  { start:1559,   end:1610,   label:'GPS/BDS/GLONASS', color:'#14532d' },
  { start:1710,   end:2200,   label:'4G中高频段',      color:'#1a2e4a' },
  { start:2400,   end:2500,   label:'WiFi/BT 2.4G',    color:'#1e3a5f' },
  { start:2500,   end:2690,   label:'5G NR n41',       color:'#1a2e4a' },
  { start:3300,   end:3600,   label:'5G NR n78',       color:'#1a2e4a' },
  { start:4800,   end:5000,   label:'5G NR n79',       color:'#1a2e4a' },
  { start:5150,   end:5850,   label:'WiFi 5G',         color:'#1e3a5f' },
];

// ── 工具函数 ─────────────────────────────────────────────────
function formatTime(date = new Date()) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} `
       + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatFreq(mhz) {
  if (mhz >= 1000) return (mhz/1000).toFixed(4) + ' GHz';
  return mhz.toFixed(3) + ' MHz';
}

function seededRandom(seed) {
  let s = seed;
  return function() {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

function lerp(a, b, t) { return a + (b - a) * t; }

function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

// ── 实时时钟 ─────────────────────────────────────────────────
function startClock(el) {
  if (!el) return;
  const update = () => { el.textContent = formatTime(); };
  update();
  setInterval(update, 1000);
}

// ── 滚动计数动画 ──────────────────────────────────────────────
function animateCount(el, target, duration = 1500, prefix = '', suffix = '') {
  if (!el) return;
  const start = performance.now();
  const from = parseInt(el.textContent) || 0;
  const update = (t) => {
    const p = Math.min((t - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = prefix + Math.round(lerp(from, target, ease)) + suffix;
    if (p < 1) requestAnimationFrame(update);
  };
  requestAnimationFrame(update);
}

// ── 导航高亮 ─────────────────────────────────────────────────
function highlightNav() {
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-link').forEach(link => {
    const href = link.getAttribute('href');
    link.classList.toggle('active', href === path || (path === '' && href === 'index.html'));
  });
}

// ── Tour引导系统 ──────────────────────────────────────────────
class TourGuide {
  constructor(steps) {
    this.steps = steps;
    this.current = 0;
    this.overlay = document.getElementById('tour-overlay');
    this.tooltip = document.getElementById('tour-tooltip');
    this.spotlight = null;
    this.active = false;
  }

  start() {
    this.active = true;
    this.current = 0;
    this.overlay.classList.add('active');
    this.overlay.style.pointerEvents = 'auto';
    this.showStep(0);
  }

  stop() {
    this.active = false;
    this.overlay.classList.remove('active');
    this.overlay.style.pointerEvents = 'none';
    if (this.tooltip) this.tooltip.style.opacity = '0';
    if (this.spotlight) { this.spotlight.remove(); this.spotlight = null; }
  }

  showStep(idx) {
    const step = this.steps[idx];
    if (!step) { this.stop(); return; }

    // Run action before showing tooltip
    if (step.action) step.action();

    // Find target element
    const target = step.target ? document.querySelector(step.target) : null;

    // Update spotlight
    if (this.spotlight) this.spotlight.remove();
    if (target) {
      const rect = target.getBoundingClientRect();
      this.spotlight = document.createElement('div');
      this.spotlight.className = 'tour-spotlight';
      this.spotlight.style.cssText = `
        left:${rect.left - 6}px; top:${rect.top - 6}px;
        width:${rect.width + 12}px; height:${rect.height + 12}px;
      `;
      this.overlay.appendChild(this.spotlight);

      // Scroll target into view
      target.scrollIntoView({ behavior:'smooth', block:'nearest' });
    }

    // Build tooltip content
    const progress = this.steps.map((_, i) =>
      `<div class="tour-dot ${i===idx?'active':''}"></div>`
    ).join('');

    this.tooltip.innerHTML = `
      <div class="tour-tooltip-step">步骤 ${idx+1} / ${this.steps.length}</div>
      <div class="tour-tooltip-title">${step.title}</div>
      <div class="tour-tooltip-body">${step.body}</div>
      <div class="tour-tooltip-actions">
        <div class="tour-progress">${progress}</div>
        <div style="display:flex;gap:8px;align-items:center">
          <button class="tour-btn-skip" id="tour-skip">跳过</button>
          <button class="tour-btn-next" id="tour-next">
            ${idx < this.steps.length - 1 ? '下一步 →' : '完成 ✓'}
          </button>
        </div>
      </div>
    `;

    // Position tooltip
    this.positionTooltip(target);
    this.tooltip.style.opacity = '1';

    document.getElementById('tour-next').onclick = () => this.next();
    document.getElementById('tour-skip').onclick = () => this.stop();
  }

  positionTooltip(target) {
    const tw = 320, th = 180;
    const vw = window.innerWidth, vh = window.innerHeight;
    let left, top;

    if (target) {
      const rect = target.getBoundingClientRect();
      // Try right side
      if (rect.right + tw + 20 < vw) {
        left = rect.right + 16;
        top = clamp(rect.top, 20, vh - th - 20);
      }
      // Try left side
      else if (rect.left - tw - 20 > 0) {
        left = rect.left - tw - 16;
        top = clamp(rect.top, 20, vh - th - 20);
      }
      // Below
      else if (rect.bottom + th + 20 < vh) {
        left = clamp(rect.left + rect.width/2 - tw/2, 20, vw - tw - 20);
        top = rect.bottom + 16;
      }
      // Above
      else {
        left = clamp(rect.left + rect.width/2 - tw/2, 20, vw - tw - 20);
        top = rect.top - th - 16;
      }
    } else {
      left = vw/2 - tw/2;
      top = vh/2 - th/2;
    }

    this.tooltip.style.left = left + 'px';
    this.tooltip.style.top  = top + 'px';
  }

  next() {
    this.current++;
    if (this.current >= this.steps.length) this.stop();
    else this.showStep(this.current);
  }
}

// ── 导航HTML ─────────────────────────────────────────────────
function injectNav() {
  const nav = document.getElementById('nav');
  if (!nav) return;
  nav.innerHTML = `
    <div class="nav-logo">
      <div class="nav-logo-icon"></div>
      <div class="nav-logo-text">
        <span>RF·MIND</span>
        无线电监测AI融合系统
      </div>
    </div>
    <div class="nav-links">
      <a href="index.html" class="nav-link">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/>
          <rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/>
        </svg>
        <span class="nav-num">01</span>系统总览
      </a>
      <a href="spectrum.html" class="nav-link">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <polyline points="1,12 4,7 7,9 10,4 13,6 15,3"/>
        </svg>
        <span class="nav-num">02</span>频谱态势
      </a>
      <a href="signals.html" class="nav-link">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r="6.5" stroke-dasharray="2 2"/>
        </svg>
        <span class="nav-num">03</span>信号库
      </a>
      <a href="tasks.html" class="nav-link">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M2 4h12M2 8h8M2 12h10"/><circle cx="13" cy="11" r="2.5"/>
          <path d="M13 9.5V11l1 1"/>
        </svg>
        <span class="nav-num">04</span>任务执行
      </a>
    </div>
    <div class="nav-right">
      <div class="nav-status">
        <div class="status-dot"></div>
        <span>SYSTEM ONLINE</span>
      </div>
      <div class="nav-time" id="nav-time">--:--:--</div>
    </div>
  `;
  startClock(document.getElementById('nav-time'));
  highlightNav();
}

// ── 页面加载后注入导航 ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  injectNav();
});
