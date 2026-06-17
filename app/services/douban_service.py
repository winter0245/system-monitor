import base64
import hashlib
import hmac
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from random import choice
from urllib import parse

import httpx

from app.config import config

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL = config.get("cache", {}).get("movie_ttl", 21600)
DOUBAN_CONFIG = config.get("douban", {})


class DoubanService:
    _base_url = "https://frodo.douban.com/api/v2"
    _api_key = DOUBAN_CONFIG.get("api_key", "")
    _api_secret = DOUBAN_CONFIG.get("api_secret", "")
    _user_agents = [
        "api-client/1 com.douban.frodo/7.22.0.beta9(231) Android/23 product/Mate 40 vendor/HUAWEI model/Mate 40 brand/HUAWEI  rom/android  network/wifi  platform/AndroidPad",
        "api-client/1 com.douban.frodo/7.18.0(230) Android/22 product/MI 9 vendor/Xiaomi model/MI 9 brand/Android  rom/miui6  network/wifi  platform/mobile nd/1",
        "api-client/1 com.douban.frodo/7.1.0(205) Android/29 product/perseus vendor/Xiaomi model/Mi MIX 3  rom/miui6  network/wifi  platform/mobile nd/1",
    ]

    _collections = {
        "movie_hot": "/subject_collection/movie_hot_gaia/items",
        "movie_showing": "/subject_collection/movie_showing/items",
        "movie_top250": "/subject_collection/movie_top250/items",
        "tv_hot": "/subject_collection/tv_hot/items",
        "tv_domestic": "/subject_collection/tv_domestic/items",
        "tv_american": "/subject_collection/tv_american/items",
        "tv_japanese": "/subject_collection/tv_japanese/items",
        "tv_korean": "/subject_collection/tv_korean/items",
        "tv_animation": "/subject_collection/tv_animation/items",
    }

    def __init__(self):
        self._cache = {}
        self._cache_time = {}

    @classmethod
    def _sign(cls, url: str, ts: str) -> str:
        url_path = parse.urlparse(url).path
        raw_sign = "&".join(["GET", parse.quote(url_path, safe=""), ts])
        return base64.b64encode(
            hmac.new(
                cls._api_secret.encode(),
                raw_sign.encode(),
                hashlib.sha1
            ).digest()
        ).decode()

    async def _request(self, path: str, count: int = 20, start: int = 0):
        url = self._base_url + path
        ts = datetime.strftime(datetime.now(), "%Y%m%d")
        params = {
            "apiKey": self._api_key,
            "os_rom": "android",
            "_ts": ts,
            "_sig": self._sign(url, ts),
            "start": str(start),
            "count": str(count),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url, params=params,
                    headers={"User-Agent": choice(self._user_agents)}
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"[Douban] {path} HTTP {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"[Douban] {path} 请求失败: {e}")
            return None

    async def get_collection(self, key: str, count: int = 20) -> list:
        now = time.time()
        if key in self._cache and (now - self._cache_time.get(key, 0)) < CACHE_TTL:
            return self._cache[key]

        cache_file = CACHE_DIR / f"douban_{key}.json"
        if cache_file.exists():
            mtime = cache_file.stat().st_mtime
            if (now - mtime) < CACHE_TTL:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                self._cache[key] = data
                self._cache_time[key] = mtime
                return data

        path = self._collections.get(key)
        if not path:
            return []

        result = await self._request(path, count=count)
        if not result:
            return self._cache.get(key, [])

        items = [self._format(item) for item in result.get("subject_collection_items", [])]

        cache_file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        self._cache[key] = items
        self._cache_time[key] = now
        return items

    async def get_movie_hot(self) -> list:
        return await self.get_collection("movie_hot")

    async def get_movie_showing(self) -> list:
        return await self.get_collection("movie_showing")

    async def get_tv_hot(self) -> list:
        return await self.get_collection("tv_hot")

    async def get_tv_domestic(self) -> list:
        return await self.get_collection("tv_domestic")

    def _format(self, item: dict) -> dict:
        rating = item.get("rating", {})
        score = rating.get("value", 0) if rating else 0
        # 电影用 cover，剧集用 pic，格式不同
        cover = item.get("cover", {})
        pic = item.get("pic", {})
        if isinstance(cover, dict) and cover.get("url"):
            cover_url = cover["url"]
        elif isinstance(pic, dict) and pic.get("normal"):
            cover_url = pic["normal"]
        elif isinstance(cover, str):
            cover_url = cover
        elif isinstance(pic, str):
            cover_url = pic
        else:
            cover_url = ""
        return {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "year": item.get("year", ""),
            "rating": score,
            "cover_url": cover_url,
            "card_subtitle": item.get("card_subtitle", ""),
            "type": item.get("type", ""),
            "url": f"https://movie.douban.com/subject/{item.get('id', '')}/",
        }


douban_service = DoubanService()
