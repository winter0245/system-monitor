import httpx
from app.config import config

TR_CONFIG = config.get("transmission", {})
TR_URL = TR_CONFIG.get("url", "http://localhost:9091")
TR_USER = TR_CONFIG.get("username", "")
TR_PASS = TR_CONFIG.get("password", "")


class TransmissionService:
    def __init__(self):
        self._session_id = ""
        auth = (TR_USER, TR_PASS) if TR_USER else None
        self._client = httpx.AsyncClient(base_url=TR_URL, timeout=10, auth=auth)

    async def _rpc(self, method: str, arguments: dict = None) -> dict:
        payload = {"method": method}
        if arguments:
            payload["arguments"] = arguments

        headers = {"X-Transmission-Session-Id": self._session_id}
        resp = await self._client.post("/transmission/rpc", json=payload, headers=headers)

        if resp.status_code == 409:
            self._session_id = resp.headers.get("X-Transmission-Session-Id", "")
            headers["X-Transmission-Session-Id"] = self._session_id
            resp = await self._client.post("/transmission/rpc", json=payload, headers=headers)

        if resp.status_code != 200:
            raise ConnectionError(f"Transmission RPC error: {resp.status_code}")

        return resp.json()

    async def get_torrents(self) -> list:
        fields = [
            "id", "name", "totalSize", "percentDone", "rateDownload", "rateUpload",
            "peersConnected", "peersSendingToUs", "peersGettingFromUs",
            "eta", "status", "uploadRatio", "addedDate", "labels",
        ]
        result = await self._rpc("torrent-get", {"fields": fields})
        torrents = result.get("arguments", {}).get("torrents", [])
        return [self._format_torrent(t) for t in torrents]

    async def get_session_stats(self) -> dict:
        result = await self._rpc("session-stats")
        args = result.get("arguments", {})
        return {
            "download_speed": args.get("downloadSpeed", 0),
            "upload_speed": args.get("uploadSpeed", 0),
            "active_torrent_count": args.get("activeTorrentCount", 0),
            "paused_torrent_count": args.get("pausedTorrentCount", 0),
            "torrent_count": args.get("torrentCount", 0),
        }

    async def get_speed_limit(self) -> dict:
        result = await self._rpc("session-get")
        args = result.get("arguments", {})
        dl_enabled = args.get("speed-limit-down-enabled", False)
        ul_enabled = args.get("speed-limit-up-enabled", False)
        return {
            "enabled": dl_enabled or ul_enabled,
            "download": args.get("speed-limit-down", 0) if dl_enabled else 0,
            "upload": args.get("speed-limit-up", 0) if ul_enabled else 0,
        }

    async def set_speed_limit(self, download: int, upload: int):
        await self._rpc("session-set", {
            "speed-limit-down-enabled": True,
            "speed-limit-down": download,
            "speed-limit-up-enabled": True,
            "speed-limit-up": upload,
        })

    async def remove_speed_limit(self):
        await self._rpc("session-set", {
            "speed-limit-down-enabled": False,
            "speed-limit-up-enabled": False,
        })

    async def pause_all(self):
        await self._rpc("torrent-stop")

    async def resume_all(self):
        await self._rpc("torrent-start")

    def _format_torrent(self, t: dict) -> dict:
        # TR status: 0=stopped, 1=check_wait, 2=checking, 3=dl_wait,
        #            4=downloading, 5=seed_wait, 6=seeding
        status_val = t.get("status", 0)
        if status_val == 0:
            state = "paused"
        elif status_val in (1, 2):
            state = "checking"
        elif status_val in (3, 4):
            state = "downloading"
        elif status_val in (5, 6):
            state = "seeding"
        else:
            state = "unknown"

        return {
            "hash": str(t.get("id", "")),
            "name": t.get("name", ""),
            "size": t.get("totalSize", 0),
            "progress": round(t.get("percentDone", 0), 4),
            "download_speed": t.get("rateDownload", 0),
            "upload_speed": t.get("rateUpload", 0),
            "peers": t.get("peersConnected", 0),
            "seeds": t.get("peersSendingToUs", 0),
            "eta": t.get("eta", -1),
            "state": state,
            "category": ", ".join(t.get("labels", [])),
            "tags": "",
            "ratio": round(t.get("uploadRatio", 0), 2),
            "added_on": t.get("addedDate", 0),
        }


tr_service = TransmissionService()
