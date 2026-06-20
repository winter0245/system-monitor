#!/bin/bash
# NAS Monitor - 快速重启（不重装依赖）

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/venv"
PORT=8900

echo "=== NAS Monitor 重启 ==="

# ---------- 工具函数：查找占用端口的 PID ----------
port_pid() {
    # 1) fuser（群晖自带，但可能需要 root）
    if command -v fuser &>/dev/null; then
        local p
        p=$(fuser $PORT/tcp 2>/dev/null)
        if [ -n "$p" ]; then
            # fuser 输出形如 "8900/tcp: 12345"，取最后一个字段
            echo "$p" | awk '{print $NF}'
            return
        fi
    fi

    # 2) 用 ps 找 uvicorn 进程（不依赖端口检测权限）
    local p
    p=$(ps aux 2>/dev/null | grep "[u]vicorn.*app.main.*$PORT" | awk '{print $2}' | head -1)
    if [ -n "$p" ]; then
        echo "$p"
        return
    fi

    # 3) ss
    if command -v ss &>/dev/null; then
        ss -tlnp "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1
        return
    fi

    # 4) netstat
    if command -v netstat &>/dev/null; then
        netstat -tlnp 2>/dev/null | grep ":$PORT " | sed -n 's/.* \([0-9]*\)\/.*/\1/p' | head -1
        return
    fi
}

# ---------- 等待端口释放 ----------
wait_port_free() {
    local timeout=${1:-10}
    local waited=0
    while [ $waited -lt $timeout ]; do
        # 用 python 检测端口是否仍被占用（比系统工具更可靠）
        if "$VENV_DIR/bin/python" -c "
import socket
s = socket.socket()
try:
    s.bind(('0.0.0.0', $PORT))
    s.close()
    exit(0)
except OSError:
    exit(1)
" 2>/dev/null; then
            return 0
        fi
        sleep 0.5
        waited=$((waited + 1))
    done
    return 1
}

# ---------- 检查 venv ----------
if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "虚拟环境不存在或损坏，请先运行 start.sh 初始化"
    echo "  bash $APP_DIR/start.sh"
    exit 1
fi

# ---------- 停止旧进程 ----------
OLD_PID=$(port_pid)
if [ -n "$OLD_PID" ]; then
    echo "停止旧进程 (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1

    # 还没死就强制杀
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "强制终止..."
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi

    # 等待端口真正释放
    echo "等待端口 $PORT 释放..."
    if ! wait_port_free 8; then
        echo "警告: 端口 $PORT 未能释放，强制继续..."
    fi
    echo "端口已释放"
fi

# ---------- 启动 ----------
echo "启动服务 (端口 $PORT)..."
cd "$APP_DIR"
nohup "$VENV_DIR/bin/uvicorn" app.main:app --host 0.0.0.0 --port $PORT > "$APP_DIR/nas-monitor.log" 2>&1 &

sleep 2

NEW_PID=$(port_pid)
if [ -n "$NEW_PID" ]; then
    HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')
    echo "OK: http://$HOST_IP:$PORT"
else
    echo "FAIL: 查看 $APP_DIR/nas-monitor.log"
    tail -10 "$APP_DIR/nas-monitor.log"
    exit 1
fi
