# RF·MESH 部署手册

> 文档版本：v1.0 | 更新日期：2026-03-16

---

## 前置要求

| 组件 | 最低版本 | 说明 |
|------|----------|------|
| Docker | 20.10+ | 云端部署必须 |
| Docker Compose | v2.x (`docker compose`) | 注意是 v2，不是旧版 `docker-compose` |
| Python | 3.11+ | 边缘节点必须（仅边缘端） |
| 操作系统 | Linux (x86_64 / arm64) | 推荐 Ubuntu 22.04 LTS |
| 网络 | 边缘节点可达云端 8000 端口 | 支持 NAT（Edge 主动连接 Cloud） |

---

## 1. 云端部署（Docker Compose 一键启动）

### 1.1 获取代码

```bash
git clone <repo-url> radio-mesh
cd radio-mesh
```

### 1.2 配置环境变量

直接在 `docker-compose.yml` 中修改，或创建 `.env` 文件：

```bash
# .env（放在项目根目录，docker compose 自动读取）
API_TOKEN=your-secret-token-here    # 留空则无鉴权（仅开发用）
DATA_RETENTION_DAYS=90              # 历史频谱保留天数（0=不自动清理）
LOG_LEVEL=INFO                      # DEBUG / INFO / WARNING
LOG_DIR=/app/logs                   # 日志目录（容器内路径）
```

### 1.3 启动服务

```bash
docker compose up -d --build
```

三个服务说明：

| 服务 | 端口 | 说明 |
|------|------|------|
| `timescaledb` | 5432 | PostgreSQL + TimescaleDB 时序数据库 |
| `cloud` | 8000 | FastAPI 后端，含 REST + WebSocket |
| `frontend` | 3000 | Vue SPA，通过 Nginx 服务并反向代理 API |

### 1.4 验证部署

```bash
# 健康检查
curl http://localhost:8000/health
# 预期：{"status":"ok"}

# 查看站点列表（应返回空数组）
curl http://localhost:8000/api/v1/stations

# 前端
open http://localhost:3000
```

### 1.5 查看日志

```bash
docker compose logs -f cloud       # 云端日志
docker compose logs -f timescaledb # 数据库日志
docker compose ps                  # 查看服务状态
```

### 1.6 停止 / 清理

```bash
docker compose down                         # 停止并删除容器（保留数据卷）
docker compose down -v                      # 同上，同时删除数据卷（！会清空数据库）
```

---

## 2. Nginx SSL 终止配置

生产环境建议在 Docker 之外部署 Nginx 作为 HTTPS 入口，将请求反向代理到 localhost:3000（前端）和 localhost:8000（API）。

### 2.1 Let's Encrypt 自动证书（推荐）

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d yourdomain.example.com
```

### 2.2 Nginx 配置示例

```nginx
# /etc/nginx/sites-available/rfmesh
server {
    listen 80;
    server_name yourdomain.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.example.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # 前端静态资源
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API（REST + WebSocket）
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # 长连接超时（WebSocket 心跳默认 30 s，此处设长一些）
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/rfmesh /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 2.3 自签证书（无域名时）

```bash
mkdir -p /etc/rfmesh/certs
openssl req -x509 -newkey rsa:4096 -keyout /etc/rfmesh/certs/key.pem \
    -out /etc/rfmesh/certs/cert.pem -days 365 -nodes \
    -subj "/CN=rfmesh-cloud"
```

然后在 Nginx 配置中替换证书路径。

---

## 3. 边缘节点部署

### 3.1 安装 Python 依赖

```bash
cd radio-mesh
pip install -r requirements.txt
# 如果使用 RSA306B，还需要安装 tekrsa-api-wrap：
# pip install tekrsa-api-wrap
```

### 3.2 配置文件

```bash
cp edge/config.yaml.template config.yaml
nano config.yaml  # 按需修改
```

关键字段说明：

```yaml
station:
  id: station-001        # 必须全局唯一，用于识别该站点
  name: "南京监测站 01"  # 显示名称

device:
  type: mock             # mock（测试）| em550 | rsa306b
  host: 192.168.1.100    # EM550 IP（仅 em550 有效）
  port: 5025             # EM550 SCPI TCP 端口（默认 5025）

scan:
  start_hz: 20000000     # 起始频率 20 MHz
  stop_hz: 3600000000    # 终止频率 3.6 GHz

aggregation:
  interval_s: 60         # 聚合窗口（秒），生产环境一般用 60

cloud:
  enabled: true
  url: https://yourdomain.example.com  # 云端 API 地址
  upload_path: /api/v1/spectrum/bundle
  token: your-secret-token-here        # 与云端 API_TOKEN 一致

audio:                   # Phase 9：音频解调（目前为预留字段）
  enabled: false
  mode: hardware         # hardware（EM550 Annex E）| software（软件解调）
  udp_port: 5556
  sample_rate: 16000
```

### 3.3 手动运行（测试用）

```bash
python -m edge.main --config config.yaml --log-level DEBUG
```

### 3.4 systemd 服务（生产环境）

创建服务文件：

```ini
# /etc/systemd/system/rfmesh-edge.service
[Unit]
Description=RF·MESH Edge Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rfmesh                          # 建议创建专用非特权用户
WorkingDirectory=/opt/rfmesh
ExecStart=/opt/rfmesh/venv/bin/python -m edge.main --config /opt/rfmesh/config.yaml
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rfmesh-edge

# 资源限制（可选）
MemoryMax=512M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
# 创建专用用户
useradd -r -s /bin/false -d /opt/rfmesh rfmesh

# 部署代码
mkdir -p /opt/rfmesh
cp -r . /opt/rfmesh/
chown -R rfmesh:rfmesh /opt/rfmesh

# Python venv
python3.11 -m venv /opt/rfmesh/venv
/opt/rfmesh/venv/bin/pip install -r /opt/rfmesh/requirements.txt

# 启用服务
systemctl daemon-reload
systemctl enable rfmesh-edge
systemctl start rfmesh-edge

# 查看状态 / 日志
systemctl status rfmesh-edge
journalctl -u rfmesh-edge -f
```

---

## 4. 设备连接

### 4.1 EM550（SCPI over TCP）

1. 确认 EM550 IP 地址（设备面板或 DHCP 日志查询）
2. 在 config.yaml 中设置 `device.type: em550`、`device.host`、`device.port: 5025`
3. 防火墙允许边缘节点访问 EM550 的 TCP 5025 端口
4. 验证连接：
   ```bash
   nc -zv 192.168.1.100 5025
   # 连通则显示 "Connection succeeded"
   ```

### 4.2 RSA306B（USB）

1. 安装 Tektronix RSA API 库：
   ```bash
   # 下载 libRSA_API.so 并放入 /usr/local/lib/
   # 或设置 LD_LIBRARY_PATH
   pip install tekrsa-api-wrap
   ```
2. 设置 udev 规则（允许非 root 访问 USB 设备）：
   ```bash
   # /etc/udev/rules.d/99-rsa306b.rules
   SUBSYSTEM=="usb", ATTRS{idVendor}=="0699", ATTRS{idProduct}=="0411", MODE="0666"
   ```
   ```bash
   udevadm control --reload-rules && udevadm trigger
   ```
3. 在 config.yaml 中设置 `device.type: rsa306b`
4. 插入 USB 后运行边缘节点

---

## 5. 多站点注意事项

- **`station_id` 必须唯一**：每个边缘节点使用不同的 `station_id`（如 `station-nj-01`、`station-sh-01`）
- **时钟同步**：建议所有节点（边缘 + 云端）使用 NTP/PTP，保证时间戳一致性（音频-频谱对齐依赖此项）
- **网络连通性**：边缘节点只需能主动连接云端（TCP 8000），不需要云端能连接边缘，天然支持 NAT
- **带宽估算**：
  - 后台扫描（1分钟聚合）：约 50 KB/分钟/站（20 MHz–3.6 GHz，25 kHz 步进，gzip 压缩后）
  - 实时流（10 fps）：约 5 MB/分钟/站（取决于频谱点数和压缩率）
- **VPN/隧道**：若云端部署在公网，建议边缘到云端走 VPN（WireGuard 或 OpenVPN），不强制

---

## 6. 故障排查

### 站点一直离线

1. 检查 config.yaml 中 `cloud.enabled: true` 和 `cloud.url` 是否正确
2. 检查 API_TOKEN 是否匹配
3. 查看边缘节点日志：`journalctl -u rfmesh-edge -f` 或 `--log-level DEBUG`
4. 确认云端 8000 端口可访问：`curl http://<cloud-ip>:8000/health`

### 频谱数据不显示

1. 确认站点已在线（StationsView 页面显示绿点）
2. 检查 Cloud 日志：`docker compose logs -f cloud`
3. 检查 TimescaleDB 是否健康：`docker compose ps`
4. 验证 ingest API：
   ```bash
   curl http://localhost:8000/api/v1/spectrum/frames \
     -G --data-urlencode "station_id=<id>" \
        --data-urlencode "start_ms=0" \
        --data-urlencode "end_ms=$(date +%s)000"
   ```

### WebSocket 连接被断开

- Nginx 反向代理需设置 `proxy_read_timeout 3600s`（默认 60 s 会断开长连接）
- 检查 Nginx 错误日志：`/var/log/nginx/error.log`

### 数据库连接失败

```bash
docker compose logs timescaledb   # 查看是否就绪
docker compose restart timescaledb cloud  # 重启顺序有依赖
```

### API 鉴权失败（401）

- 确认边缘节点 `config.yaml` 的 `cloud.token` 与云端 `API_TOKEN` 完全一致（注意空格、换行）
- 开发模式：将 `API_TOKEN` 设为空字符串（`API_TOKEN=`），跳过鉴权

---

## 7. 升级 / 维护

### 升级云端

```bash
cd radio-mesh
git pull
docker compose up -d --build   # 重新构建并热替换容器
```

### 备份数据库

```bash
# 导出
docker compose exec timescaledb pg_dump -U rfmesh rfmesh | gzip > rfmesh_$(date +%Y%m%d).sql.gz

# 恢复
gunzip -c rfmesh_20260316.sql.gz | docker compose exec -T timescaledb psql -U rfmesh rfmesh
```

### 手动触发数据清理

```bash
# 清理 90 天前的频谱帧（正常情况由后台循环自动执行）
docker compose exec timescaledb psql -U rfmesh -c \
  "DELETE FROM spectrum_frames WHERE period_start < now() - interval '90 days';"
```
