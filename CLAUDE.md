# CLAUDE.md — RF·MESH AI Assistant Guide

> **What this file is:** Concise reference for AI assistants working in this codebase.
> It covers architecture, conventions, commands, and key constraints.

---

## Project Overview

**RF·MESH** is a multi-station wireless radio spectrum monitoring platform consisting of three layers:

- **Edge** — Python node that captures RF spectrum from physical hardware and streams data to cloud
- **Cloud** — FastAPI backend that ingests, stores, and queries spectrum data; dispatches tasks to edge nodes
- **Frontend** — Vue 3 SPA that displays real-time and historical spectrum data, manages tasks, and triggers AI analysis

**Implementation status:** Phases 0–8 complete (~8,600 LOC across 49 source files); Phases 9–11 pending (audio demod, hardening, deployment docs).

---

## Repository Structure

```
radio-mesh/
├── edge/                   # Python 3.11 edge node
│   ├── drivers/            # Hardware abstraction (em550, rsa306b, mock)
│   ├── aggregator.py       # 60-second max-hold aggregation
│   ├── heartbeat.py        # WebSocket registration & keep-alive with cloud
│   ├── scanner.py          # Main scan loop & task execution
│   ├── uploader.py         # Background HTTP upload thread with retry/cache
│   ├── models.py           # SpectrumBundle dataclass
│   ├── main.py             # Entry point
│   └── config.yaml.template
├── cloud/                  # FastAPI + TimescaleDB backend
│   ├── routers/            # 10 API routers (ingest, query, tasks, stream, analysis, ...)
│   ├── db.py               # All DB interaction (TimescaleDB, 33 KB)
│   ├── models.py           # Pydantic request/response schemas
│   ├── connection_manager.py  # Edge WebSocket registry (1 socket per station)
│   ├── stream_manager.py   # Frontend WebSocket registry (1:N broadcast)
│   └── main.py             # FastAPI app, middleware, lifespan hooks
├── frontend/               # Vue 3 + Vite SPA
│   └── src/
│       ├── api/index.js    # Axios REST client
│       ├── router/index.js # Vue Router configuration
│       ├── views/          # 11 page components
│       └── App.vue         # Layout & navigation
├── docs/
│   ├── ARCHITECTURE.md     # Detailed architecture (canonical reference)
│   ├── REQUIREMENTS.md     # Design specs & rationale
│   └── band_rules.yaml     # 50 frequency band definitions
├── config.yaml             # Root config (edge settings when running locally)
├── docker-compose.yml      # 3 services: timescaledb, cloud, frontend
├── PROGRESS.md             # Phase-by-phase completion checklist
└── NEXT.md                 # Phase 9–11 roadmap
```

---

## Development Commands

### Edge Node

```bash
# Copy and edit config first
cp edge/config.yaml.template config.yaml

# Run with mock device (no hardware needed)
python -m edge.main --config config.yaml --log-level DEBUG

# Run with real hardware
python -m edge.main --config config.yaml
```

### Cloud Backend

```bash
# Install deps
pip install -r cloud/requirements.txt

# Run locally (requires TimescaleDB on port 5432)
uvicorn cloud.main:app --host 0.0.0.0 --port 8000 --reload

# API docs available at http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # Dev server with hot reload (http://localhost:5173)
npm run build     # Production build
npm run preview   # Preview production build
```

### Full Stack via Docker

```bash
docker compose up -d --build      # Start all services
docker compose logs -f cloud      # Follow cloud logs
docker compose down               # Stop and remove containers
```

Services:
- Frontend: http://localhost:3000
- Cloud API: http://localhost:8000
- TimescaleDB: localhost:5432

---

## Technology Stack

| Layer | Stack |
|-------|-------|
| Edge | Python 3.11, threading, numpy, websocket-client, pyyaml |
| Hardware drivers | SCPI over TCP (EM550), USB tekrsa-api (RSA306B), mock |
| Cloud | FastAPI, Pydantic, psycopg2, TimescaleDB (PostgreSQL extension) |
| Frontend | Vue 3, Vite, Element Plus, ECharts 5, Axios, pako |
| Deployment | Docker, Docker Compose, Nginx (reverse proxy) |
| Data encoding | `base64(gzip(float32[]))` for spectrum levels |
| Protocols | WebSocket (edge↔cloud, cloud↔frontend), REST (edge→cloud uploads, frontend↔cloud), SCPI/TCP |

---

## Architecture Constraints (Critical)

These are core design decisions — do not violate them:

1. **Edge never merges frequency bins.** Aggregation is time-domain only (60-second max-hold windows). Frequency resolution is always preserved as captured.

2. **All business logic lives in Cloud.** Channel math, anomaly detection, signal analysis — never in edge or frontend.

3. **WebSocket direction: Edge → Cloud only.** The cloud never initiates connections to edge nodes (NAT-friendly design). Task dispatch is push from cloud to edge over the existing edge-initiated WebSocket.

4. **Spectrum data encoding:** Always `base64(gzip(float32[]))`. Use `pako` in frontend to decompress.

5. **dBµV → dBm conversion (EM550):** `dBm = dBµV − 107`. Applied in the driver, not upstream.

6. **RSA306B segment limit:** 40 MHz max per sweep. The driver auto-stitches segments for full-band coverage.

7. **Real-time stream rate:** Default 10 fps, configurable up to 30 fps.

8. **Authentication:** Bearer token checked in FastAPI middleware. Empty string = no auth (dev mode). Do not hardcode tokens.

---

## Data Flow Summary

```
Hardware → edge/drivers → scanner.py → aggregator.py → SpectrumBundle
                                                              ↓
                                                        uploader.py
                                                              ↓
                                            POST /api/v1/spectrum/bundle
                                                              ↓
                                                    cloud/routers/ingest.py
                                                              ↓
                                                    cloud/db.py (TimescaleDB)

Edge heartbeat.py ←→ WS /api/v1/stations/{id}/ws ←→ cloud/routers/stations.py
                                                              ↓
                                                  stream_manager broadcasts
                                                              ↓
                                        Frontend WS /api/v1/stream/{id}/ws
```

---

## Key Files for Common Tasks

| Task | Files to read |
|------|--------------|
| Add a new API endpoint | `cloud/routers/` (find nearest example), `cloud/models.py`, `cloud/db.py`, `cloud/main.py` (register router) |
| Add a new edge driver | `edge/drivers/base.py` (interface), `edge/drivers/mock.py` (simplest example) |
| Add a frontend page | `frontend/src/views/` (pick nearest example), `frontend/src/router/index.js`, `frontend/src/App.vue` (nav) |
| Modify DB schema | `cloud/db.py` — contains all `CREATE TABLE` statements and query functions |
| Understand data formats | `edge/models.py`, `cloud/models.py`, `docs/ARCHITECTURE.md` |
| Understand requirements | `docs/REQUIREMENTS.md`, `NEXT.md` |

---

## Configuration Reference

### Edge (`config.yaml`)

```yaml
station:
  id: station-001        # Unique station identifier
  name: "Station Name"

device:
  type: mock             # mock | em550 | rsa306b
  host: 192.168.1.100    # For em550 (SCPI TCP)
  port: 5025
  step_hz: 25000         # Frequency resolution

scan:
  start_hz: 20000000     # 20 MHz
  stop_hz: 3600000000    # 3.6 GHz

aggregation:
  interval_s: 60         # Aggregation window (seconds)

cloud:
  enabled: true
  url: http://localhost:8000
  upload_path: /api/v1/spectrum/bundle
  token: ""              # Bearer token (empty = no auth)

debug:
  dump_raw_frames: false
  output_dir: ./output
```

### Cloud (environment variables)

```
DATABASE_URL=postgresql://rfmesh:rfmesh@timescaledb:5432/rfmesh
API_TOKEN=                  # Empty string = no auth
LOG_LEVEL=INFO
```

---

## Database Schema (Key Tables)

| Table | Description |
|-------|-------------|
| `spectrum_frames` | TimescaleDB hypertable; partitioned by `period_start`; indexed on `(station_id, period_start DESC)` |
| `stations` | Station registry; online/offline status |
| `tasks` | Task dispatch records with expiry |
| `task_stations` | Per-station task status and results |
| `band_rules` | Frequency band definitions |
| `signal_analyses` | Detection results + AI summaries |
| `signal_records` | Known signal library |

All DB operations are in `cloud/db.py`. Use async-compatible psycopg2 connection pool (initialized in `cloud/main.py` lifespan).

---

## Code Conventions

### Python (Edge & Cloud)

- Style: PEP 8, 4-space indent
- Type hints used throughout; Pydantic models for API I/O
- Logging via `logging.getLogger(__name__)` — never `print()`
- Exceptions: catch specifically, log with context, re-raise or return error response
- Threading: Edge uses stdlib `threading.Thread`; Cloud uses FastAPI background tasks + asyncio

### JavaScript / Vue (Frontend)

- Vue 3 Composition API (`<script setup>`)
- Element Plus for UI components
- ECharts for spectrum/waterfall charts
- Axios via `src/api/index.js` — add new endpoints there
- No TypeScript (plain JS)

### API Design

- REST endpoints: `/api/v1/{resource}` pattern
- WebSocket endpoints: `/api/v1/{resource}/{id}/ws`
- Request/response schemas defined in `cloud/models.py`
- Errors: standard FastAPI `HTTPException` with appropriate status codes

---

## Testing

No automated test suite exists. Testing approach:

- **Mock driver** (`edge/drivers/mock.py`): Simulates realistic spectrum with configurable noise floor and preset signals. Use `device.type: mock` in config.
- **Full-stack smoke test**: `docker compose up` then open http://localhost:3000 and verify station appears, spectrum data flows, tasks dispatch.
- **API testing**: Swagger UI at http://localhost:8000/docs supports interactive testing.

When adding features, test manually with mock device before hardware integration.

---

## Product Vision (from Demo Prototypes)

Two prototype demos (`docs/rf-cloud-demo/`, `docs/天璇/`) define the aspirational feature set. Use them as the north star when planning new features.

### RF·CLOUD Demo — High-level Concepts
- **Multi-station dashboard:** 10-station grid with animated task status and daily AI summary briefings
- **Spectrum + direction finding:** Full waterfall (20 MHz–8 GHz), clickable signal shortcuts, Leaflet map with bearing lines and CEP confidence circles
- **Signal alert workflow:** Unknown signal → detected → classified → AI verdict (modulation, confidence %, natural-language determination)
- **AI modulation recognition pipeline:** IQ data → STFT feature extraction → CNN classifier (87 modulations) → frame sync analysis → protocol matching → comprehensive verdict
- **NLP task intake:** Paste or upload a complaint document → AI extracts frequency/time/location → structured task → station dispatch → parallel collection → report generation
- **Audio content analysis:** Broadcast signal demodulated to audio → speech-to-text → content moderation verdict

### 天璇 Demo — Technical Tooling Concepts
- **Frequency pair planner (Feature 1):** Duplex uplink/downlink pair selection with real-time + Max Hold overlay on both bands; interactive right-click marks; auto availability check (Max Hold < −75 dBm = green)
- **Bulk site collection (Feature 2):** Simultaneously trigger all stations on a given center/span/demod_bw/duration; collect Max Hold; rank sites by peak level; click to expand per-site spectrum
- **Background scan + query (Feature 3):** 1-minute granularity continuous scan in background; query by frequency + time range; per-site time-series charts with live append; quick shortcuts for common frequencies (GPS L1, FM, walkie, 5G)

### Data Simulation Model (天璇 `data.js`)
The demo simulates these signal types — use as test scenarios for mock driver validation:
- FM broadcast (88.7–107.4 MHz, 11 stations, site-dependent attenuation)
- VHF/UHF walkie-talkie (always-on 95% duty vs intermittent 20–40%, PTT state machine)
- Aviation VHF (118–137 MHz, 15% activity)
- GSM/4G/5G carrier subbands with 3-operator split
- GNSS interference events (GPS L1 1575.42 MHz, BeiDou B1 1561.098 MHz, sporadic 2–5 min)

### Features Not Yet Implemented (Future Phases)
- Direction finding (DF) with bearing lines and location estimation map
- Spatial spectrum processing (simultaneous multi-emitter detection on same frequency)
- AI modulation classification (CNN-based)
- NLP task intake from documents
- Automatic report generation
- Audio content extraction and moderation
- Natural language daily situation briefings

---

## Phase 9–11 Roadmap (Pending)

| Phase | Feature | Key work |
|-------|---------|---------|
| 9 | Audio Demodulation | EM550 Annex E UDP audio stream; software demod fallback for RSA306B; timestamp alignment with spectrum |
| 10 | Engineering Hardening | Structured JSON logging; Redis pub/sub for multi-worker cloud; data retention policy; auth polish |
| 11 | Deployment Docs | Systemd service templates; SSL/TLS; multi-site deployment guide |

See `NEXT.md` for detailed task breakdown.

---

## Hardware Integration Checklist

Before deploying with real hardware, validate:

- [ ] EM550 PSCan full-spectrum (143,200 points at 25 kHz step, 20 MHz–3.6 GHz)
- [ ] EM550 IFPAN narrowband (requires EM550SU option)
- [ ] EM550 Annex E UDP audio stream (Phase 9)
- [ ] RSA306B 40 MHz segment stitching (verify no gaps)
- [ ] End-to-end pipeline under real RF conditions

---

*Last updated: 2026-03-16. For detailed architecture, see `docs/ARCHITECTURE.md`.*
