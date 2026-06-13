#!/bin/bash
# NAS Monitor - 一键安装启动脚本

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/venv"
PORT=8900

echo "=== NAS Monitor 安装启动 ==="
echo "目录: $APP_DIR"

# 创建虚拟环境
if [ -d "$VENV_DIR" ] && [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "[1/3] 虚拟环境异常，重建..."
    rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "[1/3] 创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
else
    echo "[1/3] 虚拟环境已存在，跳过"
fi

# 安装依赖
echo "[2/3] 安装依赖..."
"$VENV_DIR/bin/pip" install -q --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
"$VENV_DIR/bin/pip" install -q -r "$APP_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# 停止旧进程
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "停止旧进程..."
    kill $(lsof -ti:$PORT) 2>/dev/null || true
    sleep 1
fi

# 启动服务
echo "[3/3] 启动服务 (端口 $PORT)..."
cd "$APP_DIR"
nohup "$VENV_DIR/bin/uvicorn" app.main:app --host 0.0.0.0 --port $PORT > "$APP_DIR/nas-monitor.log" 2>&1 &

echo ""
echo "✅ NAS Monitor 已启动"
echo "   访问: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):$PORT"
echo "   日志: $APP_DIR/nas-monitor.log"
echo "   停止: kill \$(lsof -ti:$PORT)"
