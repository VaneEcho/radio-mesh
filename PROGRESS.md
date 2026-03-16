# RF·MESH 项目推进状态

> 最后更新：2026-03-16

---

## 当前阶段：Phase 0–5 全部完成，下一步 Phase 7（历史回放）

整体策略：**先跑通主干数据链路，再逐步补全各功能模块。**

---

## 整体进度概览

```
[██████████] Phase 0  基础框架          ✅ 完成
[██████████] Phase 1  边缘扫描引擎       ✅ 完成（含实时流推送）
[██████████] Phase 2  云端数据接收       ✅ 完成
[██████████] Phase 3  前端基础           ✅ 完成（站点/频谱/查询/任务/实时）
[██████████] Phase 4  频率指配工具       ✅ 完成（API + 前端）
[██████████] Phase 5  批量扫描+实时流    ✅ 完成（任务链路 + 实时频谱 + 瀑布图）
[░░░░░░░░░░] Phase 6  AI 信号分析        未启动
[░░░░░░░░░░] Phase 7  历史回放           未启动
[░░░░░░░░░░] Phase 8  台站信号库         未启动
```

---

## 已完成

### 文档
- [x] `PLAN.md` — 工程任务分解（Phase 划分、目录结构、技术栈选型）
- [x] `docs/REQUIREMENTS.md` — 需求与设计说明（架构决策、数据模型、接口格式）
- [x] `docs/ARCHITECTURE.md` — 技术架构手册（实际文件结构、API/WS 协议、DB Schema、设计决策）
- [x] `docs/band_rules.yaml` — 频段规则初始版本（50 条规则，20 MHz–8 GHz，基于工信部令第62号）

### 需求对齐（沟通已确认）
- [x] 整体两层架构：Edge Agent + Cloud Server
- [x] Edge 主动连接 Cloud（注册制，便于多站点部署）
- [x] 设备驱动抽象层设计（兼容多厂商，初期适配 R&S EM550）
- [x] **首批适配设备**：R&S EM550（第一优先，SCPI over TCP）+ RSA306B（第二，USB）
- [x] **R&S 设备接口方案**：`RsInstrument` Python 库（官方，纯 Socket，无需 VISA）
- [x] 全频段扫描：25 kHz 步进，1 分钟聚合包（最大值）上传
- [x] 实时流帧率控制：Edge 节流，默认 2 fps，可配置，0 = 禁用
- [x] **前端框架确认**：Vue 3 + Vite + Element Plus + ECharts
- [x] 数据保留策略：最少保留 3 个月，软件不截断
- [x] AI 分层处理策略：模板匹配 → 异常检测 → AI 初判 → 人工核实（未来 Phase 6）

### Phase 0 — 基础框架 ✅
- [x] 项目目录骨架：`edge/` / `cloud/` / `docs/` / `frontend/` 结构建立
- [x] Docker Compose 开发环境（cloud + TimescaleDB + frontend）
- [x] Edge ↔ Cloud WebSocket 心跳通道（注册 + 保活 + 在线状态维护）
- [x] DB Schema 初始化（应用启动自动执行 `init_schema()`）

### Phase 1 — 边缘扫描引擎 ✅
- [x] 设备驱动抽象接口：`edge/drivers/base.py`（`BaseSpectrumDriver` + `SpectrumFrame`）
- [x] EM550 驱动：`edge/drivers/em550.py`（PSCan 自动分段、IFPAN、FSCan、dBµV→dBm）
- [x] Mock 驱动：`edge/drivers/mock.py`（仿真噪底 + 8 组预置信号，无需硬件）
- [x] RSA306B 驱动：`edge/drivers/rsa306b.py`（占位，接口定义完毕，实现待补）
- [x] 全频段扫描主循环：`edge/scanner.py`（SIGINT/SIGTERM 优雅退出）
- [x] 1 分钟聚合器：`edge/aggregator.py`（按窗口合并，每 bin 取最大值）
- [x] 聚合包上传：`edge/uploader.py`（独立线程，Queue，断网本地落文件）
- [x] 实时流发送：`edge/heartbeat.py`（`send_frame()`，threading.Lock，帧率节流）
- [x] 任务执行器：`edge/scanner.py`（`_drain_tasks`，band_scan / channel_scan / if_analysis）

### Phase 2 — 云端数据接收与存储 ✅
- [x] FastAPI 应用骨架：`cloud/main.py`（路由挂载、CORS、lifespan）
- [x] 聚合包接收 API：`cloud/routers/ingest.py`（`POST /api/v1/spectrum/bundle`）
- [x] 数据查询 API：`cloud/routers/query.py`（历史帧列表 + 频点时间轴）
- [x] 频段规则 API：`cloud/routers/band_rules.py`（增删改查）
- [x] 站点注册与心跳 API：`cloud/routers/stations.py`（注册 + WS 端点）
- [x] DB CRUD 函数：`cloud/db.py`（连接池 + 全部 CRUD）
- [x] Dockerfile + 依赖完整

### Phase 3 — 前端基础 ✅
- [x] 项目初始化：`frontend/`（Vue 3 + Vite + Element Plus + ECharts）
- [x] 站点总览仪表盘（`StationsView.vue`，在线/离线卡片，10s 自动刷新）
- [x] 历史频谱查看页（`SpectrumView.vue`，ECharts 折线图，帧时间线浏览）
- [x] 频段规则管理页（`BandRulesView.vue`，增删改查）
- [x] 频点历史查询（`FreqQueryView.vue`，多站点排名 + 时间轴，max-pool 概览 + 原始分辨率缩放）
- [x] Nginx 反向代理（`/api` → cloud:8000，含 WebSocket，SPA 回退）
- [x] 前端 Docker 多阶段构建；docker-compose 三服务全栈

### Phase 4 — 频率指配工具 ✅
- [x] 后端 DB 层：`query_channel_max_levels()` — 解压历史帧，按信道宽度分组，计算每信道最大电平
- [x] `POST /api/v1/freq-assign` — 输入频段+信道宽度+阈值+观测窗口 → 返回全信道占用表
- [x] `FreqAssignView.vue` — 站点选择、频段+信道宽度预设（10 种）、阈值滑块、观测窗口选择
- [x] ECharts 柱状图概览（绿=空闲/红=占用，阈值标注线）
- [x] 信道明细表：全部/空闲/占用/无数据 标签页过滤 + 频率搜索 + CSV 导出

### Phase 5 — 任务下发 + 实时流 ✅
- [x] `cloud/connection_manager.py` — Edge WS 连接注册中心（1:1 per station）
- [x] `cloud/routers/tasks.py` — 任务增删改查 + Cloud→Edge 下发（WS push）
- [x] `cloud/db.py` — tasks / task_stations 表及 CRUD 函数
- [x] `edge/heartbeat.py` — 接收 task 消息，task_ack 确认，投入 task_queue；`send_frame()` 实时流推送（帧率节流 + threading.Lock）
- [x] `edge/scanner.py` — `_drain_tasks()` 每轮扫前优先执行，band_scan / channel_scan / if_analysis 结果回报云端；每扫一帧调用 `heartbeat.send_frame()`
- [x] `TaskView.vue` — 任务控制台：创建/列表/详情/内联频谱预览（SpectrumMini 组件）
- [x] `cloud/stream_manager.py` — 前端订阅者注册中心（1:N per station，async broadcast）
- [x] `cloud/routers/stream.py` — `WS /api/v1/stream/{station_id}/ws` 前端订阅端点
- [x] `cloud/routers/stations.py` — 转发 Edge stream_frame 消息给所有订阅前端
- [x] `RealtimeView.vue` — 实时频谱折线图 + 60 帧瀑布图热图，帧计数 + fps 显示

---

## 待开发

### 需求对齐（待进一步讨论）
- [ ] 获取 EM550 编程手册 SCPI 命令集完整版（联系 R&S 销售）
- [ ] 台站信号库初始数据来源（空库 or 已有历史数据可导入）
- [ ] `band_rules.yaml` 中省/地方权限字段的细化

### Phase 7 — 历史回放（推荐下一步）
- [ ] `GET /api/v1/spectrum/snapshots`：给定时间点，返回最近一帧完整频谱
- [ ] `HistoryView.vue`：电平时间轴折线图，点击时刻弹出历史频谱快照
- [ ] 多站点叠加展示（同一频率在不同站点的历史电平对比）

### Phase 6 — AI 信号分析
- [ ] 模板匹配初筛模块（本地规则，不调 AI）
- [ ] 异常检测规则引擎（带宽异常、电平基线偏离、频偏）
- [ ] 频谱图 / 瀑布图截图提取（送 AI 模型）
- [ ] AI 多后端接口层（统一输入格式，支持 Qwen / OpenAI / Gemini / Kimi 切换）
- [ ] 本地 Qwen2.5-VL 3B 接入（调试用）
- [ ] 人工核实工作流（待核实队列、确认/修正界面）

### Phase 8 — 台站信号库
- [ ] `signal_records` 表设计（频率、带宽、调制方式、归属台站）
- [ ] 信号创建 / 更新 / 查询 API
- [ ] 与 AI 分析结果关联
- [ ] 库管理前端页面（筛选、详情、状态流转、历史时间线）

### Phase 1 补全（低优先级）
- [ ] 频段合并预处理器（读取 band_rules.yaml，按信道聚合后上报，当前为原始 25kHz 粒度）

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-03-13 | v0.1 | 初始 PLAN.md，Phase 0–6 任务分解 |
| 2026-03-13 | v0.2 | 新增 REQUIREMENTS.md；补充设备抽象层、帧率控制、AI 分层策略、历史回放、台站信号库、存储设计 |
| 2026-03-13 | v0.3 | 新增 PROGRESS.md；拆分 Phase 7（历史回放）和 Phase 8（信号库）为独立阶段 |
| 2026-03-13 | v0.4 | 确认设备（EM550 + RSA306B）、AI 多后端策略、数据保留 3 个月、前端 Vue 3 + ECharts |
| 2026-03-13 | v0.5 | R&S EM550 接口方案（RsInstrument+SCPI）；band_rules.yaml（50条规则，20MHz–8GHz） |
| 2026-03-13 | v0.6 | Phase 1 核心代码完成（scanner/aggregator/uploader/em550/mock）；Phase 2 API 骨架（FastAPI + ingest/query/band_rules） |
| 2026-03-13 | v0.7 | Phase 0 完成：stations 表 + 站点注册 REST API + WebSocket 心跳端点；edge/heartbeat.py |
| 2026-03-13 | v0.8 | Phase 3 基础完成：frontend/ Vue 3（站点总览/频谱查看/频段规则）；Nginx Docker；docker-compose 三服务 |
| 2026-03-14 | v0.9 | Phase 4 完成（freq-assign API + FreqAssignView）；Phase 5 任务链路（connection_manager/tasks/heartbeat/scanner 任务执行）；FreqQueryView；TaskView；修复驱动调用参数 |
| 2026-03-16 | v1.0 | Phase 5 实时流完成（stream_manager/stream router/heartbeat.send_frame/RealtimeView 瀑布图）；新增 docs/ARCHITECTURE.md；README/PROGRESS 全面更新 |
