# RF·MESH 项目推进状态

> 最后更新：2026-03-16

---

## 当前阶段：Phase 0–8 全部实现，待设备联调

整体策略：**先跑通主干数据链路，再逐步补全各功能模块。**

> **架构确认（2026-03-16）：** 系统分两种工作模式 —— **空闲/后台扫描**（1分钟 max-hold 聚合，REST 上传）和 **任务实时流**（1/FPS秒聚合，默认 10fps，WebSocket 推送）。Edge 只做时间维度压缩，从不合并频率 bin；频率聚合（按 band_rules 信道合并）在云端查询时动态计算。

---

## 整体进度概览

```
[██████████] Phase 0  基础框架          ✅ 完成
[██████████] Phase 1  边缘扫描引擎       ✅ 完成（含实时流推送 + RSA306B驱动 + 1分钟聚合器）
[██████████] Phase 2  云端数据接收       ✅ 完成
[██████████] Phase 3  前端基础           ✅ 完成（站点/频谱/查询/任务/实时）
[██████████] Phase 4  频率指配工具       ✅ 完成（API + 前端）
[██████████] Phase 5  批量扫描+实时流    ✅ 完成（任务链路 + 实时频谱 + 瀑布图 + 任务过期）
[██████████] Phase 6  AI 信号分析        ✅ 完成（本地检测 + Claude/OpenAI后端 + 前端）
[██████████] Phase 7  历史回放           ✅ 完成（快照API + 逐帧播放 + 对比模式）
[██████████] Phase 8  台站信号库         ✅ 完成（CRUD API + 前端管理页）
```

---

## 已完成

### 文档
- [x] `PLAN.md` — 工程任务分解（Phase 划分、目录结构、技术栈选型）
- [x] `docs/REQUIREMENTS.md` — 需求与设计说明（架构决策、数据模型、接口格式）
- [x] `docs/ARCHITECTURE.md` — 技术架构手册（实际文件结构、API/WS 协议、DB Schema、设计决策）
- [x] `docs/band_rules.yaml` — 频段规则初始版本（50 条规则，20 MHz–8 GHz，基于工信部令第62号）

### Phase 0 — 基础框架 ✅
- [x] 项目目录骨架：`edge/` / `cloud/` / `docs/` / `frontend/` 结构建立
- [x] Docker Compose 开发环境（cloud + TimescaleDB + frontend）
- [x] Edge ↔ Cloud WebSocket 心跳通道（注册 + 保活 + 在线状态维护）
- [x] DB Schema 初始化（应用启动自动执行 `init_schema()`）

### Phase 1 — 边缘扫描引擎 ✅
- [x] 设备驱动抽象接口：`edge/drivers/base.py`（`BaseSpectrumDriver` + `SpectrumFrame`）
- [x] EM550 驱动：`edge/drivers/em550.py`（PSCan 自动分段、IFPAN、FSCan、dBµV→dBm）
- [x] Mock 驱动：`edge/drivers/mock.py`（仿真噪底 + 8 组预置信号，无需硬件）
- [x] **RSA306B 驱动**：`edge/drivers/rsa306b.py`（tekrsa-api-wrap，USB，40MHz分段拼接，完整实现）
- [x] 全频段扫描主循环：`edge/scanner.py`（SIGINT/SIGTERM 优雅退出）
- [x] 1 分钟聚合器：`edge/aggregator.py`（按窗口合并，每 bin 取最大值）
- [x] 聚合包上传：`edge/uploader.py`（独立线程，Queue，断网本地落文件）
- [x] 实时流发送：`edge/heartbeat.py`（`send_frame()`，threading.Lock，帧率节流）
- [x] 任务执行器：`edge/scanner.py`（`_drain_tasks`，band_scan / channel_scan / if_analysis）

### Phase 2 — 云端数据接收与存储 ✅
- [x] FastAPI 应用骨架：`cloud/main.py`（路由挂载、CORS、lifespan、**任务过期后台循环**）
- [x] 聚合包接收 API：`cloud/routers/ingest.py`（`POST /api/v1/spectrum/bundle`）
- [x] 数据查询 API：`cloud/routers/query.py`（历史帧列表 + 频点时间轴 + **快照API**）
- [x] 频段规则 API：`cloud/routers/band_rules.py`（增删改查）
- [x] 站点注册与心跳 API：`cloud/routers/stations.py`（注册 + WS 端点）
- [x] DB CRUD 函数：`cloud/db.py`（连接池 + 全部 CRUD + **信号分析表 + 信号库表**）
- [x] **任务过期**：`db.expire_stale_tasks()`，每 5 分钟扫描 pending/dispatched 超时 30 分钟的任务

### Phase 3 — 前端基础 ✅
- [x] 站点总览仪表盘（`StationsView.vue`）
- [x] 历史频谱查看页（`SpectrumView.vue`）
- [x] 频段规则管理页（`BandRulesView.vue`）
- [x] 频点历史查询（`FreqQueryView.vue`）
- [x] Nginx 反向代理 + Docker 多阶段构建

### Phase 4 — 频率指配工具 ✅
- [x] `POST /api/v1/freq-assign` + `FreqAssignView.vue`

### Phase 5 — 任务下发 + 实时流 ✅
- [x] `cloud/connection_manager.py` + `cloud/routers/tasks.py`
- [x] `cloud/stream_manager.py` + `cloud/routers/stream.py`
- [x] `RealtimeView.vue`（实时频谱 + 瀑布图）
- [x] **任务过期**：stuck 任务自动过期，`updated_at` + `status=expired`

### Phase 7 — 历史回放 ✅（新完成）
- [x] `GET /api/v1/spectrum/snapshots` — 查询时间段内帧元数据列表（不含数据blob）
- [x] `GET /api/v1/spectrum/snapshots/{frame_id}` — 获取单帧完整数据
- [x] `PlaybackView.vue` — 站点/时间选择、帧列表、ECharts 频谱图
- [x] 逐帧播放控制（上/下一帧、自动播放、速度选择）
- [x] **对比模式**：选 A/B 两帧叠加显示，不同颜色区分

### Phase 6 — AI 信号分析 ✅（新完成）
- [x] 本地信号检测：`analysis.py::_detect_signals()` — 连续超阈值段提取，3dB带宽估算，band_rules 归属查找
- [x] AI 后端：Claude API（`claude-sonnet-4-6`）+ OpenAI API（`gpt-4o-mini`）+ 本地文本描述
- [x] `POST /api/v1/analysis` — 支持单帧或时间范围，聚合多帧取最大值后分析
- [x] `GET /api/v1/analysis` + `GET /api/v1/analysis/{id}` + `PATCH /api/v1/analysis/{id}`
- [x] DB：`signal_analyses` 表（分析结果持久化，status 工作流：new/confirmed/dismissed）
- [x] `AnalysisView.vue` — 新建分析表单、分析列表、信号详情表、AI 报告展示

### Phase 8 — 台站信号库 ✅（新完成）
- [x] DB：`signal_records` 表（按频率索引，支持 active/archived 状态）
- [x] `GET/POST/PUT/PATCH/DELETE /api/v1/signals` — 完整 CRUD
- [x] `SignalLibraryView.vue` — 搜索/过滤、分页表格、创建/编辑弹窗、归档/删除操作

---

## 待完成（联调阶段）

### 设备联调（接入真实硬件后修bug）
- [ ] EM550 实机验证（SCPI 参数、电平单位转换确认）
- [ ] RSA306B 实机验证（tekrsa-api-wrap API 细节可能需微调）
- [ ] 联调完整数据链路：Edge → Cloud → 前端

### 工程化（可按需推进）
- [ ] 多 Worker 支持：stream_manager 改用 Redis pub/sub（当前单进程内存共享）
- [ ] 数据保留策略：定时清理 >3 个月历史帧
- [ ] Edge 日志：结构化日志 + 按天滚动
- [ ] Prometheus 指标暴露（可选）

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-03-13 | v0.1 | 初始 PLAN.md，Phase 0–6 任务分解 |
| 2026-03-13 | v0.2 | 新增 REQUIREMENTS.md；补充设备抽象层等 |
| 2026-03-13 | v0.3 | 新增 PROGRESS.md；拆分 Phase 7/8 |
| 2026-03-13 | v0.4–0.5 | 确认设备/AI策略/前端框架/band_rules |
| 2026-03-13 | v0.6–0.7 | Phase 1 核心代码 + Phase 2 API骨架 + Phase 0 WS心跳 |
| 2026-03-13 | v0.8 | Phase 3 前端基础 |
| 2026-03-14 | v0.9 | Phase 4 freq-assign + Phase 5 任务链路 |
| 2026-03-16 | v1.0 | Phase 5 实时流完成；docs/ARCHITECTURE.md |
| 2026-03-16 | v1.1 | **Phase 6/7/8 全部实现**：历史回放、AI信号分析、信号库；RSA306B驱动完整实现；任务过期逻辑 |
| 2026-03-16 | v1.2 | 架构修正：确认Edge只做时间压缩，移除边缘侧频率合并（preprocessor.py）；文档更新（PLAN/ARCHITECTURE/REQUIREMENTS/PROGRESS）；实时流默认帧率改为10fps；音频×频谱时间对齐要求写入需求文档 |
