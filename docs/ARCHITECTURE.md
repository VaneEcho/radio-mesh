# RF·MESH — 技术架构手册

> 版本：v1.0 | 更新日期：2026-03-16
> **面向对象：** 接手代码的开发者 / 新会话的 AI 助手
> **性质：** 反映当前已实现的状态，不是规划文档

---

## 目录

1. [系统概述](#1-系统概述)
2. [目录结构（实际）](#2-目录结构实际)
3. [关键数据流](#3-关键数据流)
4. [WebSocket 消息协议](#4-websocket-消息协议)
5. [REST API 参考](#5-rest-api-参考)
6. [数据库 Schema](#6-数据库-schema)
7. [Edge 配置文件说明](#7-edge-配置文件说明)
8. [驱动层接口约定](#8-驱动层接口约定)
9. [设计决策与取舍](#9-设计决策与取舍)
10. [已知问题与注意事项](#10-已知问题与注意事项)
11. [待构建模块](#11-待构建模块)

---

## 1. 系统概述

```
[ 接收机 (R&S EM550 / Tektronix RSA306B) ]
         │ SCPI over TCP / USB
[ 边缘节点软件 edge/ ]       ← 每站点部署一套，Python 同步单线程扫描
         │ WebSocket (主动上行，长连接)
         │ REST POST (上传聚合包 + 任务结果)
         ↓
[ 云端后端 cloud/ ]          ← FastAPI + TimescaleDB，专网中心服务器
         │ WebSocket
[ 云端前端 frontend/ ]       ← Vue 3 + ECharts，浏览器内运行
```

**核心约定：**
- Edge 永远主动连 Cloud，Cloud 不主动连 Edge（支持多站点 NAT 穿透场景）
- **Edge 只做时间维度压缩，不做频率维度合并**（信道划分、频段聚合、异常判断都在 Cloud 侧）
- 实时流按需触发（任务模式 `stream_fps > 0` 时开启），不常驻占带宽
- 两种工作模式（见下方第 3 节）：闲时后台扫描 vs 云端任务模式

---

## 2. 目录结构（实际）

```
radio-mesh/
├── edge/                           # 边缘节点（Python 3.11，同步）
│   ├── drivers/
│   │   ├── base.py                 # BaseSpectrumDriver ABC + SpectrumFrame dataclass
│   │   ├── em550.py                # R&S EM550 SCPI 驱动（PSCan/IFPAN/FSCan）
│   │   ├── mock.py                 # 仿真驱动（噪底 + 8 组预置信号，无需硬件）
│   │   └── rsa306b.py              # Tektronix RSA306B USB 驱动（tekrsa-api-wrap，40MHz分段）
│   ├── aggregator.py               # 时间窗口聚合（每 bin 取最大值，不做频率合并）
│   ├── heartbeat.py                # 注册 + WS 心跳线程 + 任务接收 + 实时流推送
│   ├── main.py                     # 入口：组装 Heartbeat + Uploader + Scanner
│   ├── models.py                   # SpectrumBundle pydantic 上传模型
│   ├── scanner.py                  # 扫描主循环 + 任务执行器（band_scan/channel_scan/if_analysis）
│   ├── uploader.py                 # 上传线程（Queue + 断网本地落文件）
│   ├── config.yaml.template        # 配置模板（em550/mock 两段注释切换）
│   └── requirements.txt
│
├── cloud/                          # 云端后端（FastAPI + psycopg2）
│   ├── routers/
│   │   ├── analysis.py             # 信号分析（本地检测 + Claude/OpenAI AI后端）
│   │   ├── band_rules.py           # 频段规则增删改查
│   │   ├── freq_assign.py          # 信道占用计算 API（云端按 band_rules 动态聚合）
│   │   ├── ingest.py               # 聚合包接收（Edge → Cloud 上传端点）
│   │   ├── query.py                # 历史数据查询 + 频点时间轴 + 历史回放快照
│   │   ├── signals.py              # 信号库 CRUD
│   │   ├── stations.py             # 站点注册 + WS 心跳端点（含 stream_frame 转发）
│   │   ├── stream.py               # 前端实时流 WS 订阅端点
│   │   └── tasks.py                # 任务增删改查 + Cloud→Edge 下发 + 任务过期
│   ├── connection_manager.py       # Edge WS 连接注册中心（1:1 per station）
│   ├── db.py                       # 连接池 + Schema + 全部 CRUD 函数
│   ├── main.py                     # FastAPI 应用（路由挂载、CORS、lifespan）
│   ├── models.py                   # Pydantic 请求/响应模型
│   ├── stream_manager.py           # 前端 WS 订阅注册中心（1:N per station）
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                       # 前端（Vue 3 + Vite + ECharts）
│   ├── src/
│   │   ├── api/index.js            # Axios API 客户端（所有 REST 调用）
│   │   ├── router/index.js         # Vue Router
│   │   ├── App.vue                 # 布局框架 + 侧边栏导航
│   │   ├── main.js                 # 应用入口（注册 ElementPlus + Router）
│   │   └── views/
│   │       ├── StationsView.vue        # 站点总览（在线/离线卡片，10s 自动刷新）
│   │       ├── SpectrumView.vue        # 历史频谱图（按帧浏览）
│   │       ├── FreqQueryView.vue       # 频点历史查询（时间轴 + 多站排名）
│   │       ├── FreqAssignView.vue      # 频率指配工具（信道占用图表 + CSV 导出）
│   │       ├── TaskView.vue            # 任务下发控制台（创建/列表/结果频谱预览）
│   │       ├── RealtimeView.vue        # 实时频谱（折线图 + 60帧瀑布图）
│   │       ├── PlaybackView.vue        # 历史回放（帧列表 + 播放控制 + A/B对比）
│   │       ├── AnalysisView.vue        # 信号分析（本地检测 + AI解读 + 人工审核）
│   │       ├── SignalLibraryView.vue   # 信号库管理（搜索 + 分页 + 编辑）
│   │       └── BandRulesView.vue       # 频段规则管理（增删改查）
│   ├── nginx.conf                  # /api → cloud:8000，含 WS 代理，SPA 回退
│   ├── Dockerfile
│   └── package.json
│
├── docs/
│   ├── ARCHITECTURE.md             # 本文件：技术架构手册（当前实现）
│   ├── REQUIREMENTS.md             # 需求与设计说明（含未实现的规划）
│   └── band_rules.yaml             # 频段规则初始数据（50条，基于工信部令62号）
│
├── docker-compose.yml              # cloud + timescaledb + frontend
├── PLAN.md                         # 原始工程任务分解（Phase 0–8，含部分规划未实现）
├── PROGRESS.md                     # 开发进度追踪（完成项目打勾）
└── README.md                       # 项目简介 + 快速启动
```

---

## 3. 两种工作模式

### 模式一：闲时后台扫描（Background Scan）

Edge 无任务时持续运行，做**时间维度压缩**后上传：

| 参数 | 值 |
|------|----|
| 扫描范围 | 设备全频段（EM550: 20MHz–3.6GHz） |
| 步进 | 25 kHz（上传原始粒度，不做频率合并） |
| 时间窗口 | 60 秒（`aggregation.interval_s`，可配置） |
| 聚合方式 | 每 bin 取最大值（max-hold） |
| 上传节奏 | 每分钟一帧，约 100–200 KB（gzip 后） |

### 模式二：任务模式（Task Mode）

Cloud 下发任务时触发，Edge 暂停后台扫描，执行任务并**实时流传**给云端：

| 参数 | 值 |
|------|----|
| 触发方式 | Cloud → Edge WS `task` 消息 |
| 传输方式 | 实时流（不走每分钟聚合上传） |
| FPS | 可配置：1 / 10 / 30 fps 或最大速率；**默认 10 fps** |
| 聚合窗口 | 1/FPS 秒（10fps → 每 100ms 聚合一次） |
| 聚合方式 | max-hold（默认）或 average（任务参数可指定） |
| 前端展示 | RealtimeView.vue 实时显示 |

> **FPS 参数的双重作用：** 降低 FPS → 减少带宽占用；提高 FPS → 提升时间分辨率（更细腻的动态）。

### 数据压缩原则（两种模式共同）

- **时间维度压缩**：Edge 负责（按窗口聚合后发送）
- **频率维度聚合**：Cloud 负责（查询时按 band_rules 动态计算，不在写入时合并）
- 原因：频段规则随时可能调整，云端统一管理，历史数据可用任意新规则重算

---

## 4. 关键数据流

### 4.1 后台常规扫描（持续运行）

```
Scanner._sweep()
  └─ driver.band_scan(start_hz, stop_hz, step_hz) → SpectrumFrame
       ├─ heartbeat.send_frame(b64, meta)          ← 实时流（rate-limited）
       └─ aggregator.update(frame) → aggregator.tick()
            └─ on_bundle(bundle) → uploader.submit(bundle)
                 └─ POST /api/v1/spectrum/bundle   ← HTTP 上传，独立线程
```

**聚合包格式（每 60s 一包，gzip 压缩）：**
```json
{
  "station_id":    "edge-01",
  "period_start_ms": 1710000000000,
  "period_end_ms":   1710000060000,
  "sweep_count":   3,
  "freq_start_hz": 20000000,
  "freq_step_hz":  25000,
  "num_points":    143200,
  "levels_b64":    "<base64(gzip(float32[]))>"
}
```

### 4.2 任务下发与执行

```
前端 POST /api/v1/tasks
  → 云端写入 tasks + task_stations 表
  → connection_manager.send(station_id, task_msg)  ← WS 推送
  → Edge heartbeat._handle_message → task_queue.put(msg)
  → Scanner._drain_tasks → _execute_task(driver, msg)
       ├─ band_scan / channel_scan / if_analysis
       └─ POST /api/v1/tasks/{task_id}/results  ← 回报结果
```

### 4.3 实时流（任务模式，按需）

```
Edge Scanner._sweep() 每帧
  → heartbeat.send_frame(b64, meta)
       └─ 帧率节流（_frame_interval = 1/stream_fps）
       └─ threading.Lock 保护 ws.send()

Cloud stations.py WS handler（receive stream_frame）
  → stream_manager.broadcast(station_id, payload)
       └─ 向所有订阅该站点的前端 WS clients 发送

Frontend RealtimeView.vue
  → WS /api/v1/stream/{station_id}/ws
  → onmessage → DecompressionStream → echarts.setOption()
```

---

## 4. WebSocket 消息协议

### 4.1 Edge ↔ Cloud 心跳通道

**端点：** `WS /api/v1/stations/{station_id}/ws`
（Edge 主动连接，用于心跳 + 任务下发 + 实时流上行）

| 方向 | 消息类型 | 结构 | 说明 |
|------|----------|------|------|
| Edge→Cloud | `ping` | `{"type":"ping","ts":<unix_ms>}` | 每 30s 一次 |
| Cloud→Edge | `pong` | `{"type":"pong","ts":<unix_ms>}` | 立即回复，同时写库更新 last_seen |
| Cloud→Edge | `task` | `{"type":"task","task_id":"...","task_type":"band_scan","params":{...}}` | 任务下发 |
| Edge→Cloud | `task_ack` | `{"type":"task_ack","task_id":"..."}` | 立即确认收到，接收后即执行 |
| Edge→Cloud | `task_progress` | `{"type":"task_progress","task_id":"...","progress":50}` | 进度上报（可选） |
| Edge→Cloud | `stream_frame` | 见下方 | 实时频谱帧 |

**stream_frame 结构：**
```json
{
  "type":       "stream_frame",
  "station_id": "edge-01",
  "b64":        "<base64(gzip(float32[num_points]))>",
  "meta": {
    "freq_start_hz": 20000000.0,
    "freq_step_hz":  25000.0,
    "num_points":    143200
  }
}
```

**任务 params 结构（按任务类型）：**
```json
// band_scan
{"start_hz": 20e6, "stop_hz": 3600e6, "step_hz": 25000}

// channel_scan
{"start_hz": 430e6, "stop_hz": 440e6, "step_hz": 12500, "demod_bw_hz": 10000}

// if_analysis
{"center_hz": 98.5e6, "span_hz": 200000}
```

### 4.2 Cloud ↔ 前端实时流

**端点：** `WS /api/v1/stream/{station_id}/ws`
（前端订阅，只接收数据，无需发送）

| 方向 | 消息类型 | 结构 |
|------|----------|------|
| Cloud→Frontend | `subscribed` | `{"type":"subscribed","station_id":"...","message":"Subscribed to live stream for ..."}` |
| Cloud→Frontend | `stream_frame` | 与 4.1 中 stream_frame 相同结构 |

---

## 5. REST API 参考

**Base URL：** `/api/v1`
**认证：** 写操作需 `Authorization: Bearer <token>`（token 为空时免鉴权）

### 站点

| Method | Path | 说明 |
|--------|------|------|
| POST | `/stations/register` | 站点注册（幂等） |
| GET | `/stations` | 获取所有站点及在线状态 |
| WS | `/stations/{station_id}/ws` | Edge 心跳通道 |

### 频谱数据

| Method | Path | 说明 |
|--------|------|------|
| POST | `/spectrum/bundle` | Edge 上传聚合包 |
| GET | `/spectrum` | 历史频谱帧列表（`?station_id=&start_ms=&stop_hz=&start_hz=`） |
| GET | `/spectrum/freq-timeseries` | 频点历史时间轴（`?freq_hz=&start_ms=&end_ms=&station_id=`） |

`freq-timeseries` 响应：
```json
{
  "stations": [
    {
      "station_id": "edge-01",
      "name":       "站点01",
      "max_dbm":    -42.1,
      "median_dbm": -68.3,
      "frame_count": 124,
      "timeseries": [[<unix_ms>, <dbm>], ...]
    }
  ]
}
```

### 频段规则

| Method | Path | 说明 |
|--------|------|------|
| GET | `/band-rules` | 获取所有规则 |
| POST | `/band-rules` | 新建规则 |
| PUT | `/band-rules/{rule_id}` | 修改规则 |
| DELETE | `/band-rules/{rule_id}` | 删除规则 |

### 频率指配

| Method | Path | 说明 |
|--------|------|------|
| POST | `/freq-assign` | 计算指定频段内各信道占用情况 |

请求体：
```json
{
  "station_id":    "edge-01",
  "start_hz":      935000000,
  "stop_hz":       960000000,
  "channel_bw_hz": 200000,
  "threshold_dbm": -95.0,
  "window_s":      3600
}
```

响应（按信道列表）：
```json
{
  "channels": [
    {
      "channel":     1,
      "freq_start_hz": 935000000,
      "freq_stop_hz":  935200000,
      "max_dbm":     -102.3,
      "status":      "free"   // "free" | "busy" | "no_data"
    }
  ],
  "summary": {"total": 125, "free": 98, "busy": 12, "no_data": 15}
}
```

### 任务

| Method | Path | 说明 |
|--------|------|------|
| GET | `/tasks` | 获取任务列表（`?limit=20`） |
| POST | `/tasks` | 创建并下发任务 |
| GET | `/tasks/{task_id}` | 获取任务详情（含各站点结果） |
| POST | `/tasks/{task_id}/results` | Edge 上报任务结果 |

创建任务请求体：
```json
{
  "type":       "band_scan",
  "station_ids": ["edge-01", "edge-02"],
  "params":     {"start_hz": 430e6, "stop_hz": 440e6, "step_hz": 25000},
  "stream_fps": 0
}
```

### 实时流

| Method | Path | 说明 |
|--------|------|------|
| WS | `/stream/{station_id}/ws` | 前端订阅实时频谱帧 |
| GET | `/stream/subscribers` | 查看当前订阅数（诊断用） |

---

## 6. 数据库 Schema

TimescaleDB（PostgreSQL 扩展）。应用启动时 `db.init_schema()` 自动建表。

```sql
-- 频谱帧（TimescaleDB 超表，按 recorded_at 分区）
CREATE TABLE spectrum_frames (
    frame_id       BIGSERIAL PRIMARY KEY,
    station_id     TEXT        NOT NULL,
    recorded_at    TIMESTAMPTZ NOT NULL,        -- 帧记录时间
    period_start   TIMESTAMPTZ NOT NULL,        -- 聚合窗口起始
    period_end     TIMESTAMPTZ NOT NULL,        -- 聚合窗口结束
    sweep_count    INT         NOT NULL,        -- 窗口内扫描次数
    freq_start_hz  FLOAT       NOT NULL,
    freq_step_hz   FLOAT       NOT NULL,
    num_points     INT         NOT NULL,
    levels_b64     TEXT        NOT NULL,        -- base64(gzip(float32[]))
    task_id        TEXT                         -- 关联任务（可空）
);
CREATE INDEX ix_sf_station_time ON spectrum_frames (station_id, recorded_at DESC);
-- 超表（通过 TimescaleDB）
SELECT create_hypertable('spectrum_frames','recorded_at', if_not_exists => TRUE);

-- 频段规则
CREATE TABLE band_rules (
    rule_id        BIGSERIAL PRIMARY KEY,
    name           TEXT        NOT NULL,
    freq_start_hz  FLOAT       NOT NULL,
    freq_stop_hz   FLOAT       NOT NULL,
    service        TEXT,
    authority      TEXT,
    notes          TEXT
);

-- 站点注册表
CREATE TABLE stations (
    station_id     TEXT PRIMARY KEY,
    name           TEXT        NOT NULL,
    registered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_ms   BIGINT,
    online         BOOLEAN     NOT NULL DEFAULT FALSE
);

-- 任务主表
CREATE TABLE tasks (
    task_id     TEXT PRIMARY KEY,
    type        TEXT        NOT NULL,   -- band_scan / channel_scan / if_analysis
    params      TEXT        NOT NULL,   -- JSON string
    stream_fps  INT         NOT NULL DEFAULT 0,
    status      TEXT        NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 任务×站点结果表
CREATE TABLE task_stations (
    task_id       TEXT        NOT NULL REFERENCES tasks(task_id),
    station_id    TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending',
    dispatched_at TIMESTAMPTZ,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    result_b64    TEXT,                 -- base64(gzip(float32[]))，任务结果频谱
    result_meta   TEXT,                 -- JSON：freq_start_hz, freq_step_hz, num_points
    error         TEXT,
    PRIMARY KEY (task_id, station_id)
);
```

**连接配置：** 环境变量 `DATABASE_URL`，默认 `postgresql://rfmesh:rfmesh@localhost:5432/rfmesh`。

---

## 7. Edge 配置文件说明

`edge/config.yaml`（从 `config.yaml.template` 复制创建）：

```yaml
station:
  id:   edge-01          # 站点唯一标识（同一云端内须唯一）
  name: "站点 01"

cloud:
  enabled: true          # false = 纯本地模式，不连云端
  url:     http://localhost:8000
  token:   ""            # 与云端 API_TOKEN 环境变量一致，空=免鉴权
  stream_fps: 2          # 实时流帧率上限（0 = 禁用实时流）

device:
  type: mock             # mock / em550 / rsa306b
  step_hz: 25000         # 默认扫描步进（EM550 仅支持离散值，驱动层自动对齐）

  # ── em550 专用参数 ──
  # host:         192.168.1.100
  # port:         5555
  # timeout_ms:   60000
  # detector:     PAVerage    # PAVerage / PMINimum / PMAXimum / PRMSrms
  # synth_mode:   FAST        # FAST / NORMal / LOWNoise
  # dwell_s:      0.001
  # agc:          true
  # mgc_dbuv:     50.0

  # ── mock 专用参数 ──
  # scan_delay_s: 0.1        # 仿真扫描延迟（0 = 无延迟）
  # seed:         42          # 随机种子，null = 每次随机

scan:
  start_hz: 20000000       # 20 MHz
  stop_hz:  3600000000     # 3600 MHz

aggregation:
  interval_s: 60.0         # 聚合窗口（秒）

debug:
  dump_raw_frames: false   # true = 每帧写本地文件（磁盘占用大，仅调试用）
  output_dir: ./output
```

---

## 8. 驱动层接口约定

`edge/drivers/base.py` 定义的 `BaseSpectrumDriver` ABC，所有驱动必须实现三个方法：

```python
class BaseSpectrumDriver(ABC):

    @abstractmethod
    def band_scan(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """PSCan 全频段扫描。驱动层自动分段，上层无感。"""

    @abstractmethod
    def if_analysis(
        self,
        center_hz: float,
        span_hz: float,
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """CW + IFPAN 窄带分析（EM550 需 EM550SU/EM550IM 选件）。固定 2049 点。"""

    @abstractmethod
    def channel_scan(
        self,
        start_hz: float,
        stop_hz: float,
        step_hz: float,
        demod_bw_hz: float,       # 必须 < step_hz，否则相邻信道串台
        station_id: str = "",
        task_id: str = "",
    ) -> SpectrumFrame:
        """FSCan 信道扫描，每点用中频方式测量。"""
```

`SpectrumFrame` 是普通 dataclass：
```python
@dataclass
class SpectrumFrame:
    station_id:   str
    timestamp_ms: int
    freq_start_hz: float
    freq_step_hz:  float
    levels_dbm:    np.ndarray   # dtype=float32
    task_id:       str = ""
    driver:        str = ""

    @property
    def num_points(self) -> int: ...
    @property
    def freq_stop_hz(self) -> float: ...
```

**注意：** 目前 scanner.py 调用驱动时**不传** `dwell_s` / `demod_bw_hz`（if_analysis） / `demod_mode` 参数，这些参数不在 base 接口中。如需添加，同时更新 `base.py`、`em550.py`、`mock.py` 和 `scanner.py`。

---

## 9. 设计决策与取舍

### 9.1 Edge 扫描循环：同步单线程

Edge 的扫描主循环是 **同步单线程**（`scanner.py`）。上传（`uploader.py`）和心跳（`heartbeat.py`）各是独立的 daemon 线程。

**原因：** SCPI 调用本身是同步阻塞的（TCP 读写），强行异步化反而增加复杂度。
**代价：** 任务执行期间后台扫描暂停（通过 `_drain_tasks` 在每轮扫描前检查）。

### 9.2 实时流走心跳 WebSocket

实时流帧（`stream_frame`）复用了 Edge 心跳 WebSocket，而不是单独开一个连接。

**原因：** Edge → Cloud 方向只能由 Edge 主动建连（NAT 穿透约定），多路复用已有连接最简单。
**代价：** 心跳消息和流帧共用同一条 TCP 连接，高帧率时可能引入 ping 延迟。实际场景中 2fps 完全无影响。

`heartbeat.send_frame()` 使用 `threading.Lock` 保证从 scanner 线程调用时线程安全（`websocket-client` 的 `send()` 本身也是线程安全的，双重保险）。

### 9.3 前端实时流单独 WebSocket

前端通过 `WS /api/v1/stream/{station_id}/ws` 订阅，而非复用其他 API 连接。

**原因：** 前端可能同时有多个页面/标签页订阅同一站点，`stream_manager` 支持 1:N 广播。如果混用会造成消息类型混乱。

### 9.4 频谱数据编码：base64(gzip(float32[]))

所有频谱数据（聚合包上传、任务结果、实时流帧）统一用此格式。

- **float32[]：** 每点 4 字节，精度足够（dBm 值通常 -120 ~ 0 范围，float32 精度 0.001 dBm）
- **gzip：** compresslevel=6，频谱数据重复性高，压缩率通常 60–80%
- **base64：** 方便放入 JSON 文本消息，避免二进制帧协议复杂度

解码路径（前端 JS）：`atob(b64) → Uint8Array → DecompressionStream('gzip') → ArrayBuffer → Float32Array`

### 9.5 信道聚合在查询时动态计算

频谱数据以原始 25 kHz 粒度存储，**不在写入时做信道合并**。信道划分、占用度计算等操作在 query 时按 band_rules 动态执行。

**原因：** 频段规则（信道带宽）可能调整，若写入时就合并，历史数据就无法用新规则重算。

---

## 10. 已知问题与注意事项

### 10.1 `psycopg2.execute()` 多语句

当前 `db.init_schema()` 用单次 `cur.execute(_SCHEMA_SQL)` 执行整个 DDL 块（多条 CREATE TABLE + 多条 CREATE INDEX + `SELECT create_hypertable`）。psycopg2 支持此模式，但 PostgreSQL 会把整块作为单个事务。如果 `create_hypertable` 失败（例如 TimescaleDB 未安装），整个 schema 初始化会回滚。

### 10.2 EM550 驱动未实测

`em550.py` 基于 R&S EM550 文档和 RsInstrument 库编写，未对真实设备做回归测试。特别注意：
- PSCan 步进必须是离散值（125Hz/250Hz/.../100kHz），驱动层自动向上取整到最近支持值
- IFPAN 需要 EM550SU 或 EM550IM 选件，无选件时 `if_analysis` 会报硬件错误
- dBµV → dBm 转换公式：`dBm = dBµV - 107`（基于 50 Ω 标准阻抗）

### 10.3 DecompressionStream 浏览器兼容性

`DecompressionStream('gzip')` 需要：Chrome 80+，Firefox 113+，Safari 16.4+。
如果需要支持旧浏览器，需要用 `pako` 等 JS 库替代。

### 10.4 scanner.py 循环导入

`scanner.py` 导入了 `from .heartbeat import Heartbeat`（仅用于类型注解）。`heartbeat.py` 不导入 scanner，目前没有循环导入问题。若未来需要 heartbeat 调用 scanner 的方法，需改用 `TYPE_CHECKING` 守护。

### 10.5 stream_manager 订阅者计数无锁

`stream_manager.subscriber_count()` 直接读 `_subs` dict，没有 asyncio lock。在单线程事件循环中是安全的，但如果未来引入多工作进程（uvicorn workers > 1），各进程有独立的内存，stream_manager 状态不共享，需要改用 Redis pub/sub 或类似方案。

### 10.6 任务结果上报走 HTTP，不走 WS

Edge 任务执行完毕后通过 HTTP POST `/api/v1/tasks/{task_id}/results` 上报结果，而不是通过已有的 WS 连接。

**原因：** 结果可能很大（完整频谱帧），HTTP 有更好的超时/重试语义。
**代价：** 每次上报都需要 HTTP 握手。

---

## 11. 已实现功能汇总（v1.1）

所有 Phase 0–8 均已完成初步实现，待设备联调：

| 模块 | 状态 | 说明 |
|------|------|------|
| Phase 0 基础框架 | ✅ | Docker Compose + WS 心跳 + DB Schema |
| Phase 1 边缘扫描 | ✅ | EM550 / RSA306B / Mock 驱动；1分钟聚合；任务执行 |
| Phase 2 云端接收 | ✅ | 7个 REST 路由；TimescaleDB 存储 |
| Phase 3 前端基础 | ✅ | 7个视图；Nginx + Docker |
| Phase 4 频率指配 | ✅ | 信道占用计算（云端动态聚合）+ 可视化 |
| Phase 5 任务+实时流 | ✅ | 任务链路；实时频谱；瀑布图；任务过期 |
| Phase 6 AI 信号分析 | ✅ | 本地检测 + Claude/OpenAI；人工审核工作流 |
| Phase 7 历史回放 | ✅ | 快照 API；逐帧播放；A/B 对比 |
| Phase 8 信号库 | ✅ | CRUD API + 前端管理页 |

## 12. 待完成 / 已知问题

### 12.1 联调阶段（接真实设备后）
- EM550 实机验证（SCPI 参数、电平转换）
- RSA306B 实机验证（tekrsa-api-wrap API 细节）

### 12.2 音频解调流（规划中，未实现）

IF 分析任务中的音频解调回传，设计方案：

- **优先**：若接收机支持解调（EM550 Annex E UDP 音频输出），由接收机解调，Edge 接收 UDP 流转发至 Cloud
- **降级**：若接收机不支持，Edge 对 IQ 数据做软件解调（AM/FM/SSB/CW），生成 PCM 音频
- **同步约定**：音频流和频谱帧必须时间对齐（打同一时间戳），前端同步播放，允许整体有固定延迟，但音画不能偏差

> 待实现：audio WebSocket 端点；前端音频播放器；Edge 音频采集/转发模块

### 12.3 瀑布图
- 当前方案：前端用历史频谱帧数据生成（每帧一行）
- 待研究：是否需要在 Edge/Cloud 侧预生成图像（PNG/JPEG）再传输

### 12.4 工程化（按需推进）
- 多 Worker 支持（stream_manager 改用 Redis pub/sub）
- 数据保留策略（定时清理 >3个月历史帧）
- 结构化日志 + 按天滚动
- Prometheus 指标暴露（可选）

---

*文档按实现状态更新，如果发现描述与代码不符，以代码为准。*
