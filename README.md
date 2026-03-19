# RF·MESH 无线电监测网格系统

多站点无线电频谱监测平台，由边缘采集节点与中心服务器协同构成，支持全频段持续扫描、任务驱动分析、实时频谱流和频率指配。

---

## 系统架构

```
[ 监测设备 (R&S EM550 / Tektronix RSA306B) ]
          │ SCPI over TCP  /  USB
[ 边缘节点软件 (edge/) ]     ← 每个站点部署一套（Linux 或 Windows）
          │ WebSocket（边缘主动上行，长连接）
          │ REST POST（聚合包 + 任务结果上传）
          ↓
[ 云端后端 (cloud/) ]        ← 专网内中心服务器，FastAPI + TimescaleDB
          │ WebSocket
[ 云端前端 (frontend/) ]     ← Vue 3 + ECharts，浏览器内运行
```

**关键设计：** Edge 永远主动连 Cloud，Cloud 通过已建立连接下发任务，无需访问各站点内网 IP（NAT 穿透友好）。

---

## 已实现功能

| 功能 | 说明 | 状态 |
|------|------|------|
| 全频段持续扫描 | EM550: 20 MHz–3.6 GHz；RSA306B: 9 kHz–6.2 GHz，25 kHz 步进，不间断运行 | ✅ |
| 聚合数据上传 | 每分钟上传最大值快照，gzip 压缩 base64 编码 | ✅ |
| 实时频谱流 | Edge WS 推送 → Cloud 广播 → 前端折线图 + 瀑布图（最大 30 fps） | ✅ |
| 频率指配工具 | 输入频段+信道宽度，输出各信道占用表，支持 CSV 导出 | ✅ |
| 任务下发 | 云端创建 band_scan / channel_scan / if_analysis 任务，下发到 Edge 执行，结果频谱预览 | ✅ |
| 频点历史查询 | 输入频率+时间段，多站点排名 + 电平时间轴（max-pool 概览 + 原始分辨率缩放） | ✅ |
| 频段规则管理 | 后台可视化增删改查，基于工信部令第 62 号 50 条初始规则 | ✅ |
| 站点总览 | 在线/离线状态卡片，最后心跳时间，10 s 自动刷新 | ✅ |

---

## 目录结构

```
radio-mesh/
├── edge/                        # 边缘节点（Python 3.11，同步单线程扫描）
│   ├── drivers/
│   │   ├── base.py              # BaseSpectrumDriver 抽象接口
│   │   ├── em550.py             # R&S EM550 SCPI/TCP 驱动（Linux/Windows）
│   │   ├── rsa306b.py           # RSA306B Linux 驱动（tekrsa-api-wrap + libRSA_API.so）
│   │   ├── rsa306b_win.py       # RSA306B Windows 驱动（ctypes 直调 RSA_API.dll）
│   │   └── mock.py              # 仿真驱动（无硬件开发/CI 用）
│   ├── aggregator.py            # 1 分钟滑动窗口聚合（时域 max-hold）
│   ├── heartbeat.py             # 注册 + WS 心跳 + 任务接收 + 实时流推送
│   ├── scanner.py               # 扫描主循环 + 任务执行器
│   ├── uploader.py              # 上传线程（断网本地缓存，自动重试）
│   ├── main.py                  # 入口
│   └── config.yaml.template     # 配置模板
│
├── cloud/                       # 云端后端（FastAPI + psycopg2）
│   ├── routers/
│   │   ├── stations.py          # 站点注册 + Edge WS 心跳端点
│   │   ├── ingest.py            # 聚合包接收
│   │   ├── query.py             # 历史数据查询 + 频点时间轴
│   │   ├── tasks.py             # 任务管理 + 下发
│   │   ├── freq_assign.py       # 信道占用计算
│   │   ├── band_rules.py        # 频段规则 CRUD
│   │   └── stream.py            # 前端实时流 WS 订阅端点
│   ├── connection_manager.py    # Edge WS 连接注册中心（1:1）
│   ├── stream_manager.py        # 前端 WS 订阅注册中心（1:N）
│   ├── db.py                    # 连接池 + Schema + CRUD
│   ├── models.py                # Pydantic 模型
│   └── main.py                  # FastAPI 应用入口
│
├── frontend/                    # 前端（Vue 3 + Vite + Element Plus + ECharts）
│   └── src/views/
│       ├── StationsView.vue     # 站点总览仪表盘
│       ├── RealtimeView.vue     # 实时频谱 + 瀑布图
│       ├── SpectrumView.vue     # 历史频谱浏览（zoom 自动切换原始分辨率）
│       ├── FreqQueryView.vue    # 频点历史查询
│       ├── FreqAssignView.vue   # 频率指配工具
│       ├── TaskView.vue         # 任务下发控制台
│       └── BandRulesView.vue    # 频段规则管理
│
├── docs/
│   ├── ARCHITECTURE.md          # 技术架构手册（API/WS 协议/DB/设计决策）
│   ├── REQUIREMENTS.md          # 需求与设计说明
│   └── band_rules.yaml          # 频段规则初始数据（50 条）
│
├── docker-compose.yml           # cloud + timescaledb + frontend 三服务
├── PROGRESS.md                  # 开发进度详细追踪
└── README.md                    # 本文件
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 边缘驱动（EM550） | Python 3.11，纯 Socket SCPI/TCP，SCPI 命令行协议 |
| 边缘驱动（RSA306B Linux） | `tekrsa-api-wrap` 1.3.3 + RSA_API-1.0.0014 `.so` |
| 边缘驱动（RSA306B Windows） | ctypes 直调 `RSA_API.dll`（来自 SignalVu-PC 安装目录） |
| 云端后端 | FastAPI，psycopg2，asyncio WebSocket |
| 时序数据库 | TimescaleDB（PostgreSQL 扩展），按时间分区 |
| 前端 | Vue 3 + Vite + Element Plus + ECharts 5 + pako |
| 数据编码 | `base64(gzip(float32[]))` 全链路统一 |
| 容器化 | Docker + Docker Compose |

---

## 快速启动

### 无硬件 Mock 模式（仅 Edge 本地运行）

```bash
pip install numpy pyyaml websocket-client
cp edge/config.yaml.template config.yaml
# 确保 device.type: mock，cloud.enabled: false
python -m edge.main --config config.yaml
```

### 完整联调（Edge + Cloud + 前端）

```bash
# 1. 启动云端所有服务（TimescaleDB + Cloud API + 前端 Nginx）
docker compose up -d --build

# 2. 配置并启动 Edge（Linux / WSL2）
cp edge/config.yaml.template config.yaml
# 编辑：cloud.enabled: true，cloud.url: http://localhost:8000
python -m edge.main --config config.yaml

# 3. 打开前端
# http://localhost:3000
# API 文档：http://localhost:8000/docs
```

> **前端开发热更新：**
> ```bash
> cd frontend && npm install && npm run dev
> # 访问 http://localhost:5173（/api 自动代理到 :8000）
> ```

---

## 硬件配置说明

### R&S EM550（SCPI/TCP，Linux/Windows 均支持）

```yaml
device:
  type: em550
  host: 192.168.1.100     # 设备 IP
  port: 5025              # SCPI TCP 端口
  step_hz: 25000          # 25 kHz 步进
  detector: PAVerage
  agc: true
scan:
  start_hz: 20000000      # 20 MHz
  stop_hz: 3600000000     # 3.6 GHz
```

### Tektronix RSA306B — Linux

依赖 `RSA_API-1.0.0014` 动态库（`.so`）和 `tekrsa-api-wrap` 1.3.3：

```yaml
device:
  type: rsa306b
  so_dir: /path/to/RSA_API-1.0.0014/
  device_index: 0
  rbw_hz: 10000
  trace_length: 1601      # 40 MHz / 1600 = 25 kHz 步进
  ref_level_dbm: 0.0
scan:
  start_hz: 9000          # 9 kHz
  stop_hz: 6200000000     # 6.2 GHz
```

### Tektronix RSA306B — Windows

需安装 [SignalVu-PC](https://www.tek.com/oscilloscope/mso2024-software/signalvu-pc)（随附 `RSA_API.dll`），edge 节点用 ctypes 直接调用，无需额外 Python 依赖：

```yaml
device:
  type: rsa306b
  dll_path: "C:\\Program Files\\Tektronix\\SignalVu-PC\\RSA\\HALSV\\DigitizerSourceFactories\\RSA_API.dll"
  device_index: 0
  rbw_hz: 10000
  trace_length: 1601      # 40 MHz / 1600 = 25 kHz 步进
  ref_level_dbm: 0.0
cloud:
  enabled: true
  url: http://<cloud-server-ip>:8000   # Windows 连 WSL2 Cloud 时使用 WSL2 IP
  token: ""
```

> **Windows Edge 启动：**
> ```powershell
> pip install numpy pyyaml websocket-client
> python -m edge.main --config config.yaml
> ```

---

## WS 协议快查

```
Edge → Cloud 心跳通道：WS /api/v1/stations/{station_id}/ws
  Edge→Cloud: {"type":"ping","ts":<ms>}
  Cloud→Edge: {"type":"pong","ts":<ms>}
  Cloud→Edge: {"type":"task","task_id":"...","task_type":"band_scan","params":{...}}
  Edge→Cloud: {"type":"task_ack","task_id":"..."}
  Edge→Cloud: {"type":"stream_frame","station_id":"...","b64":"...","meta":{...}}

前端实时流订阅：WS /api/v1/stream/{station_id}/ws
  Cloud→Frontend: {"type":"subscribed","station_id":"..."}
  Cloud→Frontend: {"type":"stream_frame",...}  ← 同上结构转发
```

---

## 相关文档

- **[技术架构手册](docs/ARCHITECTURE.md)** — API 参考、WS 协议、DB Schema、设计决策（新会话/接手必读）
- [需求与设计说明](docs/REQUIREMENTS.md) — 详细需求讨论记录，含未实现规划
- [开发进度](PROGRESS.md) — 详细完成状态追踪
