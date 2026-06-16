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
    echo "[1/4] 虚拟环境异常，重建..."
    rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
else
    echo "[1/4] 虚拟环境已存在，跳过"
fi

# 安装 Python 依赖
echo "[2/4] 安装 Python 依赖..."
"$VENV_DIR/bin/pip" install -q --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
"$VENV_DIR/bin/pip" install -q -r "$APP_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# 安装 Playwright 浏览器
echo "[3/4] 安装 Playwright 浏览器 (Chromium)..."
if "$VENV_DIR/bin/python" -c "import playwright" 2>/dev/null; then
    "$VENV_DIR/bin/playwright" install chromium
else
    echo "   Playwright Python 包未安装，跳过浏览器安装"
fi

# 停止旧进程
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "停止旧进程..."
    kill $(lsof -ti:$PORT) 2>/dev/null || true
    sleep 1
fi

# 启动服务
echo "[4/4] 启动服务 (端口 $PORT)..."
cd "$APP_DIR"
nohup "$VENV_DIR/bin/uvicorn" app.main:app --host 0.0.0.0 --port $PORT > "$APP_DIR/nas-monitor.log" 2>&1 &

echo ""
echo "✅ NAS Monitor 已启动"
echo "   访问: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):$PORT"
echo "   日志: $APP_DIR/nas-monitor.log"
echo "   停止: kill \$(lsof -ti:$PORT)"
