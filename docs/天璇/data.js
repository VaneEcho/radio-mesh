/**
 * data.js - 天璇监听阵 数据层 v2
 * 修复：信道稀疏化、FM固定台站、运营商信号精确化、预生成历史数据
 */

'use strict';

const RFData = (() => {

  // ─────────────────────────────────────────────
  // 站点定义
  // ─────────────────────────────────────────────
  const SITES = [
    { id: 1,  name: '天璇一站', shortName: 'TXS1', x: 0.18, y: 0.18, region: '北部山区' },
    { id: 2,  name: '天璇二站', shortName: 'TXS2', x: 0.50, y: 0.15, region: '中部平原' },
    { id: 3,  name: '天璇三站', shortName: 'TXS3', x: 0.82, y: 0.18, region: '东北高地' },
    { id: 4,  name: '天璇四站', shortName: 'TXS4', x: 0.15, y: 0.50, region: '西部丘陵' },
    { id: 5,  name: '天璇五站', shortName: 'TXS5', x: 0.50, y: 0.50, region: '中心基站' },
    { id: 6,  name: '天璇六站', shortName: 'TXS6', x: 0.85, y: 0.50, region: '东部沿海' },
    { id: 7,  name: '天璇七站', shortName: 'TXS7', x: 0.18, y: 0.82, region: '南部谷地' },
    { id: 8,  name: '天璇八站', shortName: 'TXS8', x: 0.50, y: 0.85, region: '南部平原' },
    { id: 9,  name: '天璇九站', shortName: 'TXS9', x: 0.82, y: 0.82, region: '东南港口' },
    { id: 10, name: '天璇十站', shortName: 'TXS0', x: 0.92, y: 0.30, region: '近海观测' },
  ];

  const FREQ_START_MHZ = 20;
  const FREQ_END_MHZ   = 8000;
  const NOISE_FLOOR_MIN = -95;
  const NOISE_FLOOR_MAX = -85;

  // ─────────────────────────────────────────────
  // FM广播：固定台站（全国模拟，各站点接收电平略有差异）
  // 真实FM广播台间隔200kHz，大城市约10-15个台，郊区5-8个
  // ─────────────────────────────────────────────
  const FM_STATIONS = [
    // 频率MHz, 基础电平dBm, 名称
    { freq: 88.7,  level: -32, name: '新闻频率' },
    { freq: 91.4,  level: -35, name: '交通频率' },
    { freq: 93.0,  level: -38, name: '音乐频率' },
    { freq: 95.8,  level: -33, name: '综合频率' },
    { freq: 97.4,  level: -36, name: '文艺频率' },
    { freq: 99.6,  level: -31, name: '经济频率' },
    { freq: 101.8, level: -37, name: '体育频率' },
    { freq: 103.2, level: -34, name: '农业频率' },
    { freq: 105.0, level: -39, name: '民族频率' },
    { freq: 106.6, level: -36, name: '教育频率' },
    { freq: 107.4, level: -33, name: '都市频率' },
  ];

  // 各站点能接收到的FM台（模拟距离差异：市区站多，山区/海边少）
  // 数组内为FM_STATIONS的索引，加上该站点的电平偏移dB
  const SITE_FM_COVERAGE = {
    1:  { indices: [0,1,3,5,9],         offset: -4  }, // 山区：5台，衰减多
    2:  { indices: [0,1,2,3,4,5,6,8,10], offset: 0  }, // 平原中心：9台
    3:  { indices: [0,2,3,5,7,9],       offset: -3  }, // 东北：6台
    4:  { indices: [1,3,5,8],           offset: -5  }, // 丘陵：4台
    5:  { indices: [0,1,2,3,4,5,6,7,8,9,10], offset: 2 }, // 中心：全部11台
    6:  { indices: [0,1,3,5,6,9,10],    offset: -1  }, // 沿海：7台
    7:  { indices: [0,3,5,6,9],         offset: -4  }, // 谷地：5台
    8:  { indices: [0,1,2,3,5,6,8,9],   offset: -1  }, // 南部平原：8台
    9:  { indices: [0,3,5,6,9,10],      offset: -2  }, // 港口：6台
    10: { indices: [3,5,9],             offset: -6  }, // 近海：3台，最弱
  };

  // ─────────────────────────────────────────────
  // 对讲机：每个站点固定的活跃信道集合
  // VHF 150-174MHz，步进25kHz，共960个信道
  // UHF 400-470MHz，步进25kHz，共2800个信道（实际专用段集中在400-430MHz）
  //
  // 真实情况：一个城区监测站大约能监测到8-20对（上下行）对讲信道
  // 郊区/山区 4-10对，市区 12-20对
  // 信道频率是固定的，但占用是间歇的（Push-to-Talk特性）
  // ─────────────────────────────────────────────

  // 生成VHF信道频率列表（150.0125到173.9875，步进25kHz）
  function _genVHFChannels() {
    const chs = [];
    for (let f = 150.0125; f < 174; f = parseFloat((f + 0.025).toFixed(4))) {
      chs.push(parseFloat(f.toFixed(4)));
    }
    return chs;
  }
  // 生成UHF专用段信道（403-423.5MHz，步进25kHz）
  function _genUHFChannels() {
    const chs = [];
    for (let f = 403.0125; f < 423.5; f = parseFloat((f + 0.025).toFixed(4))) {
      chs.push(parseFloat(f.toFixed(4)));
    }
    // 加上公众对讲 409.75-409.99MHz（已包含在上面范围内）
    return chs;
  }

  const ALL_VHF_CHS = _genVHFChannels();
  const ALL_UHF_CHS = _genUHFChannels();

  // 伪随机选取信道（确保站点间不同，但固定）
  function _pickChannels(allChs, count, seedOffset) {
    // 用简单LCG给出固定顺序
    let s = seedOffset * 1234567 + 89101112;
    const picked = [];
    const pool = [...allChs];
    for (let i = 0; i < count && pool.length > 0; i++) {
      s = (s * 1664525 + 1013904223) >>> 0;
      const idx = s % pool.length;
      picked.push(pool[idx]);
      pool.splice(idx, 1);
    }
    return picked.sort((a, b) => a - b);
  }

  // 各站点活跃信道配置
  // 包含：信道频率、类型（常发/时发）、基础电平
  const SITE_WALKY_CHANNELS = {};
  // 站点信道数量（VHF, UHF）
  const SITE_CH_COUNTS = {
    1: { vhf: 4,  uhf: 6  },  // 山区，稀疏
    2: { vhf: 7,  uhf: 12 },  // 平原中心，较密
    3: { vhf: 5,  uhf: 8  },
    4: { vhf: 3,  uhf: 5  },  // 丘陵，最稀疏
    5: { vhf: 8,  uhf: 15 },  // 中心基站，最密
    6: { vhf: 6,  uhf: 10 },  // 沿海
    7: { vhf: 4,  uhf: 7  },
    8: { vhf: 6,  uhf: 11 },
    9: { vhf: 5,  uhf: 9  },
    10:{ vhf: 3,  uhf: 4  },  // 近海，极稀疏
  };

  SITES.forEach(s => {
    const cnt = SITE_CH_COUNTS[s.id] || { vhf: 5, uhf: 8 };
    const vhfChs = _pickChannels(ALL_VHF_CHS, cnt.vhf, s.id * 100);
    const uhfChs = _pickChannels(ALL_UHF_CHS, cnt.uhf, s.id * 200);

    const channels = [];

    // VHF信道：上下行配对，偏移5MHz（模拟中继台收发频差）
    vhfChs.forEach((txFreq, i) => {
      const rxFreq = parseFloat((txFreq + 5.0).toFixed(4)); // 下行偏移5MHz
      // 随机分配常发/时发（约30%常发）
      const alwaysOn = (s.id + i) % 3 === 0;
      const level = -58 + (s.id % 5) * 2 + i % 4; // 各站点电平略有差异
      channels.push({ freq: txFreq, pairFreq: rxFreq, band: 'VHF', alwaysOn, level });
    });

    // UHF信道：上下行配对，偏移约10MHz
    uhfChs.forEach((txFreq, i) => {
      const rxFreq = parseFloat((txFreq + 10.0).toFixed(4));
      const alwaysOn = (s.id + i) % 4 === 0;
      const level = -55 + (s.id % 5) * 2 + i % 5;
      channels.push({ freq: txFreq, pairFreq: rxFreq, band: 'UHF', alwaysOn, level });
    });

    SITE_WALKY_CHANNELS[s.id] = channels;
  });

  // ─────────────────────────────────────────────
  // 对讲信道占用状态机（每个信道独立PTT状态）
  // ─────────────────────────────────────────────
  const _chState = {}; // key: `${siteId}_${freq}` => { active, nextToggle }

  function _getChannelActive(siteId, freq, alwaysOn) {
    const key = `${siteId}_${freq}`;
    const now = Date.now();
    if (!_chState[key]) {
      // 初始化：随机散开，避免全部同时切换
      const initRand = ((siteId * 999 + freq * 37) | 0) % 100 / 100;
      _chState[key] = {
        active: alwaysOn ? true : initRand > 0.7,
        nextToggle: now + initRand * 15000,
      };
    }
    const st = _chState[key];
    if (now > st.nextToggle) {
      if (alwaysOn) {
        // 常发：95%时间在线，偶尔短暂静默
        st.active = Math.random() > 0.05;
        st.nextToggle = now + (st.active ? 8000 + Math.random() * 30000 : 2000 + Math.random() * 5000);
      } else {
        // 时发：占空比约20-40%
        st.active = !st.active;
        st.nextToggle = now + (st.active
          ? 3000  + Math.random() * 15000   // 发射持续3-18秒
          : 10000 + Math.random() * 40000); // 静默10-50秒
      }
    }
    return st.active;
  }

  // ─────────────────────────────────────────────
  // 运营商频段精确定义（只有特定子频段有信号）
  // ─────────────────────────────────────────────
  const CARRIER_BANDS = [
    // GSM：上行890-915MHz / 下行935-960MHz（各25MHz带宽）
    { name: 'GSM上行', startMHz: 890,  endMHz: 915,  level: -45, bwMHz: 0.2, type: 'gsm' },
    { name: 'GSM下行', startMHz: 935,  endMHz: 960,  level: -38, bwMHz: 0.2, type: 'gsm' },
    // 4G 700: B28 上行703-748 / 下行758-803
    { name: '4G B28上', startMHz: 703,  endMHz: 733,  level: -44, bwMHz: 1.0, type: 'lte' },
    { name: '4G B28下', startMHz: 758,  endMHz: 788,  level: -38, bwMHz: 1.0, type: 'lte' },
    // 4G 1.8G: B3 上行1710-1785 / 下行1805-1880
    { name: '4G B3上', startMHz: 1710, endMHz: 1785, level: -42, bwMHz: 1.0, type: 'lte' },
    { name: '4G B3下', startMHz: 1805, endMHz: 1880, level: -36, bwMHz: 1.0, type: 'lte' },
    // 4G 2.1G: B1 上行1920-1980 / 下行2110-2170
    { name: '4G B1上', startMHz: 1920, endMHz: 1980, level: -42, bwMHz: 1.0, type: 'lte' },
    { name: '4G B1下', startMHz: 2110, endMHz: 2170, level: -36, bwMHz: 1.0, type: 'lte' },
    // 4G 2.6G: B41 2496-2690 TDD（不分上下行）
    { name: '4G B41',  startMHz: 2496, endMHz: 2690, level: -40, bwMHz: 2.0, type: 'lte' },
    // 5G 3.5G: n78 3300-3600MHz
    { name: '5G n78',  startMHz: 3300, endMHz: 3600, level: -38, bwMHz: 4.0, type: '5g'  },
    // 5G 4.9G: n79 4800-4900MHz
    { name: '5G n79',  startMHz: 4800, endMHz: 4900, level: -40, bwMHz: 4.0, type: '5g'  },
  ];

  // 运营商频段内的具体载波位置（模拟3家运营商，各有固定RB分配）
  // 每家运营商在各频段分配固定的子频段
  const CARRIER_SUBCHANNELS = {};
  CARRIER_BANDS.forEach(band => {
    const bw = band.endMHz - band.startMHz;
    const subs = [];
    // 模拟3家运营商各占约1/3带宽，有间隔保护带
    const guard = bw * 0.03;
    const opBw  = (bw - guard * 4) / 3;
    for (let i = 0; i < 3; i++) {
      subs.push({
        startMHz: band.startMHz + guard + i * (opBw + guard),
        endMHz:   band.startMHz + guard + i * (opBw + guard) + opBw,
        level:    band.level + i * 2,  // 三家电平略有差异
      });
    }
    CARRIER_SUBCHANNELS[band.name] = subs;
  });

  // ─────────────────────────────────────────────
  // GNSS干扰事件
  // ─────────────────────────────────────────────
  const _gnssJamEvents = [];
  let _gnssJamTimer = null;

  function _scheduleNextGnssJam() {
    clearTimeout(_gnssJamTimer);
    const delay = (40 + Math.random() * 80) * 1000;
    _gnssJamTimer = setTimeout(() => {
      const siteId  = SITES[Math.floor(Math.random() * SITES.length)].id;
      const freqs   = [1575.42, 1561.098];
      const targetFreq = freqs[Math.floor(Math.random() * freqs.length)];
      const duration = (2 + Math.random() * 5) * 60 * 1000;
      _gnssJamEvents.push({
        siteId,
        freqMHz:   targetFreq,
        startTime: Date.now(),
        endTime:   Date.now() + duration,
        level:     -78 + Math.random() * 12,
      });
      const now = Date.now();
      while (_gnssJamEvents.length > 0 && _gnssJamEvents[0].endTime < now) _gnssJamEvents.shift();
      _scheduleNextGnssJam();
    }, delay);
  }
  _scheduleNextGnssJam();

  function isGnssJammed(siteId, freqMHz) {
    const now = Date.now();
    for (const ev of _gnssJamEvents) {
      if (ev.siteId === siteId && Math.abs(ev.freqMHz - freqMHz) < 2 && ev.startTime <= now && now <= ev.endTime) {
        return ev.level;
      }
    }
    return null;
  }

  // ─────────────────────────────────────────────
  // 核心：获取某站点某频率的瞬时电平（dBm）
  // ─────────────────────────────────────────────
  function getInstantLevel(siteId, freqMHz, atTime) {
    // atTime 用于历史数据生成，默认当前时间
    const t = atTime !== undefined ? atTime : Date.now();

    // 底噪 + 轻微随机
    let level = NOISE_FLOOR_MIN + Math.random() * (NOISE_FLOOR_MAX - NOISE_FLOOR_MIN);

    // ── FM广播 ──────────────────────────────
    if (freqMHz >= 87.5 && freqMHz <= 108) {
      const coverage = SITE_FM_COVERAGE[siteId] || { indices: [], offset: 0 };
      let bestLevel = level;
      for (const idx of coverage.indices) {
        const sta = FM_STATIONS[idx];
        if (!sta) continue;
        const dist = Math.abs(freqMHz - sta.freq);
        if (dist < 0.1) { // 200kHz信道内
          // 信道内电平随距离中心衰减，模拟带内起伏
          const roll = Math.sin(t / 3000 + sta.freq * 7) * 1.5 + Math.random() * 1.5;
          const chanLevel = sta.level + coverage.offset + roll - dist * 15;
          if (chanLevel > bestLevel) bestLevel = chanLevel;
        }
      }
      return bestLevel;
    }

    // ── 对讲机 VHF ──────────────────────────
    if (freqMHz >= 150 && freqMHz <= 174) {
      const channels = SITE_WALKY_CHANNELS[siteId] || [];
      for (const ch of channels) {
        if (ch.band !== 'VHF') continue;
        // 检查是否命中该信道（25kHz带宽内）
        if (Math.abs(freqMHz - ch.freq) < 0.0125 || Math.abs(freqMHz - ch.pairFreq) < 0.0125) {
          // 历史数据用确定性状态（基于时间切片）
          let active;
          if (atTime !== undefined) {
            // 历史模式：用时间种子决定状态
            const slice = Math.floor(atTime / (ch.alwaysOn ? 10000 : 30000));
            const seed = ((siteId * 997 + ch.freq * 1000 + slice) | 0) >>> 0;
            const r = (seed * 1664525 + 1013904223) >>> 0;
            active = ch.alwaysOn ? (r % 100 > 5) : (r % 100 < 30);
          } else {
            active = _getChannelActive(siteId, ch.freq, ch.alwaysOn);
          }
          if (active) {
            return ch.level + (Math.random() * 4 - 2);
          }
        }
      }
      return level;
    }

    // ── 对讲机 UHF ──────────────────────────
    if (freqMHz >= 400 && freqMHz <= 430) {
      const channels = SITE_WALKY_CHANNELS[siteId] || [];
      for (const ch of channels) {
        if (ch.band !== 'UHF') continue;
        if (Math.abs(freqMHz - ch.freq) < 0.0125 || Math.abs(freqMHz - ch.pairFreq) < 0.0125) {
          let active;
          if (atTime !== undefined) {
            const slice = Math.floor(atTime / (ch.alwaysOn ? 10000 : 30000));
            const seed = ((siteId * 997 + ch.freq * 1000 + slice) | 0) >>> 0;
            const r = (seed * 1664525 + 1013904223) >>> 0;
            active = ch.alwaysOn ? (r % 100 > 5) : (r % 100 < 30);
          } else {
            active = _getChannelActive(siteId, ch.freq, ch.alwaysOn);
          }
          if (active) {
            return ch.level + (Math.random() * 4 - 2);
          }
        }
      }
      return level;
    }

    // ── 航空通信 VHF 118-137MHz ──────────────
    if (freqMHz >= 118 && freqMHz <= 137) {
      // 航空信道步进25kHz，大约只有4-6个频点有信号
      const aviFreqs = [118.1, 119.3, 121.5, 123.45, 127.0, 131.8, 135.0];
      for (const af of aviFreqs) {
        if (Math.abs(freqMHz - af) < 0.015) {
          const slice = Math.floor((atTime || Date.now()) / 20000);
          const seed = ((siteId * 31 + af * 100 + slice) | 0) >>> 0;
          const r = (seed * 1664525 + 1013904223) >>> 0;
          if (r % 100 < 15) { // 约15%时间有信号
            return -52 + Math.random() * 10;
          }
        }
      }
      return level;
    }

    // ── 运营商频段 ───────────────────────────
    for (const band of CARRIER_BANDS) {
      if (freqMHz < band.startMHz || freqMHz > band.endMHz) continue;
      const subs = CARRIER_SUBCHANNELS[band.name] || [];
      for (const sub of subs) {
        if (freqMHz >= sub.startMHz && freqMHz <= sub.endMHz) {
          const t2 = atTime !== undefined ? atTime : Date.now();
          // 宽带信号内的多载波起伏
          const ripple = Math.sin(t2 / 2000 + freqMHz * 0.1) * 1.8
                       + Math.sin(t2 / 700  + freqMHz * 0.3) * 1.2
                       + (Math.random() - 0.5) * 2;
          return sub.level + ripple;
        }
      }
      // 在频段内但不在任何运营商子信道里（保护带）
      return level;
    }

    // ── GNSS ────────────────────────────────
    if (Math.abs(freqMHz - 1575.42) < 1.5 || Math.abs(freqMHz - 1561.098) < 1.5) {
      const jamLevel = isGnssJammed(siteId, freqMHz);
      if (jamLevel !== null) return jamLevel + (Math.random() * 4 - 2);
      return -128 + Math.random() * 6;
    }

    // ── 偶发短时窄带干扰（概率极低）────────────
    const spurKey  = Math.round(freqMHz / 0.025) * 0.025;
    const spurTime = Math.floor((atTime || Date.now()) / 12000);
    const spurSeed = ((siteId * 9999 + spurKey * 37 + spurTime) | 0) >>> 0;
    const sr = (spurSeed * 1664525 + 1013904223) >>> 0;
    if (sr % 10000 < 8) { // 0.08%概率，极稀疏
      level = -72 + Math.random() * 8;
    }

    return level;
  }

  // ─────────────────────────────────────────────
  // 获取频谱快照
  // ─────────────────────────────────────────────
  function getSpectrumSnapshot(siteId, startMHz, endMHz, points, atTime) {
    const result = new Float32Array(points);
    const step   = (endMHz - startMHz) / (points - 1);
    for (let i = 0; i < points; i++) {
      result[i] = getInstantLevel(siteId, startMHz + i * step, atTime);
    }
    return result;
  }

  // ─────────────────────────────────────────────
  // Max Hold 管理
  // ─────────────────────────────────────────────
  const _maxHoldStore = {};

  function updateMaxHold(key, spectrum) {
    if (!_maxHoldStore[key] || _maxHoldStore[key].length !== spectrum.length) {
      _maxHoldStore[key] = new Float32Array(spectrum.length).fill(-120);
    }
    const mh = _maxHoldStore[key];
    for (let i = 0; i < spectrum.length; i++) {
      if (spectrum[i] > mh[i]) mh[i] = spectrum[i];
    }
    return mh;
  }

  function getMaxHold(key)  { return _maxHoldStore[key] || null; }
  function clearMaxHold(key){ delete _maxHoldStore[key]; }

  // ─────────────────────────────────────────────
  // 功能二：站点批量采集
  // ─────────────────────────────────────────────
  function collectSiteResults(centerMHz, spanMHz, bwKHz, durationSec, onProgress, onComplete) {
    const startMHz = centerMHz - spanMHz / 2;
    const endMHz   = centerMHz + spanMHz / 2;
    const bwMHz    = bwKHz / 1000;
    const bwStart  = centerMHz - bwMHz / 2;
    const bwEnd    = centerMHz + bwMHz / 2;
    const POINTS   = 512;
    const frames   = Math.max(5, Math.round(durationSec * 2));
    let frame = 0;

    const siteMaxHolds = {};
    SITES.forEach(s => { siteMaxHolds[s.id] = new Float32Array(POINTS).fill(-120); });

    const interval = setInterval(() => {
      frame++;
      SITES.forEach(s => {
        const snap = getSpectrumSnapshot(s.id, startMHz, endMHz, POINTS);
        const mh = siteMaxHolds[s.id];
        for (let i = 0; i < POINTS; i++) if (snap[i] > mh[i]) mh[i] = snap[i];
      });
      if (onProgress) onProgress(frame / frames);

      if (frame >= frames) {
        clearInterval(interval);
        const results = SITES.map(s => {
          const mh = siteMaxHolds[s.id];
          let maxLv = -120;
          const step = (endMHz - startMHz) / (POINTS - 1);
          for (let i = 0; i < POINTS; i++) {
            const freq = startMHz + i * step;
            if (freq >= bwStart && freq <= bwEnd && mh[i] > maxLv) maxLv = mh[i];
          }
          return { site: s, maxLevel: maxLv, spectrum: mh, startMHz, endMHz };
        });
        results.sort((a, b) => b.maxLevel - a.maxLevel);
        if (onComplete) onComplete(results);
      }
    }, (durationSec * 1000) / frames);

    return () => clearInterval(interval);
  }

  // ─────────────────────────────────────────────
  // 功能三：后台扫描 & 历史数据
  // ─────────────────────────────────────────────

  // 关键采样频点
  const KEY_FREQS = (() => {
    const freqs = new Set();

    // FM台站
    FM_STATIONS.forEach(s => freqs.add(parseFloat(s.freq.toFixed(4))));

    // 对讲信道（所有站点的活跃信道）
    SITES.forEach(s => {
      (SITE_WALKY_CHANNELS[s.id] || []).forEach(ch => {
        freqs.add(ch.freq);
        freqs.add(ch.pairFreq);
      });
    });

    // 航空
    [118.1, 119.3, 121.5, 123.45, 127.0, 131.8, 135.0].forEach(f => freqs.add(f));

    // 运营商子信道代表频点
    CARRIER_BANDS.forEach(band => {
      const subs = CARRIER_SUBCHANNELS[band.name] || [];
      subs.forEach(sub => {
        const center = (sub.startMHz + sub.endMHz) / 2;
        freqs.add(parseFloat(center.toFixed(3)));
      });
    });

    // GNSS
    freqs.add(1575.42);
    freqs.add(1561.098);

    // 背景代表频点（稀疏）
    [50, 80, 200, 300, 500, 600, 800, 1000, 1400, 2000, 3000, 5000, 6000, 7500].forEach(f => freqs.add(f));

    return [...freqs].sort((a, b) => a - b);
  })();

  // 历史数据存储
  const _scanHistory = {};
  SITES.forEach(s => { _scanHistory[s.id] = {}; });

  let _scanInterval    = null;
  let _scanSimTime     = null;
  let _scanStartTime   = null;
  let _scanGranMin     = 1;
  let _scanAccel       = 60;
  const _scanCallbacks = new Set();

  // ── 预生成6小时历史数据（页面加载时调用） ──────
  function _prebuildHistory() {
    const GRANULARITY_MIN = 1;
    const HOURS = 6;
    const PERIODS = HOURS * 60 / GRANULARITY_MIN; // 360个周期
    const PERIOD_MS = GRANULARITY_MIN * 60 * 1000;
    const now = Date.now();
    const historyStart = now - HOURS * 3600 * 1000;

    SITES.forEach(s => {
      _scanHistory[s.id] = {};
    });

    for (let p = 0; p < PERIODS; p++) {
      const simT = historyStart + p * PERIOD_MS;
      SITES.forEach(s => {
        KEY_FREQS.forEach(freq => {
          // 每个周期内模拟5个采样取Max
          let maxLv = -120;
          for (let sample = 0; sample < 5; sample++) {
            const sampleT = simT + sample * (PERIOD_MS / 5);
            const lv = getInstantLevel(s.id, freq, sampleT);
            if (lv > maxLv) maxLv = lv;
          }
          const key = freq.toFixed(4);
          if (!_scanHistory[s.id][key]) _scanHistory[s.id][key] = [];
          _scanHistory[s.id][key].push({ t: simT, level: maxLv });
        });
      });
    }

    _scanSimTime   = now;
    _scanStartTime = historyStart;
    _scanGranMin   = GRANULARITY_MIN;
  }

  // ── 启动实时追加扫描 ──────────────────────────
  function startBackgroundScan(granularityMin = 1, accel = 60) {
    if (_scanInterval) return;
    _scanGranMin = granularityMin;
    _scanAccel   = accel;
    if (!_scanSimTime) {
      _scanStartTime = Date.now();
      _scanSimTime   = Date.now();
      SITES.forEach(s => { _scanHistory[s.id] = {}; });
    }

    const intervalMs  = (granularityMin * 60 * 1000) / accel;
    const sampleMs    = Math.min(500, intervalMs / 4);
    let accumulated   = 0;
    let periodMax     = {};
    SITES.forEach(s => { periodMax[s.id] = {}; });

    _scanInterval = setInterval(() => {
      accumulated  += sampleMs;
      _scanSimTime += sampleMs * accel;

      SITES.forEach(s => {
        KEY_FREQS.forEach(freq => {
          const lv  = getInstantLevel(s.id, freq);
          const key = freq.toFixed(4);
          if (periodMax[s.id][key] === undefined || lv > periodMax[s.id][key]) {
            periodMax[s.id][key] = lv;
          }
        });
      });

      if (accumulated >= intervalMs) {
        accumulated = 0;
        const simT  = _scanSimTime;
        SITES.forEach(s => {
          KEY_FREQS.forEach(freq => {
            const key = freq.toFixed(4);
            if (!_scanHistory[s.id][key]) _scanHistory[s.id][key] = [];
            _scanHistory[s.id][key].push({
              t:     simT,
              level: periodMax[s.id][key] !== undefined ? periodMax[s.id][key] : -92,
            });
            if (_scanHistory[s.id][key].length > 3000) _scanHistory[s.id][key].shift();
          });
          periodMax[s.id] = {};
        });
        _scanCallbacks.forEach(cb => cb({ simTime: simT }));
      }
    }, sampleMs);
  }

  function stopBackgroundScan() {
    if (_scanInterval) { clearInterval(_scanInterval); _scanInterval = null; }
  }

  function isScanRunning()    { return _scanInterval !== null; }
  function onScanUpdate(cb)   { _scanCallbacks.add(cb); return () => _scanCallbacks.delete(cb); }
  function getScanSimTime()   { return _scanSimTime; }
  function getScanStartRealTime() { return _scanStartTime; }

  // 查询历史：某站点、目标频率、分析带宽、时间范围
  function queryScanHistory(siteId, freqMHz, bwMHz, timeRangeMs) {
    const hist  = _scanHistory[siteId];
    if (!hist)  return [];
    const now   = _scanSimTime || Date.now();
    const since = now - timeRangeMs;
    const bwStart = freqMHz - bwMHz / 2;
    const bwEnd   = freqMHz + bwMHz / 2;

    // 找出带宽内所有已采样频点
    const relevant = KEY_FREQS.filter(f => f >= bwStart && f <= bwEnd);
    if (relevant.length === 0) {
      // 找最近频点
      let best = KEY_FREQS[0], bestD = Infinity;
      KEY_FREQS.forEach(f => { const d = Math.abs(f - freqMHz); if (d < bestD) { bestD = d; best = f; } });
      relevant.push(best);
    }

    // 按时间合并（取Max）
    const timeMap = {};
    relevant.forEach(freq => {
      const key = freq.toFixed(4);
      if (!hist[key]) return;
      hist[key].forEach(entry => {
        if (entry.t < since) return;
        if (timeMap[entry.t] === undefined || entry.level > timeMap[entry.t]) {
          timeMap[entry.t] = entry.level;
        }
      });
    });

    return Object.entries(timeMap)
      .map(([t, level]) => ({ t: Number(t), level }))
      .sort((a, b) => a.t - b.t);
  }

  function querySiteMaxLevels(freqMHz, bwMHz, timeRangeMs) {
    return SITES.map(s => {
      const hist  = queryScanHistory(s.id, freqMHz, bwMHz, timeRangeMs);
      const maxLv = hist.length > 0 ? Math.max(...hist.map(h => h.level)) : -120;
      return { site: s, maxLevel: maxLv, history: hist };
    }).sort((a, b) => b.maxLevel - a.maxLevel);
  }

  // 监测带宽定义（功能三扫描配置显示用）
  const MONITOR_BANDS = [
    { startMHz: 87.5,  endMHz: 108,   bwKHz: 200  },
    { startMHz: 118,   endMHz: 137,   bwKHz: 25   },
    { startMHz: 150,   endMHz: 174,   bwKHz: 25   },
    { startMHz: 400,   endMHz: 470,   bwKHz: 25   },
    { startMHz: 890,   endMHz: 960,   bwKHz: 200  },
    { startMHz: 703,   endMHz: 803,   bwKHz: 100  },
    { startMHz: 1710,  endMHz: 1880,  bwKHz: 100  },
    { startMHz: 1920,  endMHz: 2170,  bwKHz: 100  },
    { startMHz: 2496,  endMHz: 2690,  bwKHz: 100  },
    { startMHz: 3300,  endMHz: 3600,  bwKHz: 100  },
    { startMHz: 4800,  endMHz: 4900,  bwKHz: 100  },
    { startMHz: 1559,  endMHz: 1610,  bwKHz: 1000 },
  ];

  // 兼容旧代码
  function getBandForFreq(freqMHz) {
    for (const b of CARRIER_BANDS) {
      if (freqMHz >= b.startMHz && freqMHz <= b.endMHz) return b;
    }
    return null;
  }

  // ─────────────────────────────────────────────
  // 初始化：页面加载时预构建历史
  // ─────────────────────────────────────────────
  _prebuildHistory();
  // 预构建完成后，自动启动实时追加（加速比60，1分钟粒度）
  startBackgroundScan(1, 60);

  // ─────────────────────────────────────────────
  // 公开接口
  // ─────────────────────────────────────────────
  return {
    SITES,
    FREQ_START_MHZ,
    FREQ_END_MHZ,
    NOISE_FLOOR_MIN,
    NOISE_FLOOR_MAX,
    MONITOR_BANDS,
    FM_STATIONS,
    SITE_FM_COVERAGE,
    SITE_WALKY_CHANNELS,
    KEY_FREQS,

    getInstantLevel,
    getSpectrumSnapshot,
    getBandForFreq,
    isGnssJammed,
    getGnssJamEvents: () => [..._gnssJamEvents],

    updateMaxHold,
    getMaxHold,
    clearMaxHold,

    collectSiteResults,

    startBackgroundScan,
    stopBackgroundScan,
    isScanRunning,
    onScanUpdate,
    queryScanHistory,
    querySiteMaxLevels,
    getScanSimTime,
    getScanStartRealTime,
  };
})();
