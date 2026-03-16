# RF·MESH 无线电监测网格系统 — 需求与设计说明

> 文档版本：v0.8 | 最后更新：2026-03-16
> 性质：研发对齐文档，记录架构决策与功能需求，随沟通持续更新

---

## 1. 系统定位

RF·MESH 是一套部署于专网环境的多站点无线电监测平台，由边缘节点与中心云端服务器协同构成。核心目标：

- **持续积累**：各站点不间断扫描，形成全频段历史电平数据库
- **数据集中**：所有数据回传云端，云端完整承载、存储、展示
- **历史查询与统计分析**：按站点 / 频率 / 时间段灵活查询历史数据，支持统计分析
- **异常发现**：通过频段规划 + AI 辅助，自动识别频谱中的异常信号
- **任务驱动**：支持对特定频段发起定向扫描任务，聚合多站结果
- **台站建库**：逐步建立覆盖辖区内所有已知信号的台站信号库

---

## 2. 整体架构

### 2.1 拓扑结构

```
[ 接收机（各厂商） ]
        │ SCPI / 私有协议
[ 边缘节点软件 (Edge Agent) ]    ← 每个监测站点部署一套
        │ 向上主动建立连接（WebSocket + REST）
        ↓
[ 云端服务器 (Cloud Server) ]    ← 专网内中心服务器
        │ WebSocket
[ 云端前端 (Web UI) ]
```

**连接方向约定：** Edge 主动向 Cloud 注册并建立长连接，Cloud 通过已建立的连接向 Edge 下发任务。

**网络规划：** 通过隧道技术将各站点与云端服务器纳入同一局域网（不同网段），降低穿透复杂度。

### 2.2 边缘软件本质：接收机控制程序

Edge Agent 的本质是**接收机控制程序**，不是数据采集脚本。它的职责：

1. 通过驱动层统一控制各厂商接收机
2. 在无云端任务时，后台持续执行常规扫描，将时间压缩后的频谱数据上传云端
3. 接收云端下发的任务指令，执行定向操作，上报结果
4. 维护与云端的长连接（注册、心跳、任务通道）

**关键设计原则：Edge 不做业务逻辑，只做数据压缩（时间维度）和传输。**
信道划分、频段合并、异常检测等业务逻辑全部在云端执行，理由：
- 频段规划参数可能调整，云端统一管理，改一处全网生效
- 每个站点单独维护参数则运维成本极高

### 2.3 接收机驱动抽象层

所有接收机驱动必须实现同一接口，对上层暴露三种标准操作：

#### 操作一：频段扫描（Band Scan）

给定频率范围 + 步进，快速逐点扫描，每个频率点返回一个电平值。

适用场景：后台空闲常规扫描、快速频谱概览。

| 参数 | 类型 | 说明 | 必须 |
|------|------|------|------|
| `start_hz` | float | 起始频率（Hz） | ✅ |
| `stop_hz` | float | 截止频率（Hz） | ✅ |
| `step_hz` | float | 步进 / RBW（Hz） | ✅ |
| `detector` | enum | 检波方式：`peak` / `average` / `rms` | ✅ |
| `dwell_s` | float | 每步驻留时间（秒） | ✅ |
| `agc` | bool | 自动增益开关 | ✅ |
| `attenuation_db` | float | 手动衰减值（AGC=false 时有效） | ✅ |
| `synth_mode` | enum | 合成器模式：`fast` / `normal` / `low_noise` | 可选 |

返回：`SpectrumFrame`（freq_start, freq_step, levels_dbm[]）

EM550 对应：PSCan 模式（`SENSe:FREQuency:MODE PSCan`）

> **EM550 硬件限制：** PSCan 步进为离散值（125 Hz / 250 Hz / ... / 100 kHz），MTRACE 每段最大 2 048 点，驱动层自动分段拼接，上层无感。

#### 操作二：中频分析（IF Analysis）

定点分析，对单个中心频率做高分辨率 IF 频谱，同时解调音频。

适用场景：对某个信号做精细分析、监听解调内容。

| 参数 | 类型 | 说明 | 必须 |
|------|------|------|------|
| `center_hz` | float | 中心频率（Hz） | ✅ |
| `span_hz` | float | IF 分析跨距（Hz） | ✅ |
| `demod_bw_hz` | float | 解调带宽（Hz） | ✅ |
| `demod_mode` | enum | 解调方式：`AM` / `FM` / `USB` / `LSB` / `CW` / `PM` / `IQ` | ✅ |
| `agc` | bool | 自动增益开关 | ✅ |
| `attenuation_db` | float | 手动衰减值 | ✅ |
| `audio_enabled` | bool | 是否启用解调音频实时回传 | ✅ |
| `audio_sample_rate` | int | 音频采样率（Hz，如 8000 / 16000 / 48000） | 可选 |

返回：`IFFrame`（IF 频谱，2049 点）+ 音频流（实时 UDP/WebSocket，`audio_enabled=true` 时）

EM550 对应：CW 模式 + IFPAN 选件（`SENSe:FREQuency:MODE CW` + `TRACe? IFPAN`）；音频流通过 UDP 推送（Annex E：Mass Data Output）。

> **EM550 IFPAN 限制：** 跨距为离散值（10 kHz / 25 kHz / ... / 9 600 kHz），固定 2 049 点，需安装 EM550SU 或 EM550IM 选件。

> **音频 × 频谱时间对齐（持续匹配原则）：**
> 音频流与 IF 频谱帧必须始终保持时间同步，即用户听到的声音与当前显示的频谱形态对应同一时刻。
> - EM550：IFPAN 帧与 Annex E UDP 音频包均携带硬件时间戳，Edge 转发时保留时间戳。
> - 软件解调（无硬件支持时）：Edge 将解调音频分块，每块附加与当前频谱帧相同的时间戳。
> - 前端：音频播放器与频谱图均以时间戳为基准同步渲染；整体延迟与真实世界相比可以有固定偏差，但两路数据之间的时间差不得超过一个帧率窗口（100 ms @ 10 fps）。

#### 操作三：信道扫描（Channel Scan）

在给定频率范围内逐信道步进，每个步进点用中频方式测量电平。
电平从**解调带宽**内取值，解调带宽须小于步进以避免串台。

适用场景：精确测量每个信道的占用电平；获得比 Band Scan 更准确的信道级电平值。

| 参数 | 类型 | 说明 | 必须 |
|------|------|------|------|
| `start_hz` | float | 起始频率（Hz） | ✅ |
| `stop_hz` | float | 截止频率（Hz） | ✅ |
| `step_hz` | float | 信道间隔（Hz），即步进 | ✅ |
| `demod_bw_hz` | float | 解调带宽（Hz），必须 < step_hz | ✅ |
| `dwell_s` | float | 每步驻留时间（秒） | ✅ |
| `detector` | enum | 检波方式 | ✅ |
| `agc` | bool | 自动增益开关 | ✅ |

返回：`SpectrumFrame`（每步进点一个电平值，测量带宽 = demod_bw_hz）

EM550 对应：FSCan / SWEep 模式（`SENSe:FREQuency:MODE SWEep`），使用 `BANDwidth` 设置解调带宽，与 `SWEep:STEP` 分开配置。

**已确认适配设备：**

| 设备 | 接口 | 驱动方式 | 状态 |
|------|------|----------|------|
| R&S EM550 VHF/UHF 数字宽带接收机 | SCPI over TCP，端口 **5555** | `RsInstrument` Python 库 | **第一优先，已在站点部署** |
| Tektronix RSA306B USB 频谱分析仪 | USB 3.0 | `tekrsa-api-wrap` + `libRSA_API.so` | 第二优先，**已完整实现**（40 MHz 分段拼接） |

---

## 3. 边缘节点软件（Edge Agent）

### 3.0 两种工作模式总览

Edge 运行时始终处于以下两种模式之一：

| 模式 | 触发条件 | 时间聚合窗口 | 聚合方式 | 频率合并 | 传输方式 |
|------|----------|------------|----------|----------|----------|
| **空闲/后台扫描** | 无云端任务 | 1 分钟（可配置） | max-hold（每 25 kHz bin 取最大值） | **不做** | REST 上传（60 s/包） |
| **任务实时流** | 云端下发任务 + `stream.enabled=true` | 1/FPS 秒 | max-hold 或 average（任务参数指定） | **不做** | WebSocket 实时推送 |

**核心原则：Edge 只在时间维度做压缩，从不合并频率 bin。** 频率聚合（按信道合并）在云端查询时按 band_rules 动态执行。

### 3.1 后台常规扫描（Background Scan，空闲时持续运行）

Edge 在无云端任务下发时，持续执行全频段 Band Scan，将时间压缩数据上传云端。

**扫描参数（EM550 默认配置）：**
- 扫描范围：20 MHz – 3 600 MHz（EM550 全频段）
- 步进：25 kHz（约 143 200 个频率点）
- 每次全频段扫描时间：取决于驻留时间和分段数，估计 2–5 分钟/次

**数据压缩（时间维度）：**
- 时间窗口：1 分钟（固定）
- 聚合方式：每个 25 kHz bin 取窗口内**最大电平值**（max-hold）
- **不做频率维度合并**（不划分信道，不应用频段规则）
- 上传内容：25 kHz 粒度的全频谱"1分钟最大值快照"

**数据量估算：**
- 143 200 点 × 4 字节（float32）≈ 573 KB/分钟（未压缩）
- gzip 压缩后约 100–200 KB/分钟（频谱数据重复性高）
- 按每站 10 Mbps 带宽，完全可接受

> **多站并发上传问题（待处理）：** 多站同时上传可能造成云端接收压力。处理方向：
> - 方案 A：Edge 启动时随机延迟 0–30 秒，错开上传时刻
> - 方案 B：云端接收端使用异步队列缓冲，解耦接收与写库速度
> - 暂不实现，首期单站验证通过后再处理

### 3.2 任务执行模式

Cloud 下发任务时，Edge 暂停后台扫描，执行任务，完成后恢复。

支持的任务类型对应接收机三种操作：

| 任务类型 | 对应操作 | 典型用途 |
|----------|----------|----------|
| `band_scan` | 频段扫描 | 快速检查某频段频谱 |
| `if_analysis` | 中频分析 | 精细分析单个信号，含音频监听 |
| `channel_scan` | 信道扫描 | 精确测量某频段各信道电平 |

### 3.3 实时频谱流

任务参数中 `stream.enabled = true` 时，Edge 将扫描结果实时推送至 Cloud（WebSocket 二进制帧）。

**帧率控制：**
- Edge 侧节流，**默认 10 fps**，可选 1 / 10 / 30 fps
- FPS 同时控制两件事：**传输带宽**（帧率越高数据量越大）+ **时间分辨率**（聚合窗口 = 1/FPS 秒）
- 每帧在 1/FPS 秒窗口内对所有扫描结果做 max-hold 或 average（任务参数 `stream.aggregate` 指定）
- `stream.aggregate` 默认为 `max`，可选 `average`

**音频与频谱时间对齐：**
- `if_analysis` 任务开启音频解调（`audio_enabled=true`）时，音频流与频谱帧必须携带匹配时间戳
- 前端播放时按时间戳对齐，确保听到的声音与当前频谱帧是同一时刻采集的
- 允许两路数据都有固定传输延迟，但两路延迟必须相同（或在同一帧率窗口内）

---

## 4. 云端功能模块

云端完整承载边缘发来的所有数据，并在此基础上提供以下功能：

### 4.1 频段规则与信道管理（云端专属）

**频段规则数据库（band_rules）** 只在云端维护，不下发至边缘节点。

每条规则字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | 整数 | 规则 ID |
| `freq_start_mhz` | 浮点 | 频段起始（MHz） |
| `freq_end_mhz` | 浮点 | 频段结束（MHz） |
| `service_name` | 字符串 | 业务名称（如"FM广播"） |
| `service_type` | 枚举 | `broadcasting / aviation / maritime / pmr / mobile / gnss / satellite / amateur / radar / ism / government / other` |
| `channel_bw_khz` | 浮点 | 信道带宽（kHz），用于将原始 25 kHz bins 合并为信道 |
| `authority` | 枚举 | `national / provincial / local` |
| `operator` | 字符串（可空） | 归属运营商 |
| `description` | 字符串 | 备注 |
| `anomaly_bw_threshold_khz` | 浮点（可空） | 信号带宽超出此值时触发异常 |
| `enabled` | 布尔 | 是否启用 |

**管理后台页面：** 频段规则增删改查 + 频谱颜色块可视化预览。

初始数据来源：`docs/band_rules.yaml`（基于工信部令第 62 号，2023 年 7 月施行），导入云端数据库后 YAML 文件作为版本备份保留。

### 4.2 站点总览仪表盘

- 所有已注册站点的在线状态、最后心跳时间、当日数据量
- 实时推送站点状态变更

### 4.3 历史数据查询与统计分析

**基础查询场景：**
- 按站点 + 时间段查询某频率点的历史电平曲线
- 按时间段查询某频段的全频谱历史快照
- 多站对比：同一频率在不同站点的历史电平

**统计分析场景：**
- 频段占用率统计（某时间段内某频段的平均占用百分比）
- 电平分布直方图
- 信号出现时间规律分析
- 多站信号强度分布（用于判断信号来源方向）

**查询接口设计原则：**
- 信道聚合在查询时按 band_rules 动态计算，不预计算存储
- 支持原始分辨率（25 kHz）和信道分辨率两种返回格式

---

### 4.3.1 频点历史查询页（核心功能，待实现）

**入口：** 用户在搜索框输入一个频点（MHz），选择时间范围后查询。

**Step 1 — 多站汇总表：**

系统找到最近的 25 kHz bin，查询所有站点在该时间段内覆盖该频点的帧数据，展示一张站点汇总表：

| 字段 | 说明 |
|------|------|
| 站点 ID / 名称 | 识别站点 |
| 最大电平（dBm） | 该时段内该频点的最高检测值 |
| 中位电平（dBm） | 该时段内中位值，判断信号是否持续 |
| 检测帧数 | 该站点在时段内覆盖该频点的帧数 |

**排序：** 默认按最大电平从高到低，可切换按站点 ID 排序。

**Step 2 — 单站时间轴（点击展开）：**

点击某站点后，在下方展开（或跳转）该站点 × 该频点的时间轴图：

- **横轴：** 时间（精度 = 1 分钟，即每帧一个点）
- **纵轴：** 该频点电平（dBm）
- **数据点：** 从每帧的 25 kHz 粒度数据中提取对应 bin 的电平值

**时间轴压缩与展开策略（重要）：**

原则与频谱图相同——压缩显示时不能丢失信号峰值：

- **概览（缩小）：** 将可见时间范围内的帧 max-pool 压缩到目标点数，每个区间取最大电平值，确保信号出现的峰值不被平均掉
- **局部展开（放大）：** 当可见区间内数据点数 ≤ 目标点数时，直接显示所有原始点（1 分钟 / 点），并启用平滑插值（`smooth: true`）减少视觉锯齿感
- **交界行为：** 压缩 → 展开时，通过缩放事件实时切换数据集，避免跳帧感

**后端 API：**

```
GET /api/v1/spectrum/freq-timeseries
  ?freq_hz=<Hz>
  &start_ms=<Unix ms>
  &end_ms=<Unix ms>
  &station_id=<可选，不传则返回所有站点>
```

响应：

```json
{
  "freq_hz": 98100000,
  "freq_bin_hz": 98100000,
  "stations": [
    {
      "station_id": "ST-01",
      "name": "北区站",
      "max_dbm": -42.1,
      "median_dbm": -68.3,
      "frame_count": 87,
      "series": [
        { "t": 1741852800000, "dbm": -44.2 },
        { "t": 1741852860000, "dbm": -43.7 }
      ]
    }
  ]
}
```

**实现说明：**
- 云端从 `spectrum_frames` 中解压 `levels_gz`，找到 `(freq_hz - freq_start_hz) / freq_step_hz` 对应的 bin index，提取该 bin 的电平值
- 此操作在 Python 层完成（解压 → numpy 切片），不在 SQL 层做
- 当时间范围跨度大时，可在后端直接 max-pool 返回压缩系列（减少传输量），前端据此自适应分辨率

### 4.4 频率指配工具

**场景：** 为某业务分配工作频率，查询现有频段内哪些信道当前空闲。

**输入：**
- 上行频段范围（起止频率）
- 下行频段范围（起止频率）
- 信道带宽
- 查询时间窗（最近 N 分钟历史数据）
- 空闲判定阈值（默认 −95 dBm）
- 参与统计的站点

**输出：** 信道对照表（上下行对称），每信道显示最大电平和空闲/占用判断，可导出 CSV。

### 4.5 批量站点扫描任务

**场景：** 对特定频段发起多站同步扫描，汇聚结果判断信号空间分布。

**输入：** 中心频率、跨距、任务类型（band_scan / channel_scan / if_analysis）、扫描时长、参与站点。

**执行流程：**
1. Cloud 下发任务至各选中站点的 WebSocket 长连接
2. 各 Edge 执行扫描，上报结果
3. Cloud 汇聚展示：站点列表 + 各站电平对比

**实时回放（附加功能）：** 在汇总结果页点击任意站点触发实时频谱流，前端显示滚动频谱图 / 瀑布图。

### 4.6 历史数据回放

**输入：** 中心频率、分析带宽、历史时间范围、展示站点。

**展示层 1 — 电平时间线（折线图）：**
- 横轴：时间，纵轴：最大电平（dBm）
- 每站一条折线，支持单站 / 多站叠加

**展示层 2 — 历史频谱快照（点击展开）：**
- 点击时间线某时刻 → 弹出该时刻的频谱图
- 展示中心频率 ± 跨距范围内的频谱形态

---

## 5. AI 辅助信号分析

### 5.1 AI 模型策略

可插拔多后端，统一接口：

| 阶段 | 模型 |
|------|------|
| 调试 | 本地 Qwen2.5-VL 3B（图像输入） |
| 生产 | OpenAI GPT-4o / Gemini / Kimi / 豆包（按配置切换） |

### 5.2 分层处理流水线

```
原始频谱数据（云端存储）
    ↓
[第一层：频段模板匹配]（按 band_rules 逐信道判断是否有信号）
    ↓
[第二层：异常检测]（带宽异常 / 电平偏离基线 / 频率偏移）
    → 提取异常信号的频谱截图 + 瀑布图截图
    ↓
[第三层：AI 初判]（图像识别 + 频段知识库）
    ↓
[第四层：人工核实]（确认后入台站信号库）
```

### 5.3 台站信号库

| 类别 | 处理方式 |
|------|----------|
| AI 自动归档（高置信度） | 直接入库，人工抽查 |
| AI + 人工核实（中置信度） | 推送待核实队列 |
| 人工处理（AI 无法判断） | 推送处置工单 |

---

## 6. 数据存储设计

### 6.1 存储总原则

不在软件层设置数据截断，容量由硬件扩容解决。最少保留 3 个月。

| 数据类型 | 存储方式 | 保留策略 |
|----------|----------|----------|
| 1 分钟频谱统计帧 | TimescaleDB（二进制压缩列） | 最少 3 个月 |
| 全频谱快照文件 | 文件系统（压缩，按日目录） | 最少 3 个月 |
| 触发快照（告警/任务） | 同上，独立子目录 | 永久 |
| 台站信号库 | PostgreSQL | 永久 |
| 任务记录 | PostgreSQL | 永久 |
| 告警记录 | PostgreSQL | 永久 |
| 频段规则（band_rules） | PostgreSQL | 永久（可导出 YAML 备份） |

### 6.2 核心数据模型

**频谱统计帧（spectrum_frames）— TimescaleDB 超表：**
```
time            TIMESTAMPTZ    -- 1 分钟窗口起始时间（主分区键）
station_id      TEXT
freq_start_hz   BIGINT         -- 起始频率（Hz），通常 20_000_000
freq_step_hz    INT            -- 步进（Hz），通常 25_000
num_points      INT            -- 频率点数，通常 143_200
levels_dbm      BYTEA          -- float32 数组，gzip 压缩
sweep_count     SMALLINT       -- 本分钟内贡献的扫描次数
```

> **为何不按信道存行：** 143 200 点/分钟 × 所有站点 × 每月 43 200 分钟 ≈ 数十亿行，不适合按行存储。二进制压缩列可将每帧压缩至 100–200 KB，查询时解压并在内存中应用 band_rules 做信道聚合。

**全频谱快照索引（spectrum_snapshots）：**
```
snapshot_id     UUID
station_id      TEXT
captured_at     TIMESTAMPTZ
trigger_type    TEXT           -- routine / task / alarm
task_id         TEXT（可空）
freq_start_hz   BIGINT
freq_step_hz    INT
num_points      INT
data_path       TEXT           -- 压缩文件路径（.npz 或 .msgpack）
```

**台站信号库（signals）：**
```
signal_id         TEXT (主键, SIG-XXXXXX)
freq_center_mhz   FLOAT
bandwidth_khz     FLOAT
modulation        TEXT
signal_type       TEXT
status            ENUM(auto_archived, pending_review, manual)
confidence        FLOAT
first_seen        TIMESTAMPTZ
last_seen         TIMESTAMPTZ
occurrence_count  INT
ai_conclusion     TEXT
tags              TEXT[]
notes             TEXT
```

### 6.3 全频谱快照存储策略

- **常规模式**：每 5 分钟存一帧
- **任务/告警触发**：执行期间每分钟存一帧（或每次扫描完即存）
- **格式**：NumPy `.npz`（float32 levels + freq metadata），压缩比约 3–5×

---

## 7. 关键接口协议

### 7.1 频谱统计帧（Edge → Cloud，每分钟上传）

```json
{
  "station_id": "ST-01",
  "period_start_ms": 1741852800000,
  "period_end_ms":   1741852860000,
  "sweep_count": 3,
  "freq_start_hz": 20000000,
  "freq_step_hz": 25000,
  "num_points": 143200,
  "levels_dbm_b64": "<base64 encoded gzip float32 array>"
}
```

> 说明：`levels_dbm_b64` 是对 float32 数组先 gzip 压缩再 base64 编码的结果，约 150–200 KB。
> 云端解码后得到 143 200 个 float32 电平值，与 `freq_start_hz + i * freq_step_hz` 一一对应。

### 7.2 任务指令格式（Cloud → Edge，WebSocket）

```json
{
  "task_id": "TASK-000123",
  "type": "band_scan",
  "params": {
    "start_hz": 430000000,
    "stop_hz": 440000000,
    "step_hz": 25000,
    "detector": "peak",
    "dwell_s": 0.01
  },
  "stream": {
    "enabled": true,
    "fps": 10,
    "aggregate": "max"
  }
}
```

`type` 可选值：`band_scan` / `if_analysis` / `channel_scan`

`if_analysis` 的 params 示例：
```json
{
  "center_hz": 433920000,
  "span_hz": 200000,
  "demod_bw_hz": 15000,
  "demod_mode": "FM",
  "audio_enabled": true,
  "audio_sample_rate": 16000
}
```

`channel_scan` 的 params 示例：
```json
{
  "start_hz": 430000000,
  "stop_hz": 440000000,
  "step_hz": 25000,
  "demod_bw_hz": 16000,
  "dwell_s": 0.05,
  "detector": "average"
}
```

### 7.3 实时频谱帧（Edge → Cloud，WebSocket 二进制）

| 字段 | 类型 | 说明 |
|------|------|------|
| station_id | string | 站点 ID |
| task_id | string | 关联任务 ID |
| timestamp | int64 | Unix 时间戳（毫秒） |
| freq_start_hz | float64 | 起始频率 |
| freq_step_hz | float32 | 步进 |
| levels | float32[] | 电平数组（dBm） |

---

## 8. 已决策的设计要点

| 决策项 | 结论 | 原因 |
|--------|------|------|
| 连接方向 | Edge 主动连接 Cloud | 多站点部署方便，无需逐一配置 Cloud 侧站点 IP |
| 驱动抽象 | 三种标准操作（Band Scan / IF Analysis / Channel Scan） | 统一多厂商接口，切换设备只改驱动 |
| 信道合并位置 | **云端执行，Edge 不做** | 频段规划参数可能调整，云端集中管理，避免逐站更新 |
| 上传格式 | 25 kHz 粒度原始频率点 + 1 分钟最大值，二进制压缩 | 保留原始分辨率供云端灵活查询；压缩后带宽可接受 |
| 存储格式 | 每帧二进制压缩（BYTEA），不按信道行存 | 143 200 行/分钟不适合行存，压缩列高效存取 |
| 帧率控制 | 边缘节流，默认 10 fps，可选 1/10/30 | FPS 同时决定传输带宽与时间分辨率（聚合窗口 = 1/FPS 秒） |
| AI 策略 | 分层处理（模板→异常→AI→人工） | 端到端识别不可靠，分层保证可控性 |
| AI 后端 | 可插拔多后端（本地 Qwen → 云端多模态） | 调试用本地，生产按需切换 |
| 快照存储 | 低频常规 + 触发高频 | 平衡写入 IO 与回放需求 |
| 数据保留 | 不设软件截断，最少 3 个月 | 容量由硬件保障，软件不限制 |
| 时序数据库 | TimescaleDB | 原生时序压缩，SQL 接口 |
| 信号库数据库 | PostgreSQL | 关系型，JSONB 灵活扩展 |
| 前端框架 | Vue 3 + Vite + Element Plus + ECharts | 中文生态成熟 |
| R&S 接口 | `RsInstrument` + 原始 SCPI（TCP Socket，端口 5555） | 官方维护，无需 VISA，适合 Linux |
| band_rules 位置 | **云端数据库，唯一来源** | 频率规划与站点无关，集中管理 |

---

## 9. 首期实现范围（MVP）

**目标：** 用 EM550 跑通完整数据链路，验证可行性。

**Edge 侧：**
- [x] EM550 驱动（Band Scan / IF Analysis / Channel Scan）
- [ ] 后台常规扫描主循环（Band Scan，1 分钟最大值聚合）
- [ ] 频谱统计帧压缩上传
- [ ] WebSocket 长连接（注册、心跳、任务接收）

**Cloud 侧：**
- [x] 频谱统计帧接收 API（解码 + 写 TimescaleDB）
- [x] 历史频谱查询 API（按站点 + 时间段取全频谱帧）
- [x] 频段规则数据库 + 管理页面（band_rules CRUD）
- [ ] 频点历史查询 API（§4.3.1，按频点 + 时间段跨站查询电平时间序列）
- [ ] Cloud → Edge 任务下发通道（WebSocket）

**前端：**
- [x] 站点总览页（在线状态、心跳时间）
- [x] 站点频谱查看页（全频谱帧浏览 + max-pool 缩放）
- [x] 频段规则管理页
- [ ] 频点历史查询页（§4.3.1）
- [ ] 任务下发控制台

**暂不实现：**
- IF Analysis 音频流（需 Annex E UDP 流协议，后续加）
- AI 分析流水线
- 频率指配工具
- 多站并发上传优化

---

## 10. 待对齐事项

| # | 问题 | 影响模块 |
|---|------|----------|
| 1 | EM550 音频流协议细节（Annex E: Mass Data Output，UDP 流格式） | IF Analysis 音频回传 |
| 2 | 台站信号库初始数据来源（空库 or 有历史数据可导入） | 信号库模块 |
| 3 | band_rules 权限层级字段细化（部分频段省内有自主权） | 频段规则管理 |
| 4 | 多站并发上传优化方案确认（随机抖动 vs 云端队列缓冲） | Edge 上传模块 / Cloud 接收层 |
