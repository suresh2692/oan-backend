#!/bin/bash
set -euo pipefail

# ── Redirect all output to log ────────────────────────────────────────────────
exec > >(tee /var/log/user-data.log | logger -t user-data -s 2>/dev/console) 2>&1
echo "[$(date)] Starting Langfuse setup..."

# ── System update & dependencies ──────────────────────────────────────────────
dnf update -y
dnf install -y docker nginx jq awscli

# ── Docker ────────────────────────────────────────────────────────────────────
systemctl enable --now docker
usermod -aG docker ec2-user

# Docker Compose v2 plugin
COMPOSE_VERSION="v2.27.0"
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/$${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version

# ── Determine public IP ───────────────────────────────────────────────────────
EIP="${eip_public_ip}"
LANGFUSE_HOSTNAME="${langfuse_hostname}"
if [ -n "$LANGFUSE_HOSTNAME" ]; then
  NEXTAUTH_URL="http://$LANGFUSE_HOSTNAME"
else
  NEXTAUTH_URL="http://$EIP"
fi

echo "[$(date)] Using NEXTAUTH_URL: $NEXTAUTH_URL"

# ── Langfuse directory ────────────────────────────────────────────────────────
mkdir -p /opt/langfuse/{data/postgres,data/clickhouse,data/minio,data/redis}
chmod -R 755 /opt/langfuse

# ── docker-compose.yml ────────────────────────────────────────────────────────
cat > /opt/langfuse/docker-compose.yml << 'COMPOSE_EOF'
version: "3.9"

x-langfuse-env: &langfuse-env
  DATABASE_URL: postgresql://langfuse:${postgres_password}@postgres:5432/langfuse
  NEXTAUTH_URL: NEXTAUTH_URL_PLACEHOLDER
  NEXTAUTH_SECRET: ${nextauth_secret}
  SALT: ${salt}
  ENCRYPTION_KEY: ${nextauth_secret}
  # ClickHouse
  CLICKHOUSE_MIGRATION_URL: clickhouse://clickhouse:9000
  CLICKHOUSE_URL: http://clickhouse:8123
  CLICKHOUSE_USER: langfuse
  CLICKHOUSE_PASSWORD: ${clickhouse_password}
  # Redis
  REDIS_HOST: redis
  REDIS_PORT: "6379"
  # MinIO (S3-compatible blob storage)
  LANGFUSE_S3_MEDIA_UPLOAD_ENABLED: "true"
  LANGFUSE_S3_MEDIA_UPLOAD_BUCKET: langfuse-media
  LANGFUSE_S3_MEDIA_UPLOAD_REGION: us-east-1
  LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID: langfuse
  LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY: ${minio_secret}
  LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT: http://minio:9000
  LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE: "true"
  LANGFUSE_S3_EVENT_UPLOAD_ENABLED: "true"
  LANGFUSE_S3_EVENT_UPLOAD_BUCKET: langfuse-events
  LANGFUSE_S3_EVENT_UPLOAD_REGION: us-east-1
  LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: langfuse
  LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: ${minio_secret}
  LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT: http://minio:9000
  LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE: "true"
  # Seed initial org/project/user
  LANGFUSE_INIT_ORG_ID: "oan-org"
  LANGFUSE_INIT_ORG_NAME: "OAN"
  LANGFUSE_INIT_PROJECT_ID: "oan-project"
  LANGFUSE_INIT_PROJECT_NAME: "OAN Backend"
  LANGFUSE_INIT_PROJECT_PUBLIC_KEY: ${langfuse_public_key}
  LANGFUSE_INIT_PROJECT_SECRET_KEY: ${langfuse_secret_key}
  LANGFUSE_INIT_USER_EMAIL: ${langfuse_init_email}
  LANGFUSE_INIT_USER_NAME: "Admin"
  LANGFUSE_INIT_USER_PASSWORD: ${langfuse_init_password}
  TELEMETRY_ENABLED: "false"
  LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES: "true"

services:
  # ── Databases ───────────────────────────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: ${postgres_password}
      POSTGRES_DB: langfuse
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse"]
      interval: 10s
      timeout: 5s
      retries: 5

  clickhouse:
    image: clickhouse/clickhouse-server:24.12-alpine
    restart: unless-stopped
    environment:
      CLICKHOUSE_DB: langfuse
      CLICKHOUSE_USER: langfuse
      CLICKHOUSE_PASSWORD: ${clickhouse_password}
    volumes:
      - ./data/clickhouse:/var/lib/clickhouse
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8123/ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    ulimits:
      nofile:
        soft: 262144
        hard: 262144

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --save 60 1 --loglevel warning
    volumes:
      - ./data/redis:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: langfuse
      MINIO_ROOT_PASSWORD: ${minio_secret}
    volumes:
      - ./data/minio:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Create MinIO buckets on first start
  minio-setup:
    image: minio/mc:latest
    depends_on:
      minio:
        condition: service_healthy
    restart: on-failure
    entrypoint: >
      /bin/sh -c "
        mc alias set local http://minio:9000 langfuse ${minio_secret} &&
        mc mb --ignore-existing local/langfuse-media &&
        mc mb --ignore-existing local/langfuse-events &&
        echo 'MinIO buckets ready'
      "

  # ── Langfuse ─────────────────────────────────────────────────────────────────
  langfuse-web:
    image: langfuse/langfuse:${langfuse_version}
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      clickhouse:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio-setup:
        condition: service_completed_successfully
    environment:
      <<: *langfuse-env
    ports:
      - "3000:3000"
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3000/api/public/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s

  langfuse-worker:
    image: langfuse/langfuse-worker:${langfuse_version}
    restart: unless-stopped
    depends_on:
      langfuse-web:
        condition: service_healthy
    environment:
      <<: *langfuse-env
COMPOSE_EOF

# Inject the real NEXTAUTH_URL (can't use shell vars inside COMPOSE_EOF heredoc directly)
sed -i "s|NEXTAUTH_URL_PLACEHOLDER|$NEXTAUTH_URL|g" /opt/langfuse/docker-compose.yml

# ── Systemd service for Langfuse ─────────────────────────────────────────────
cat > /etc/systemd/system/langfuse.service << 'SERVICE_EOF'
[Unit]
Description=Langfuse Observability Stack
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/langfuse
ExecStart=/usr/local/lib/docker/cli-plugins/docker-compose up -d --remove-orphans
ExecStop=/usr/local/lib/docker/cli-plugins/docker-compose down
TimeoutStartSec=300
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
systemctl enable langfuse

# ── Nginx reverse proxy ───────────────────────────────────────────────────────
cat > /etc/nginx/conf.d/langfuse.conf << 'NGINX_EOF'
# Rate limiting zone
limit_req_zone $binary_remote_addr zone=langfuse_limit:10m rate=20r/s;

server {
    listen 80;
    server_name _;

    # Security headers
    add_header X-Frame-Options           "SAMEORIGIN"    always;
    add_header X-Content-Type-Options    "nosniff"       always;
    add_header X-XSS-Protection          "1; mode=block" always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy        "geolocation=(), microphone=(), camera=()" always;

    # Hide Nginx version
    server_tokens off;

    # Rate limiting
    limit_req zone=langfuse_limit burst=50 nodelay;

    # Health check endpoint (no auth required)
    location /api/public/health {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass         http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade            $http_upgrade;
        proxy_set_header   Connection         "upgrade";
        proxy_set_header   Host               $host;
        proxy_set_header   X-Real-IP          $remote_addr;
        proxy_set_header   X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto  $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        client_max_body_size 50m;
    }
}
NGINX_EOF

# Remove default nginx config
rm -f /etc/nginx/conf.d/default.conf /etc/nginx/sites-enabled/default 2>/dev/null || true

nginx -t
systemctl enable --now nginx

# ── CloudWatch Agent ──────────────────────────────────────────────────────────
dnf install -y amazon-cloudwatch-agent

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CW_EOF'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/user-data.log",
            "log_group_name": "/ec2/langfuse/user-data",
            "log_stream_name": "{instance_id}",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/nginx/access.log",
            "log_group_name": "/ec2/langfuse/nginx-access",
            "log_stream_name": "{instance_id}",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/nginx/error.log",
            "log_group_name": "/ec2/langfuse/nginx-error",
            "log_stream_name": "{instance_id}",
            "timezone": "UTC"
          }
        ]
      }
    }
  },
  "metrics": {
    "namespace": "Langfuse/EC2",
    "metrics_collected": {
      "cpu": { "measurement": ["cpu_usage_idle", "cpu_usage_user"], "metrics_collection_interval": 60 },
      "disk": { "measurement": ["used_percent"], "metrics_collection_interval": 60, "resources": ["/"] },
      "mem": { "measurement": ["mem_used_percent"], "metrics_collection_interval": 60 }
    }
  }
}
CW_EOF

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s

# ── Start Langfuse ────────────────────────────────────────────────────────────
echo "[$(date)] Starting Langfuse stack..."
systemctl start langfuse

echo "[$(date)] Setup complete. Langfuse will be available at: $NEXTAUTH_URL"
echo "[$(date)] Check status: docker compose -f /opt/langfuse/docker-compose.yml ps"
echo "[$(date)] View logs:    docker compose -f /opt/langfuse/docker-compose.yml logs -f"
