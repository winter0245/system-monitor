import psutil
import platform
import time
from datetime import datetime


def _get_cpu_model() -> str:
    """跨平台获取 CPU 型号名称"""
    import subprocess
    system = platform.system()

    if system == "Windows":
        # 方式1: platform.processor() 在 Windows 上从注册表读，通常可靠
        cpu = platform.processor()
        if cpu and cpu.strip():
            return cpu.strip()
        # 方式2: 直接读注册表
        try:
            result = subprocess.run(
                ["reg", "query",
                 r"HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                 "/v", "ProcessorNameString"],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "ProcessorNameString" in line:
                        val = line.split("REG_SZ", 1)[-1].strip()
                        if val:
                            return val
        except Exception:
            pass
        # 方式3: wmic
        try:
            result = subprocess.run(
                ["wmic", "cpu", "get", "name"],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    line = line.strip()
                    if line and "name" not in line.lower():
                        return line
        except Exception:
            pass

    elif system == "Linux":
        # 方式1: 直接读 /proc/cpuinfo
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except (OSError, FileNotFoundError):
            pass
        # 方式2: lscpu 命令（容器/Docker 里更可靠）
        try:
            result = subprocess.run(
                ["lscpu"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Model name:" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        # 方式3: /proc/cpuinfo 的备选字段（ARM、虚拟机等）
        cpuinfo_fields = ["Processor", "cpu model", "Hardware"]
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    for field in cpuinfo_fields:
                        if line.startswith(field):
                            val = line.split(":", 1)[1].strip()
                            if val:
                                return val
        except (OSError, FileNotFoundError):
            pass

    elif system == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    return "Unknown"


def get_system_info() -> dict:
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    cpu_freq = psutil.cpu_freq()
    freq_str = f"{cpu_freq.current:.0f}MHz" if cpu_freq else "N/A"

    # 预热 cpu_percent，否则首次调用返回 0
    psutil.cpu_percent(interval=0.1)

    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu_model": _get_cpu_model(),
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "cpu_freq": freq_str,
        "total_memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "uptime": f"{days}d {hours}h {minutes}m",
        "boot_time": datetime.fromtimestamp(boot_time).isoformat(),
    }


def get_system_stats() -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    net = psutil.net_io_counters()

    disks = []
    for part in psutil.disk_partitions():
        if part.fstype and "snap" not in part.mountpoint:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024**3), 1),
                    "used_gb": round(usage.used / (1024**3), 1),
                    "percent": usage.percent,
                })
            except PermissionError:
                continue

    return {
        "cpu": {"percent": cpu_percent},
        "memory": {
            "percent": memory.percent,
            "used_gb": round(memory.used / (1024**3), 1),
            "total_gb": round(memory.total / (1024**3), 1),
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        },
        "disks": disks,
        "timestamp": time.time(),
    }


class NetworkSpeedTracker:
    def __init__(self):
        self._last = psutil.net_io_counters()
        self._last_time = time.time()
        self._history = []

    def get_speed(self) -> dict:
        current = psutil.net_io_counters()
        now = time.time()
        elapsed = now - self._last_time
        if elapsed <= 0:
            elapsed = 1

        download_speed = (current.bytes_recv - self._last.bytes_recv) / elapsed
        upload_speed = (current.bytes_sent - self._last.bytes_sent) / elapsed

        self._last = current
        self._last_time = now

        point = {
            "download_speed": round(download_speed),
            "upload_speed": round(upload_speed),
            "timestamp": now,
        }
        self._history.append(point)
        # 保留最近 900 个数据点（30分钟 × 2秒间隔）
        if len(self._history) > 900:
            self._history = self._history[-900:]

        return point

    def get_history(self) -> list:
        return self._history[-180:]  # 最近 6 分钟展示


network_tracker = NetworkSpeedTracker()
