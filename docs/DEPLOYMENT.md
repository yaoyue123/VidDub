# 生产部署指南

> 本工具设计为个人本地使用，但可以部署到服务器 7×24 运行（自动扫描频道 + 自动发布）。
> 本文给出 Linux 服务器和 Windows 两种生产部署方案。

---

## 推荐拓扑

```
                +-----------------+
                |   用户浏览器     |
                +--------+--------+
                         |
                  https://your-domain/
                         |
                +--------+--------+
                |     nginx       |  (反代 + TLS + 静态)
                |   反向代理      |
                +----+-------+----+
                     |       |
            +--------+   +---+-----------+
            |            |               |
     static /        /api/*           /ws
     (Vue dist)      ↓                ↓
              +-----+----+      +-----+-----+
              | uvicorn  |      | uvicorn   |
              | :8000    +------+ WebSocket |
              | (FastAPI)|      | (同进程)  |
              +----------+      +-----------+
                     |
              +------+--------+
              | SQLite +       |
              | downloads/    |
              | data/         |
              +---------------+
```

**关键决策**：
- 后端 FastAPI 监听 127.0.0.1:8000，由 nginx 反代
- 前端 `npm run build` 产物 `frontend/dist/` 由 nginx 直接 serve
- 静态成品 `backend/downloads/` 也由 nginx 直接 serve（路径 `/static/downloads/`）
- WebSocket 走 nginx 的 `/ws` 路径，需配置 Upgrade 头
- Playwright headed → 服务器需 xvfb-run（Linux）

---

## 方案 A：Linux 服务器（systemd + nginx）

### A.1 服务器准备

```bash
# Ubuntu 22.04 LTS 推荐
sudo apt update
sudo apt install -y python3.11 python3.11-venv nodejs npm ffmpeg git \
                    nginx sqlite3 xvfb
# Playwright 系统依赖
sudo apt install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
                    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
                    libgbm1 libpango-1.0-0 libcairo2 libasound2

# Node 18+（如默认版本低）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### A.2 部署代码

```bash
sudo mkdir -p /opt/viddub
sudo chown $USER:$USER /opt/viddub
cd /opt/viddub
git clone <your-repo-url> .

# 一键 setup
chmod +x setup.sh start.sh
./setup.sh
```

### A.3 配置 `.env`

```bash
vim backend/.env
# 填入 SILICONFLOW_API_KEY=sk_xxx
# 设置 DATABASE_URL=sqlite+aiosqlite:////opt/viddub/backend/data/viddub.db
```

### A.4 构建前端

```bash
cd frontend
npm run build
# 产物在 frontend/dist/
```

### A.5 nginx 配置

`/etc/nginx/sites-available/viddub`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 重定向到 https（推荐配 certbot）
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # 前端静态
    root /opt/viddub/frontend/dist;
    index index.html;

    # Vue Router history mode
    location / {
        try_files $uri $uri/ /index.html;
    }

    # FastAPI 反代
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;    # 长任务（下载/上传视频）
        proxy_send_timeout 600s;
        client_max_body_size 2G;     # 上传参考音频 / 大文件
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;   # 长连接
    }

    # Swagger 文档（可选 — 生产建议关掉或加 auth）
    location /docs { proxy_pass http://127.0.0.1:8000; }
    location /redoc { proxy_pass http://127.0.0.1:8000; }
    location /openapi.json { proxy_pass http://127.0.0.1:8000; }

    # 静态成品（视频/音频文件）
    location /static/downloads/ {
        alias /opt/viddub/backend/downloads/;
        # 限制访问（可选 basic auth）
        # auth_basic "restricted";
        # auth_basic_user_file /etc/nginx/.htpasswd;
    }
}
```

启用：
```bash
sudo ln -s /etc/nginx/sites-available/viddub /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# TLS（用 certbot）
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### A.6 systemd 服务

`/etc/systemd/system/viddub.service`：

```ini
[Unit]
Description=VidDub Backend (FastAPI + uvicorn)
After=network.target

[Service]
Type=simple
User=viddub
Group=viddub
WorkingDirectory=/opt/viddub/backend
EnvironmentFile=/opt/viddub/backend/.env

# xvfb-run 让 Playwright headed 在无显示器环境下工作
ExecStart=/usr/bin/xvfb-run -a --server-args="-screen 0 1920x1080x24" \
    /opt/viddub/backend/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 \
    --workers 1 \
    --no-access-log

Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/viddub/uvicorn.log
StandardError=append:/var/log/viddub/uvicorn.err.log

# 安全限制
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/opt/viddub/backend/data /opt/viddub/backend/downloads

[Install]
WantedBy=multi-user.target
```

启用：
```bash
sudo mkdir -p /var/log/viddub
sudo chown viddub:viddub /var/log/viddub

sudo systemctl daemon-reload
sudo systemctl enable viddub
sudo systemctl start viddub
sudo systemctl status viddub
```

---

## 方案 B：Windows Server / Windows 10+ 桌面（nssm）

### B.1 安装 nssm

下载 https://nssm.cc/download → 解压 → 把 `nssm.exe` 放到 `C:\Windows\System32\` 或自定义路径。

### B.2 安装服务

**管理员 PowerShell**：

```powershell
nssm install VidDubBackend "C:\viddub\backend\venv\Scripts\uvicorn.exe" `
    "app.main:app --host 127.0.0.1 --port 8000 --workers 1"

nssm set VidDubBackend AppDirectory "C:\viddub\backend"
nssm set VidDubBackend AppEnvironmentExtra "PYTHONUNBUFFERED=1"
nssm set VidDubBackend AppStdout "C:\viddub\logs\uvicorn.log"
nssm set VidDubBackend AppStderr "C:\viddub\logs\uvicorn.err.log"
nssm set VidDubBackend AppRotateFiles 1
nssm set VidDubBackend AppRotateBytes 10485760   # 10MB 滚动
nssm set VidDubBackend Start SERVICE_AUTO_START
nssm set VidDubBackend Description "VidDub FastAPI backend"
nssm set VidDubBackend DependOnService Tcpip

nssm start VidDubBackend
```

### B.3 IIS 反向代理（可选）

安装 IIS + URL Rewrite + Application Request Routing (ARR)。

`web.config`：
```xml
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="ProxyAPI" stopProcessing="true">
          <match url="^api/(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8000/api/{R:1}" />
        </rule>
        <rule name="ProxyWS" stopProcessing="true">
          <match url="^ws" />
          <action type="Rewrite" url="http://127.0.0.1:8000/ws" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

WebSocket 需在 IIS 管理器 → 站点 → Configuration Editor → 启用 WebSocket Protocol。

### B.4 开机自启

`nssm install` 时已设 `SERVICE_AUTO_START`，重启会自动启动。也可在 `services.msc` 看到 `VidDubBackend` 服务。

---

## 日志收集

### 后端日志

- **uvicorn access log**：stdout → systemd journal 或 nssm 指定文件
- **应用日志**：`backend/data/*.log`（如有 logger 配置）
- **任务日志**：`tasks.message` 字段 + WebSocket 事件

查看实时日志：
```bash
# Linux systemd
sudo journalctl -u viddub -f

# 或文件
tail -f /var/log/viddub/uvicorn.log
```

### 前端日志

浏览器 DevTools → Console（前端不写文件）。

### Playwright 截图

发布失败时自动保存：`backend/data/screenshots/*.png`，便于排查 DOM 选择器失效。

---

## 备份策略

### 必备份

| 路径 | 内容 | 频率 |
|------|------|------|
| `backend/data/viddub.db` | 数据库（视频/任务/配置/字幕元数据） | 每天 |
| `backend/data/login/*_storage_state.json` | 平台登录态 cookies | 每次登录后 |
| `backend/.env` | API key + 配置 | 修改后 |

### 可选备份

| 路径 | 内容 | 备注 |
|------|------|------|
| `backend/downloads/` | 视频成品 + SRT | 占用大，按需备份 |
| `frontend/dist/` | 前端构建产物 | 可重新 `npm run build` |

### 自动备份脚本

`/opt/viddub/scripts/backup.sh`：
```bash
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/var/backups/viddub/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# SQLite 在线备份（不锁库）
sqlite3 /opt/viddub/backend/data/viddub.db ".backup '$BACKUP_DIR/viddub.db'"

# 登录态
cp -r /opt/viddub/backend/data/login "$BACKUP_DIR/"

# .env
cp /opt/viddub/backend/.env "$BACKUP_DIR/"

# 压缩
tar czf "${BACKUP_DIR}.tar.gz" -C "$BACKUP_DIR" .
rm -rf "$BACKUP_DIR"

# 保留 30 天
find /var/backups/viddub/ -mtime +30 -delete
```

cron：
```bash
0 3 * * * /opt/viddub/scripts/backup.sh
```

---

## 升级流程

```bash
cd /opt/viddub
sudo systemctl stop viddub

# 拉新代码
git pull origin main

# 跑迁移
cd backend
venv/bin/python -m alembic upgrade head

# 重建前端
cd ../frontend
npm install
npm run build

# 启动
sudo systemctl start viddub
sudo systemctl status viddub
```

---

## 性能调优

### 高负载场景

1. **uvicorn workers**：当前配置 `--workers 1`（SQLite 限制）。如换 PostgreSQL 可改 2-4。
2. **Nginx gzip**：
   ```nginx
   gzip on;
   gzip_types application/json text/css application/javascript;
   gzip_min_length 1000;
   ```
3. **HTTP/2**：上述 nginx 配置已启用 `http2`
4. **静态文件缓存**：
   ```nginx
   location ~* \.(js|css|png|jpg|svg|woff2)$ {
       expires 7d;
       add_header Cache-Control "public, no-transform";
   }
   ```

### 大文件下载优化

```nginx
location /static/downloads/ {
    alias /opt/viddub/backend/downloads/;
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
}
```

---

## 安全建议

1. **限制 IP 白名单**：nginx 配置 `allow 1.2.3.4; deny all;`
2. **Basic Auth**：
   ```bash
   sudo htpasswd -c /etc/nginx/.htpasswd your_user
   ```
   nginx 配置 `auth_basic` + `auth_basic_user_file`
3. **不要把 `/docs` 暴露公网**：生产建议删除或加 auth
4. **HTTPS 强制**：certbot 自动续签
5. **文件权限**：
   ```bash
   sudo chown -R viddub:viddub /opt/viddub
   sudo chmod 600 /opt/viddub/backend/.env
   sudo chmod 600 /opt/viddub/backend/data/login/*.json
   ```
6. **防火墙**：仅开放 80/443，不要把 8000/5173 直接暴露公网

---

## 监控（可选）

简单方案：cron 调用 `/api/stats/dashboard` + 邮件/钉钉报警：

```bash
*/5 * * * * curl -fs http://127.0.0.1:8000/api/stats/dashboard \
    | jq '.failed_tasks | length' \
    | awk '{if($1>5) system("echo \"Too many failed tasks\" | mail -s \"VidDub Alert\" you@example.com")}'
```

进阶方案：Prometheus + Grafana + node_exporter（监控 CPU/磁盘/RAM），自定义 exporter 监控任务队列深度。

---

*本文档对应 Phase 10 (v2.0.10) · 最后更新：2026-06-22*
