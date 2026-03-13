# RF·MESH 无线电监测网格系统

多站点无线电频谱监测平台，由边缘采集节点与中心服务器协同构成，支持全频段持续扫描、异常发现、任务驱动分析与台站信号建库。

---

## 系统架构

```
[ 监测设备 (R&S EM550 / Tektronix RSA306B) ]
          │ SCPI over TCP  /  USB
[ 边缘节点软件 (Edge Agent) ]   ← 每个站点部署一套
          │ WebSocket + REST（边缘主动向上建连）
          ↓
[ 云端服务器 (Cloud Server) ]   ← 专网内中心服务器
          │ WebSocket
[ 云端前端 (Web UI) ]
```

**连接方向：** Edge 主动向 Cloud 注册并维持长连接，Cloud 通过已建立的连接下发任务，无需逐一访问各站内网 IP。

---

## 主要功能

| 功能 | 说明 |
|------|------|
| 全频段持续扫描 | 20 MHz – 3.6 GHz（EM550），25 kHz 步进，不间断运行 |
| 聚合数据上传 | 每分钟上传滑动窗口最大值统计包，节省带宽 |
| 频率指配工具 | 输入两频段范围，自动计算各信道空闲度，输出可用信道列表 |
| 批量站点扫描 | 指定频点和带宽，同时触发多站点定向扫描，结果汇聚对比 |
| 实时频谱流 | 按需触发，WebSocket 推送实时频谱帧到前端（默认 5 fps） |
| 历史回放 | 电平时间线折线图 + 点击查看历史频谱快照 |
| AI 信号分析 | 模板匹配 → 异常检测 → AI 初判 → 人工核实，分层流水线 |
| 台站信号库 | 自动归档已知信号，支持 AI + 人工核实，逐步积累辖区信号档案 |
| 频段规则管理 | 后台可视化配置频段规则，对应《无线电频率划分规定》，不写死于代码 |

---

## 目录结构

```
radio-mesh/
├── edge/                        # 边缘节点软件（Python）
│   ├── drivers/                 # 设备驱动层
│   │   ├── base.py              # BaseSpectrumDriver 抽象接口 + SpectrumFrame
│   │   ├── em550.py             # R&S EM550 SCPI 驱动（已实现）
│   │   └── rsa306b.py           # Tektronix RSA306B 驱动（占位）
│   └── requirements.txt
├── docs/
│   ├── REQUIREMENTS.md          # 需求与架构设计说明（详细）
│   ├── band_rules.yaml          # 频段规则初始配置（50条，20MHz–8GHz）
│   └── ...
├── PLAN.md                      # 工程任务分解（Phase 0–8）
├── PROGRESS.md                  # 开发进度追踪
└── README.md                    # 本文件
```

> 云端后端（FastAPI）、前端（Vue 3）目录在 Phase 0 基础框架阶段创建。

---

## 技术栈

| 层 | 技术选型 |
|----|----------|
| 边缘驱动 | Python 3.11+，`RsInstrument`（R&S 官方 SCPI 库，纯 Socket） |
| 边缘运行时 | Python asyncio，Linux（Debian/Ubuntu） |
| 云端后端 | Python + FastAPI，WebSocket，REST |
| 时序数据库 | TimescaleDB（PostgreSQL 扩展） |
| 业务数据库 | PostgreSQL |
| 频谱快照 | 本地文件系统（压缩存储） |
| 前端 | Vue 3 + Vite + Element Plus + ECharts |
| AI 后端 | 本地 Qwen2.5-VL 3B（调试）/ OpenAI / Gemini / Kimi（生产），统一接口 |
| 容器化 | Docker + Docker Compose（云端服务） |

---

## 已适配设备

### R&S EM550（第一优先）

| 参数 | 值 |
|------|----|
| 频率范围 | 20 MHz – 3.6 GHz |
| 连接方式 | SCPI over TCP，默认端口 **5555** |
| PSCan 步进（RBW） | 125 Hz / 250 Hz / 500 Hz / 625 Hz / 1.25 kHz / 2.5 kHz / 3.125 kHz / 6.25 kHz / 12.5 kHz / 25 kHz / 50 kHz / 100 kHz（离散值） |
| 单次最大采集点数 | 2 048 点（驱动层自动分段拼接） |
| 电平单位 | dBµV（驱动层转换为 dBm 输出，50 Ω：dBm = dBµV − 107） |
| 参考手册 | R&S EM550 Manual, doc 4065.5119.32-06.00 |

```python
from edge.drivers import EM550Driver

with EM550Driver(host="192.168.1.100") as rx:
    # 全频段扫描（驱动层自动分 ~70 段，对上层透明）
    frame = rx.scan_range(20e6, 3600e6, step_hz=25_000, station_id="site-01")
    print(f"{frame.num_points} points, {frame.freq_start_hz/1e6:.1f}–{frame.freq_stop_hz/1e6:.1f} MHz")

    # IF 全景分析（窄带精细扫描，2049 点，需 EM550SU/EM550IM 选件）
    frame = rx.scan_ifpan(center_hz=98.5e6, span_hz=9.6e6, station_id="site-01")
```

### Tektronix RSA306B（第二优先，占位）

| 参数 | 值 |
|------|----|
| 频率范围 | 9 kHz – 6.2 GHz |
| 连接方式 | USB 3.0，`tekrsa-api-wrap` + `libRSA_API.so` |
| 最大实时带宽 | 40 MHz（驱动层自动分段拼接） |

---

## 频段规则配置

`docs/band_rules.yaml` 包含基于《中华人民共和国无线电频率划分规定》（工信部令第 62 号，2023 年 7 月施行）整理的 50 条频段规则，覆盖 20 MHz – 8 GHz：

- FM 广播（87.5–108 MHz，200 kHz 信道）
- 民用航空（118–137 MHz，25 kHz 信道）
- 公安/应急 PDT 集群（350–390 MHz，12.5 kHz）
- 四大运营商 4G/5G（700 / 900 / 1800 / 2100 / 2600 / 3500 / 4900 MHz）
- GNSS（GPS/北斗/Galileo/GLONASS L1 / L2 / L5）
- WiFi 2.4 GHz / 5 GHz ISM
- 其他专业对讲、卫星、雷达频段

规则通过后台管理页面维护，不写死于代码，支持随频率规划调整动态修改。

---

## 开发进度

详见 [PROGRESS.md](PROGRESS.md)。当前阶段：**Phase 0 基础框架**。

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 0 | 基础框架、数据模型、WebSocket 心跳 | 🔲 未启动 |
| Phase 1 | 边缘扫描引擎（驱动层已完成） | 🔲 未启动 |
| Phase 2 | 云端数据接收与存储 | 🔲 未启动 |
| Phase 3 | 前端基础（Vue 3） | 🔲 未启动 |
| Phase 4 | 频率指配工具 | 🔲 未启动 |
| Phase 5 | 批量站点扫描 + 实时流 | 🔲 未启动 |
| Phase 6 | AI 信号分析 | 🔲 未启动 |
| Phase 7 | 历史回放 | 🔲 未启动 |
| Phase 8 | 台站信号库 | 🔲 未启动 |

---

## 本地开发

```bash
# 边缘节点依赖
pip install -r edge/requirements.txt

# 连接测试（Telnet 验证 EM550 通信，默认端口 5555）
telnet <设备IP> 5555
# 输入：*IDN?  回车，应返回设备标识字符串
```

---

## 相关文档

- [需求与架构设计说明](docs/REQUIREMENTS.md) — 详细设计决策、数据模型、接口格式
- [工程任务分解](PLAN.md) — Phase 划分、子模块职责
- [频段规则配置](docs/band_rules.yaml) — 初始频段规则（可通过后台页面维护）
- R&S EM550 Manual: doc 4065.5119.32-06.00
- [RsInstrument (GitHub)](https://github.com/Rohde-Schwarz/RsInstrument)
- [tekrsa-api-wrap (GitHub)](https://github.com/NTIA/tekrsa-api-wrap)
