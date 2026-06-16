#!/bin/bash
# NAS Monitor - 快速重启（不重装依赖）
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/venv"
PORT=8900

echo "=== NAS Monitor 重启 ==="

# 停止旧进程
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "停止旧进程..."
    kill $(lsof -ti:$PORT) 2>/dev/null || true
    sleep 1
fi

# 启动
echo "启动服务 (端口 $PORT)..."
cd "$APP_DIR"
nohup "$VENV_DIR/bin/uvicorn" app.main:app --host 0.0.0.0 --port $PORT > "$APP_DIR/nas-monitor.log" 2>&1 &

sleep 2

if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "OK: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):$PORT"
else
    echo "FAIL: 查看 $APP_DIR/nas-monitor.log"
    tail -5 "$APP_DIR/nas-monitor.log"
    exit 1
fi
