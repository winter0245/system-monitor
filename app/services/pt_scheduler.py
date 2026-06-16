"""
PT 站点定时访问调度器
- 支持按站点配置不同的访问频率和时间
- 每个站点的 visit_times 或 visit_freq 决定何时执行
- 每个时间点有随机窗口，基于 日期+站点+时间点 生成稳定的随机偏移
- 同一天内时间固定，每天不同，模拟真人访问习惯
"""

import asyncio
import hashlib
import logging
import time
import random
from datetime import datetime, timedelta
from typing import Optional

from app.config import config
from app.services.pt_site_service import db
from app.services.pt_monitor_service import monitor_site

logger = logging.getLogger(__name__)

# 从配置文件读取访问时间表，提供默认回退
DEFAULT_VISIT_SCHEDULE = {
    1: [{"time": "09:00", "window": 45}],
    2: [{"time": "09:00", "window": 45}, {"time": "21:00", "window": 45}],
    3: [{"time": "08:00", "window": 40}, {"time": "14:00", "window": 40}, {"time": "20:00", "window": 40}],
    4: [{"time": "06:00", "window": 30}, {"time": "12:00", "window": 30}, {"time": "18:00", "window": 30}, {"time": "23:00", "window": 30}],
}


def _get_visit_schedule() -> dict:
    """从配置文件读取访问时间表"""
    pt_config = config.get("pt", {})
    raw = pt_config.get("visit_schedule", None)
    if raw is None:
        return DEFAULT_VISIT_SCHEDULE
    # config.yaml 的 key 是 int，但 YAML 可能读成 str，做一下转换
    result = {}
    for k, v in raw.items():
        freq = int(k)
        slots = []
        for item in v:
            slots.append({
                "time": str(item["time"]),
                "window": int(item.get("window", 30)),
            })
        result[freq] = slots
    return result


def _stable_random_offset(date_str: str, site_id: str, time_str: str, window: int) -> int:
    """
    基于 日期 + 站点ID + 时间点 生成稳定的随机偏移（分钟）
    同一天内同一站点的同一时间点偏移不变，每天不同
    """
    seed_str = f"{date_str}|{site_id}|{time_str}"
    seed_hash = hashlib.md5(seed_str.encode()).hexdigest()
    seed_int = int(seed_hash[:8], 16)
    rng = random.Random(seed_int)
    # 在 [-window, +window] 内均匀分布
    return rng.randint(-window, window)


class PtScheduler:
    """PT 站点定时调度器"""

    def __init__(self):
        self._last_run: dict[str, float] = {}  # site_id -> last run timestamp
        self._running = False

    def _get_site_slots(self, site: dict) -> list[dict]:
        """
        解析站点的访问时间点列表，返回 [{"time": "08:00", "window": 40}, ...]
        """
        visit_times = site.get("visit_times", "").strip()
        if visit_times:
            # 自定义时间，每个时间点用默认 30 分钟窗口
            times = [t.strip() for t in visit_times.split(",") if t.strip()]
            return [{"time": t, "window": 30} for t in times]

        # 回退到 visit_freq 从配置文件读取
        freq = site.get("visit_freq", 2)
        schedule = _get_visit_schedule()
        return schedule.get(freq, schedule[2])

    def _get_site_times(self, site: dict) -> list[str]:
        """兼容旧接口：返回时间字符串列表"""
        return [s["time"] for s in self._get_site_slots(site)]

    def _next_run_time(self, site: dict) -> Optional[float]:
        """
        计算站点下一次应该执行的时间（Unix timestamp），含随机偏移
        返回 None 表示今天没有更多执行时间
        """
        slots = self._get_site_slots(site)
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        for slot in sorted(slots, key=lambda s: s["time"]):
            base_time = slot["time"]
            window = slot.get("window", 30)

            # 计算随机偏移后的实际执行时间
            offset_minutes = _stable_random_offset(today_str, site["id"], base_time, window)
            base_dt = datetime.strptime(f"{today_str} {base_time}", "%Y-%m-%d %H:%M")
            actual_dt = base_dt + timedelta(minutes=offset_minutes)

            if actual_dt > now:
                last_key = site["id"]
                last_run = self._last_run.get(last_key, 0)
                # 如果这个时间点还没执行过
                if last_run < actual_dt.timestamp():
                    return actual_dt.timestamp()

        return None  # 今天已全部执行，等明天

    async def run_once(self, site_id: str = None):
        """手动触发一次访问（支持指定站点或全部）"""
        sites = db.list_sites(enabled_only=True)
        if site_id:
            sites = [s for s in sites if s["id"] == site_id]
            if not sites:
                logger.warning(f"[PT Scheduler] 站点不存在或已禁用: {site_id}")
                return

        if not sites:
            logger.info("[PT Scheduler] 没有启用的 PT 站点，跳过")
            return

        logger.info(f"[PT Scheduler] 手动执行: {len(sites)} 个站点")

        # 并发访问所有站点（每个站点独立，不互相阻塞）
        tasks = [_visit_and_record(site) for site in sites]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        fail_count = len(sites) - success_count
        logger.info(f"[PT Scheduler] 手动执行完成: 成功 {success_count}, 失败 {fail_count}")

    async def run_scheduled(self):
        """执行所有到期站点的定时访问"""
        sites = db.list_sites(enabled_only=True)
        now = time.time()

        to_run = []
        for site in sites:
            next_time = self._next_run_time(site)
            if next_time and next_time <= now + 60:  # 1分钟容差
                last_key = site["id"]
                last_run = self._last_run.get(last_key, 0)
                if now - last_run >= 300:  # 至少间隔5分钟，防重复
                    to_run.append(site)

        if to_run:
            logger.info(f"[PT Scheduler] 定时执行: {len(to_run)} 个站点")
            tasks = [_visit_and_record(site) for site in to_run]
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            logger.debug("[PT Scheduler] 没有到期的站点")

    async def start_loop(self):
        """启动调度循环，每分钟检查一次"""
        self._running = True
        logger.info("[PT Scheduler] 调度循环启动")
        while self._running:
            try:
                await self.run_scheduled()
            except Exception as e:
                logger.error(f"[PT Scheduler] 调度异常: {e}")
            await asyncio.sleep(60)

    def stop(self):
        self._running = False

    def next_schedule_info(self) -> list:
        """返回各站点的下次执行时间（含随机偏移，供前端展示）"""
        sites = db.list_sites(enabled_only=True)
        result = []
        for site in sites:
            slots = self._get_site_slots(site)
            today_str = datetime.now().strftime("%Y-%m-%d")
            # 构建实际时间列表
            actual_times = []
            for slot in slots:
                base = slot["time"]
                window = slot.get("window", 30)
                offset = _stable_random_offset(today_str, site["id"], base, window)
                base_dt = datetime.strptime(f"{today_str} {base}", "%Y-%m-%d %H:%M")
                actual_dt = base_dt + timedelta(minutes=offset)
                actual_times.append(actual_dt.strftime("%H:%M"))

            next_run = self._next_run_time(site)
            result.append({
                "site_id": site["id"],
                "site_name": site["name"],
                "visit_times": actual_times,
                "next_run": datetime.fromtimestamp(next_run).strftime("%Y-%m-%d %H:%M:%S") if next_run else "明天",
            })
        return result


async def _visit_and_record(site: dict, visit_type: str = "scheduled") -> dict:
    """访问一个站点并记录结果"""
    site_id = site["id"]
    site_name = site["name"]

    self_ref = globals().get("scheduler")
    if self_ref:
        self_ref._last_run[site_id] = time.time()

    # 执行 Playwright 访问
    result = await monitor_site(site, simulate_browsing=True)

    if result["success"] and result["data"]:
        # 保存数据快照
        db.save_snapshot(site_id, result["data"])
        db.log_visit(site_id, visit_type, True, "访问成功",
                     f"上传:{_fmt_bytes(result['data']['upload_bytes'])} 下载:{_fmt_bytes(result['data']['download_bytes'])} 积分:{result['data']['seed_points']}")
        logger.info(f"[PT] {site_name} 监控成功")
    else:
        db.log_visit(site_id, visit_type, False, result.get("message", "未知错误"), "")
        logger.warning(f"[PT] {site_name} 监控失败: {result.get('message')}")

    return result


def _fmt_bytes(b: int) -> str:
    """格式化字节数"""
    if b >= 1024 ** 4:
        return f"{b / 1024 ** 4:.1f}TB"
    if b >= 1024 ** 3:
        return f"{b / 1024 ** 3:.1f}GB"
    if b >= 1024 ** 2:
        return f"{b / 1024 ** 2:.1f}MB"
    if b >= 1024:
        return f"{b / 1024:.1f}KB"
    return f"{b}B"


# 全局调度器单例
scheduler = PtScheduler()
