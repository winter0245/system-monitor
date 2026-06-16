import asyncio
import time
import logging
from datetime import datetime

from app.config import config
from app.services.qbittorrent_service import qb_service
from app.services.transmission_service import tr_service

logger = logging.getLogger(__name__)

SPEED_CONFIG = config.get("speed_limit", {})
SCHEDULE_RULES = SPEED_CONFIG.get("schedule", [])
REMOVE_COOLDOWN = SPEED_CONFIG.get("remove_cooldown", 180)  # 默认3小时(分钟)


class SpeedLimitScheduler:
    def __init__(self):
        self._manual_override = {}  # {client: {download, upload, expire_at}}
        self._current_rule = None

    def get_status(self) -> dict:
        now = time.time()
        result = {"schedule_rule": self._get_active_rule_name(), "manual_overrides": {}}
        for client, override in self._manual_override.items():
            if override["expire_at"] and now > override["expire_at"]:
                continue
            remaining = None
            if override["expire_at"]:
                remaining = int(override["expire_at"] - now)
            result["manual_overrides"][client] = {
                "download": override["download"],
                "upload": override["upload"],
                "remaining_seconds": remaining,
            }
        return result

    def set_manual_override(self, client: str, download: int, upload: int, duration_minutes: int = 0):
        expire_at = None
        if duration_minutes > 0:
            expire_at = time.time() + duration_minutes * 60
        self._manual_override[client] = {
            "download": download,
            "upload": upload,
            "expire_at": expire_at,
        }
        logger.info(f"[SpeedLimit] 手动限速 {client}: ↓{download}KB/s ↑{upload}KB/s, 时长={duration_minutes}min")

    def remove_manual_override(self, client: str):
        if client in self._manual_override:
            del self._manual_override[client]
            logger.info(f"[SpeedLimit] 移除手动限速 {client}")

    def _get_active_rule(self):
        if not SCHEDULE_RULES:
            return None
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        for rule in SCHEDULE_RULES:
            start = rule.get("start", "00:00")
            end = rule.get("end", "23:59")
            if start <= end:
                if start <= current_time < end:
                    return rule
            else:  # 跨午夜，如 23:00 - 08:00
                if current_time >= start or current_time < end:
                    return rule
        return None

    def _get_active_rule_name(self) -> str:
        rule = self._get_active_rule()
        return rule.get("name", "无") if rule else "无规则"

    def get_client_source(self, client: str) -> dict:
        """返回指定客户端的限速来源信息"""
        now = time.time()
        override = self._manual_override.get(client)
        if override:
            if override["expire_at"] and now > override["expire_at"]:
                pass  # 已过期，走兜底逻辑
            else:
                if override["download"] == 0 and override["upload"] == 0:
                    return {
                        "source": "manual",
                        "label": "手动解除 · cooldown",
                        "rule_name": None,
                    }
                return {
                    "source": "manual",
                    "label": "手动限速",
                    "rule_name": None,
                }
        rule = self._get_active_rule()
        if rule:
            return {
                "source": "schedule",
                "label": f"定时 · {rule.get('name', '')}",
                "rule_name": rule.get("name"),
            }
        return {
            "source": "none",
            "label": "不限速",
            "rule_name": None,
        }

    async def apply_limits(self):
        now = time.time()
        # 清理过期的手动限速
        expired = [c for c, o in self._manual_override.items() if o["expire_at"] and now > o["expire_at"]]
        for client in expired:
            logger.info(f"[SpeedLimit] 手动限速已过期: {client}")
            del self._manual_override[client]

        # 决定每个客户端的限速
        for client, service in [("qb", qb_service), ("tr", tr_service)]:
            override = self._manual_override.get(client)
            if override:
                dl, ul = override["download"], override["upload"]
            else:
                rule = self._get_active_rule()
                if rule:
                    dl, ul = rule.get("download", 0), rule.get("upload", 0)
                else:
                    dl, ul = 0, 0

            try:
                if dl == 0 and ul == 0:
                    await service.remove_speed_limit()
                else:
                    await service.set_speed_limit(dl, ul)
            except Exception as e:
                logger.warning(f"[SpeedLimit] {client} 应用限速失败: {e}")


scheduler = SpeedLimitScheduler()


async def speed_limit_loop():
    while True:
        await scheduler.apply_limits()
        await asyncio.sleep(60)
