import httpx
from app.config import config

QB_CONFIG = config.get("qbittorrent", {})
QB_URL = QB_CONFIG.get("url", "http://localhost:8080")
QB_USER = QB_CONFIG.get("username", "admin")
QB_PASS = QB_CONFIG.get("password", "adminadmin")


class QBittorrentService:
    def __init__(self):
        self._cookie = None
        self._client = httpx.AsyncClient(base_url=QB_URL, timeout=10)

    async def _login(self):
        resp = await self._client.post("/api/v2/auth/login", data={
            "username": QB_USER,
            "password": QB_PASS,
        })
        if resp.status_code in (200, 204) or resp.text == "Ok.":
            # 新版 qB cookie 名为 QBT_SID_端口号，旧版为 SID
            for name, value in resp.cookies.items():
                if "SID" in name.upper():
                    self._cookie = value
                    self._client.cookies.set(name, value)
                    return
            raise ConnectionError("qBittorrent login: no SID cookie returned")
        else:
            raise ConnectionError(f"qBittorrent login failed: HTTP {resp.status_code}")

    async def _request(self, method: str, path: str, **kwargs):
        if not self._cookie:
            await self._login()
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code == 403:
            await self._login()
            resp = await self._client.request(method, path, **kwargs)
        return resp

    async def get_torrents(self) -> list:
        resp = await self._request("GET", "/api/v2/torrents/info")
        if resp.status_code != 200:
            return []
        torrents = resp.json()
        return [self._format_torrent(t) for t in torrents]

    async def get_transfer_info(self) -> dict:
        resp = await self._request("GET", "/api/v2/transfer/info")
        if resp.status_code != 200:
            return {}
        data = resp.json()
        return {
            "download_speed": data.get("dl_info_speed", 0),
            "upload_speed": data.get("up_info_speed", 0),
            "download_total": data.get("dl_info_data", 0),
            "upload_total": data.get("up_info_data", 0),
        }

    async def get_speed_limit(self) -> dict:
        dl_resp = await self._request("GET", "/api/v2/transfer/downloadLimit")
        ul_resp = await self._request("GET", "/api/v2/transfer/uploadLimit")
        # qB API 返回 bytes/sec，统一转为 KB/s
        dl = int(dl_resp.text.strip()) // 1024 if dl_resp.status_code == 200 else 0
        ul = int(ul_resp.text.strip()) // 1024 if ul_resp.status_code == 200 else 0
        return {
            "enabled": dl > 0 or ul > 0,
            "download": dl,
            "upload": ul,
        }

    async def set_speed_limit(self, download: int, upload: int):
        await self._request("POST", "/api/v2/transfer/setDownloadLimit", data={"limit": download * 1024})
        await self._request("POST", "/api/v2/transfer/setUploadLimit", data={"limit": upload * 1024})

    async def remove_speed_limit(self):
        await self._request("POST", "/api/v2/transfer/setDownloadLimit", data={"limit": 0})
        await self._request("POST", "/api/v2/transfer/setUploadLimit", data={"limit": 0})

    async def pause_all(self):
        await self._request("POST", "/api/v2/torrents/pause", data={"hashes": "all"})

    async def resume_all(self):
        await self._request("POST", "/api/v2/torrents/resume", data={"hashes": "all"})

    def _format_torrent(self, t: dict) -> dict:
        state_map = {
            "downloading": "downloading",
            "stalledDL": "downloading",
            "uploading": "seeding",
            "stalledUP": "seeding",
            "pausedDL": "paused",
            "pausedUP": "paused",
            "queuedDL": "queued",
            "queuedUP": "queued",
            "error": "error",
            "missingFiles": "error",
        }
        return {
            "hash": t.get("hash", ""),
            "name": t.get("name", ""),
            "size": t.get("total_size", 0),
            "progress": round(t.get("progress", 0), 4),
            "download_speed": t.get("dlspeed", 0),
            "upload_speed": t.get("upspeed", 0),
            "peers": t.get("num_leechs", 0),
            "seeds": t.get("num_seeds", 0),
            "eta": t.get("eta", 0),
            "state": state_map.get(t.get("state", ""), "unknown"),
            "category": t.get("category", ""),
            "tags": t.get("tags", ""),
            "ratio": round(t.get("ratio", 0), 2),
            "added_on": t.get("added_on", 0),
        }


qb_service = QBittorrentService()
