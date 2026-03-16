# RF·MESH 项目推进状态

> 最后更新：2026-03-14

---

## 当前阶段：Phase 5 实时流完成，下一步历史回放（Phase 7）

整体策略：**先跑通主干数据链路，再逐步补全各功能模块。**

---

## 整体进度概览

```
[██████████] Phase 0  基础框架          ✅ 完成
[██████████] Phase 1  边缘扫描引擎       ✅ 完成（含实时流推送）
[██████████] Phase 2  云端数据接收       ✅ 完成
[██████████] Phase 3  前端基础           ✅ 完成（站点/频谱/任务/实时）
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
- [x] `docs/band_rules.yaml` — 频段规则初始版本（50 条规则，20 MHz–8 GHz，基于工信部令第62号）
- [x] `PROGRESS.md` — 本文件

### 需求对齐（沟通已确认）
- [x] 整体两层架构：Edge Agent + Cloud Server
- [x] Edge 主动连接 Cloud（注册制，便于多站点部署）
- [x] 设备驱动抽象层设计（兼容多厂商，初期适配一款参考设备）
- [x] **首批适配设备确认**：R&S EM550（第一优先，SCPI over Ethernet）+ RSA306B（第二，USB）
- [x] **R&S 设备接口方案**：`RsInstrument` Python 库（R&S 官方，纯 Socket，无需 VISA，适合 Linux）
- [x] **EM550 IF 带宽限制已知**：单次 IF 分析 10 kHz–9.6 MHz，驱动层自动分段拼接
- [x] **频段管理后台**：需求已设计，后台可视化配置页面（增删改查 + 频谱颜色块预览）
- [x] 全频段扫描：25 kHz 步进，1 分钟聚合包（最大值）上传
- [x] 实时流帧率控制：边缘节流，默认 5 fps，可配置，0 = 最快
- [x] 三大核心功能：频率指配 / 批量站点扫描 / 历史回放
- [x] 历史回放两层展示：电平时间线折线图 + 点击查看历史频谱快照
- [x] AI 分层处理策略：模板匹配 → 异常检测 → AI 初判 → 人工核实
- [x] **AI 多后端策略**：本地 Qwen2.5-VL 3B（调试）→ OpenAI / Gemini / Kimi（生产），统一接口切换
- [x] 台站信号库三类管理（自动归档 / AI+人工核实 / 纯人工）
- [x] 存储分层：TimescaleDB（时序统计）+ PostgreSQL（业务数据）+ 文件系统（频谱快照）
- [x] **数据保留策略**：所有数据最少保留 3 个月，软件不截断，容量由硬件扩容解决
- [x] 全频谱快照策略：低频常规存储 + 触发高频存储
- [x] **前端框架确认**：Vue 3 + Vite + Element Plus + ECharts

### Phase 0 — 基础框架 ✅
- [x] 技术栈确定：FastAPI + TimescaleDB + PostgreSQL（后端），Vue 3 + ECharts（前端）
- [x] 项目目录骨架：`edge/` / `cloud/` / `docs/` 结构建立
- [x] 共享数据模型：`edge/models.py`（SpectrumBundle Pydantic）、`cloud/models.py`（DB ORM）
- [x] Docker Compose 开发环境：`docker-compose.yml`（cloud + TimescaleDB + PostgreSQL）
- [x] Edge ↔ Cloud WebSocket 心跳通道（注册 + 保活）

### Phase 1 — 边缘扫描引擎
- [x] 设备驱动抽象接口：`edge/drivers/base.py`（`BaseSpectrumDriver` + `SpectrumFrame`）
- [x] EM550 驱动：`edge/drivers/em550.py`（PSCan 自动分段、IFPAN、FSCan、dBµV→dBm）
- [x] Mock 驱动：`edge/drivers/mock.py`（仿真噪底 + 8 组预置信号，无需硬件）
- [x] RSA306B 驱动：`edge/drivers/rsa306b.py`（占位，接口已定义）
- [x] 全频段扫描主循环：`edge/scanner.py`（SIGINT/SIGTERM 优雅退出）
- [x] 1 分钟聚合器：`edge/aggregator.py`（按窗口合并，最大值保留）
- [x] 聚合包上传：`edge/uploader.py`（独立线程，Queue，断网本地落文件）
- [x] 配置文件模板：`edge/config.yaml.template`（em550 / mock 两段注释切换）
- [ ] 频段合并预处理器（读取 band_rules.yaml，按频段分组上报）
- [ ] 任务执行器（接收云端指令，暂停常规扫描执行专项任务）
- [ ] 实时流发送模块（WebSocket 推送，含帧率节流）

### Phase 2 — 云端数据接收与存储
- [x] FastAPI 应用骨架：`cloud/main.py`（路由挂载、CORS、lifespan）
- [x] 聚合包接收 API：`cloud/routers/ingest.py`（`POST /api/v1/spectrum/bundle`）
- [x] 数据查询 API：`cloud/routers/query.py`（时段 / 频段 / 站点查询）
- [x] 频段规则 API：`cloud/routers/band_rules.py`（增删改查）
- [x] Dockerfile + 依赖：`cloud/Dockerfile`、`cloud/requirements.txt`
- [x] 数据库 Schema 初始化（`spectrum_frames` TimescaleDB 超表 + `band_rules` + `stations` 建表，应用启动自动执行）
- [x] 站点注册与心跳管理 API（`POST /api/v1/stations/register`，`WS /api/v1/stations/{id}/ws`）

---

## 进行中

### 需求对齐（待进一步讨论）
- [ ] 获取 EM550 编程手册 SCPI 命令集完整版（联系 R&S 销售）
- [ ] 台站信号库初始数据来源（空库 or 已有历史数据可导入）
- [ ] `band_rules.yaml` 中省/地方权限字段的细化

---

### Phase 3 — 前端基础
- [x] 项目初始化：`frontend/`（Vue 3 + Vite + Element Plus + ECharts）
- [x] 站点总览仪表盘（`StationsView.vue`，在线/离线卡片，10s 自动刷新）
- [x] 频谱查看页（`SpectrumView.vue`，ECharts 折线图，时间范围选择，帧时间线）
- [x] 频段规则管理页（`BandRulesView.vue`，增删改查）
- [x] Nginx 反向代理（`/api` → cloud:8000，含 WebSocket，SPA 回退）
- [x] 前端 Docker 多阶段构建；docker-compose.yml 新增 frontend 服务（:3000）
- [x] **频点查询页**（`FreqQueryView.vue`，输入频率+时间段，多站点排名+电平时间轴，max-pool 概览+缩放切原始分辨率）
- [ ] 任务下发控制台（创建任务、查看进度、结果频谱展示）
- [ ] WebSocket 实时推送（前端订阅站点状态变化，无需轮询）

## 进行中

### Phase 4 — 频率指配工具 ✅
- [x] 后端 DB 层：`query_channel_max_levels()` — 解压历史帧，按信道宽度分组，计算每信道最大电平
- [x] `POST /api/v1/freq-assign` — 输入频段+信道宽度+阈值+观测窗口 → 返回全信道占用表
- [x] `FreqAssignView.vue` — 站点选择、频段+信道宽度预设、阈值滑块、观测窗口选择
- [x] ECharts 柱状图概览（绿=空闲/红=占用，阈值标注线）
- [x] 信道明细表：全部/空闲/占用/无数据 标签页过滤 + 频率搜索 + CSV 导出

### Phase 5 — 任务下发 + 实时流 ✅
- [x] `cloud/connection_manager.py` — WebSocket 连接注册中心
- [x] `cloud/routers/tasks.py` — 任务增删改查 + Cloud→Edge 下发
- [x] `cloud/db.py` — tasks / task_stations 表，CRUD 函数
- [x] `edge/heartbeat.py` — 接收 Cloud 推送的 task 消息，task_ack 确认，投入 task_queue；`send_frame()` 带帧率限制的实时流推送
- [x] `edge/scanner.py` — drain_tasks() 每轮扫前优先执行，支持 band_scan / channel_scan / if_analysis，结果回报云端；每扫一帧调用 `heartbeat.send_frame()`
- [x] `TaskView.vue` — 任务控制台：创建/列表/详情/内联频谱预览
- [x] `cloud/stream_manager.py` — 前端订阅者注册中心（1:N per station）
- [x] `cloud/routers/stream.py` — `WS /api/v1/stream/{station_id}/ws` 前端订阅端点
- [x] `cloud/routers/stations.py` — 转发 Edge stream_frame 消息给所有订阅前端
- [x] `RealtimeView.vue` — 实时频谱折线图 + 瀑布图热图，帧计数 + fps 显示

### Phase 6 — AI 信号分析
- [ ] 频段模板配置（信道带宽规范化定义）
- [ ] 模板匹配初筛模块
- [ ] 异常检测规则引擎（带宽异常、电平基线偏离、频偏）
- [ ] 频谱图 / 瀑布图截图提取
- [ ] AI 多后端接口层（统一输入格式，支持 Qwen / OpenAI / Gemini / Kimi 切换）
- [ ] 本地 Qwen2.5-VL 3B 接入（调试用）
- [ ] 人工核实工作流（待核实队列、确认/修正界面）

### Phase 7 — 历史回放
- [ ] 全频谱快照存储（常规低频 + 触发高频）
- [ ] 历史查询 API（电平时间线 + 快照检索）
- [ ] 前端电平时间线折线图（含悬停交互）
- [ ] 点击时刻查看历史频谱图
- [ ] 多站点叠加展示

### Phase 8 — 台站信号库
- [ ] 信号记录数据模型完整设计
- [ ] 信号创建 / 更新 / 查询 API
- [ ] 与 AI 分析结果关联
- [ ] 库管理前端页面（筛选、详情、状态流转）
- [ ] 信号历史活动记录（时间线）

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-03-13 | v0.1 | 初始 PLAN.md，Phase 0–6 任务分解 |
| 2026-03-13 | v0.2 | 新增 REQUIREMENTS.md；补充设备抽象层、帧率控制、AI 分层策略、历史回放、台站信号库、存储设计 |
| 2026-03-13 | v0.3 | 新增 PROGRESS.md，拆分 Phase 7（历史回放）和 Phase 8（信号库）为独立阶段 |
| 2026-03-13 | v0.4 | 确认设备（EM550 + RSA306B）、AI 多后端策略、数据保留 3 个月、前端 Vue 3 + ECharts |
| 2026-03-13 | v0.5 | 明确 R&S EM550 接口方案（RsInstrument+SCPI）；创建 band_rules.yaml（50条规则，20MHz-8GHz）；设计频段管理后台需求 |
| 2026-03-13 | v0.6 | Phase 1 核心代码完成（scanner/aggregator/uploader/em550/mock 驱动）；Phase 2 API 骨架完成（FastAPI + ingest/query/band_rules 路由）；docker-compose.yml 开发环境就绪 |
| 2026-03-13 | v0.7 | Phase 0 完成：stations 表（DB Schema）+ 站点注册 REST API + WebSocket 心跳端点（Cloud）；edge/heartbeat.py 注册+保活线程（Edge）；Phase 0 全部打通 |
| 2026-03-13 | v0.8 | Phase 3 基础完成：frontend/ Vue 3 项目（站点总览 / 频谱查看 / 频段规则）；Nginx 多阶段 Docker；docker-compose 三服务全栈，localhost:3000 可用 |
| 2026-03-14 | v0.9 | Phase 4 完成：freq-assign API（信道占用计算）+ FreqAssignView.vue（柱图+表格+CSV）；Phase 5 任务链路：connection_manager + tasks 表 + tasks router + edge 任务接收/执行/上报；FreqQueryView（频点历史查询+时间轴）；TaskView（任务控制台+内联频谱预览）；修复 edge scanner 驱动调用参数错误 |
