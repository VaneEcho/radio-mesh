# RF·MESH 下一阶段开发计划

> 文档版本：v1.0 | 创建日期：2026-03-16
> **用途：** 新会话接力文档。当前会话完成了 Phase 0–8 全部代码实现及架构文档修正，此文档描述接下来要做什么。

---

## 当前状态快照

```
Phase 0–8  全部代码已实现，合并入主分支
Phase 9    音频解调流      🔶 Cloud WS + 前端播放器已实现；Edge 硬件路径等设备
Phase 10   工程化加固      🔶 日志/数据保留/鉴权已实现；Redis pub/sub 待实现
Phase 11   部署运维文档    ✅ docs/DEPLOYMENT.md 已写
联调阶段   等待真实设备接入  ⏳ 取决于硬件到位时间
```

关键文档：
- `docs/ARCHITECTURE.md` — 当前代码结构、API 协议、DB Schema、设计决策（看这个快速上手）
- `docs/REQUIREMENTS.md` — 需求说明，含两种工作模式、音频同步要求
- `PROGRESS.md` — 已完成事项
- `PLAN.md` — 原始任务分解（部分已过时，以 ARCHITECTURE.md 为准）

---

## Phase 9：音频解调流

> **优先级：高**（核心功能，IF Analysis 任务的关键输出）

### 背景

IF Analysis 任务（`if_analysis`）要求同时输出：
1. IF 频谱帧（已实现）
2. 解调音频流（**未实现**）

两路数据必须时间对齐（持续匹配原则）：用户听到的声音 ≡ 当前屏幕上的频谱。

### 9.1 两套实现路径（按优先级）

#### 路径 A — EM550 硬件解调（优先）

EM550 支持 Annex E：Mass Data Output，以 UDP 推送解调后的 PCM 音频。

```
EM550 设备 UDP 推送 → edge/audio.py 接收 → 打时间戳 → heartbeat.send_audio()
```

实现步骤：
1. 研究 EM550 Annex E 协议文档（UDP 端口、包格式、采样率）
2. `edge/audio.py`：UDP socket 监听，提取 PCM 数据，每个音频块打 `timestamp_ms`（与同一时刻的频谱帧时间戳对齐）
3. `edge/drivers/em550.py`：新增 `start_audio_stream(demod_mode, sample_rate)` / `stop_audio_stream()` 方法
4. `edge/heartbeat.py`：新增 `send_audio_chunk(timestamp_ms, pcm_b64)` 方法，向 Cloud 发送 `audio_chunk` 消息

#### 路径 B — 软件解调（降级方案，用于 RSA306B 或无 Annex E 选件时）

```
RSA306B IQ 数据 → edge/demod.py（AM/FM/SSB/CW） → PCM → heartbeat.send_audio()
```

实现步骤：
1. `edge/demod.py`：基于 scipy.signal 实现 AM/FM/USB/LSB 解调
2. `edge/drivers/rsa306b.py`：`if_analysis` 返回 IQ 数据（而非仅频谱）
3. 传给 `demod.py` 解调，输出 PCM

### 9.2 Cloud 侧

新增 `cloud/routers/audio.py`：

```python
WS  /api/v1/audio/{station_id}/ws   # 前端订阅音频流
```

新增 `cloud/audio_manager.py`（与 stream_manager.py 镜像结构）：
- `register(station_id, ws)` / `unregister(ws)`
- `broadcast(station_id, payload)`

修改 `cloud/routers/stations.py`：
- `stations.py` 的 WebSocket handler 识别 `audio_chunk` 消息类型
- 调用 `audio_manager.broadcast(station_id, chunk)`

修改 `cloud/main.py`：
- 挂载 `audio.router`

### 9.3 Edge 配置文件

`edge/config.yaml` 新增字段：

```yaml
audio:
  enabled: true          # 是否启用音频解调
  mode: hardware         # hardware（EM550 Annex E）/ software（软件解调）
  udp_port: 5556         # EM550 Annex E UDP 推送端口（需查文档确认）
  sample_rate: 16000     # 16000 / 48000 Hz
```

### 9.4 前端

修改 `frontend/src/views/RealtimeView.vue`：
- 当前 IF Analysis 任务运行时，显示音频播放控件（播放/暂停/音量）
- 订阅 `WS /api/v1/audio/{station_id}/ws`
- 收到 `audio_chunk` → `AudioContext.decodeAudioData()` → `AudioBufferSourceNode.start(ctx.currentTime + latency_offset)`
- 时间同步：频谱帧 `timestamp_ms` 与音频块 `timestamp_ms` 对比，计算 offset，保持两路同步

### 9.5 时间对齐协议

所有音频块必须携带时间戳，格式：

```json
{
  "type":         "audio_chunk",
  "station_id":   "edge-01",
  "timestamp_ms": 1710000001000,
  "sample_rate":  16000,
  "channels":     1,
  "encoding":     "pcm_s16le",
  "pcm_b64":      "<base64(PCM bytes)>"
}
```

前端同步策略：
- 建立 `timestamp_to_audioCtxTime` 映射
- 每收到频谱帧，记录 `(frame.timestamp_ms, audioCtx.currentTime)`
- 播放音频时，用映射关系决定 `AudioBufferSourceNode.start()` 的精确时刻

---

## Phase 10：工程化加固

> **优先级：中**（可在联调阶段同步推进，不依赖硬件）

### 10.1 结构化日志

**Edge**：新增 `edge/logger.py`

```python
import logging, logging.handlers
handler = logging.handlers.TimedRotatingFileHandler(
    'logs/edge.log', when='midnight', backupCount=30
)
handler.setFormatter(logging.Formatter(
    '{"ts":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","msg":"%(message)s"}'
))
```

**Cloud**：`cloud/main.py` 配置 uvicorn access log + 应用日志，同样按天滚动。

目标格式：JSON 一行一条，便于 ELK/Loki 采集。

### 10.2 多 Worker 支持（Redis pub/sub）

当前 `cloud/stream_manager.py` 是进程内内存结构，不支持多 uvicorn worker。

修改方案：
1. `docker-compose.yml` 新增 Redis 服务（`redis:7-alpine`）
2. `cloud/stream_manager.py` 新增 Redis backend：
   - `broadcast()` 改为 `redis.publish(f"stream:{station_id}", payload)`
   - 每个 WS handler 订阅 `stream:{station_id}` channel
3. 保留 in-memory backend 作为单进程降级选项（环境变量 `STREAM_BACKEND=redis|memory`）

### 10.3 数据保留策略

在 `cloud/main.py` 的 lifespan 中新增后台循环 `_retention_loop()`：

```python
async def _retention_loop():
    while True:
        await asyncio.sleep(86400)  # 每天运行一次
        cutoff = datetime.now() - timedelta(days=settings.retention_days)  # 默认 90
        await db.delete_old_frames(cutoff)
```

在 `cloud/db.py` 新增：
```python
def delete_old_frames(cutoff: datetime) -> int:
    # DELETE FROM spectrum_frames WHERE recorded_at < cutoff
    # 利用 TimescaleDB chunk-level DROP 高效删除
```

配置项（环境变量 `DATA_RETENTION_DAYS`，默认 90）。

### 10.4 API 鉴权（Bearer Token）

当前 `cloud/main.py` 中 token 校验逻辑存在但为空时直接通过。

实际启用步骤：
1. `cloud/main.py`：完善 `verify_token()` 函数，空 token 返回 401
2. `cloud/.env.example`：新增 `API_TOKEN=<生产密钥>`
3. Edge `config.yaml`：`cloud.token` 填入对应密钥
4. 只对写操作（POST/PUT/DELETE）做鉴权，GET 查询接口可选

### 10.5 Docker 健康检查

`docker-compose.yml` 为各服务添加：

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/stations"]
  interval: 30s
  timeout: 10s
  retries: 3
```

---

## Phase 11：部署文档

> **优先级：低**（联调前写好，方便上线操作）

新建 `docs/DEPLOYMENT.md`，内容：

1. **前置要求**：Docker 20+、Docker Compose v2、TimescaleDB 2.x、Python 3.11+
2. **云端部署**：
   - `docker-compose.yml` 一键启动
   - 环境变量说明（`DATABASE_URL`、`API_TOKEN`、`DATA_RETENTION_DAYS`）
   - Nginx SSL 终止配置示例（Let's Encrypt / 自签证书）
3. **边缘端部署**：
   - `edge/config.yaml` 字段说明
   - 以 systemd service 运行（service 文件模板）
   - 连接设备（EM550 SCPI TCP / RSA306B USB udev rules）
4. **多站点注意事项**：
   - 每个站点 `station_id` 唯一
   - VPN/隧道配置建议（不强制，按网络情况）
5. **故障排查清单**

---

## 联调阶段任务

> 接入真实硬件后按此清单逐项验证，发现问题提 issue / 修 bug

### EM550 联调

| # | 验证项 | 预期结果 | 常见问题 |
|---|--------|----------|----------|
| 1 | TCP 连接到 EM550（端口 5555） | `IDN?` 返回设备型号 | IP 地址、防火墙 |
| 2 | PSCan 全频段（20M–3.6G，25kHz步进） | 约 143200 点，有明显 FM 广播峰 | 步进对齐、分段拼接边界 |
| 3 | dBµV → dBm 转换 | FM 强台 ~−50 dBm，匹配已知参考 | 转换公式 `dBm = dBµV - 107` |
| 4 | IFPAN（需 EM550SU 选件） | 2049 点，跨距 200 kHz | 选件未安装报错 |
| 5 | FSCan（信道扫描） | 每步进点一个电平值 | STEP 与 BW 配置 |
| 6 | Annex E UDP 音频 | UDP 包到达 edge 监听端口 | 端口配置、防火墙 |

### RSA306B 联调

| # | 验证项 | 预期结果 | 常见问题 |
|---|--------|----------|----------|
| 1 | USB 识别（tekrsa-api-wrap） | `DEVICE_Search()` 返回设备列表 | `libRSA_API.so` 路径、udev rules |
| 2 | 40 MHz 单段采集 | 1601 点频谱 | SPECTRUM_SetSettings 参数 |
| 3 | 全频段分段拼接（20M–3.6G） | 各段边界无明显跳变 | 段间频率重叠处理 |

### 数据链路端对端联调

1. Edge Mock 模式 → Cloud → 前端：验证各页面数据正确显示
2. Edge EM550 → Cloud → 前端：验证真实频谱数据流通
3. 任务下发完整链路：前端创建任务 → Cloud WS → Edge 执行 → 结果回传 → 前端展示
4. 实时流：前端 RealtimeView → Cloud WS → Edge 实时频谱
5. 历史回放：PlaybackView 选时段 → 快照API → ECharts 显示
6. AI 分析：AnalysisView 提交 → 本地检测 → Claude/OpenAI → 结果展示

---

## 优先级总结

```
已完成（不依赖硬件）：
  ├── ✅ Phase 9  音频全链路（demod.py、if_analysis_iq、AudioStreamer、EM550 Annex E、heartbeat、前端播放器）
  ├── ✅ Phase 10 工程化加固全部（日志/数据保留/鉴权/Redis pub/sub）
  └── ✅ Phase 11 部署文档（docs/DEPLOYMENT.md）

等设备到位后：
  ├── EM550 联调（逐项验证，见下方联调清单）
  ├── EM550 Annex E 验证（start_audio_stream SCPI 命令语法确认）
  └── RSA306B 联调（if_analysis_iq IQ 数据格式确认）
```

---

## 新会话快速上手

新 AI 会话接手时，按以下顺序阅读：

1. `docs/ARCHITECTURE.md` — 当前代码结构（必读）
2. `PROGRESS.md` — 已完成内容
3. `NEXT.md`（本文档）— 下一步任务
4. 根据任务类型按需读具体文件（见 ARCHITECTURE.md §2 目录结构）

**关键技术约定（不要违反）：**
- Edge 只做时间维度聚合，**绝不合并频率 bin**
- 实时流默认 10 fps，聚合窗口 = 1/FPS 秒
- 频谱数据统一编码：`base64(gzip(float32[]))`
- 所有业务逻辑（信道划分、异常检测）在 Cloud 侧执行
- 音频流与频谱帧必须时间戳对齐
