import time
import json
from pathlib import Path
import httpx

from app.config import config

TMDB_CONFIG = config.get("tmdb", {})
TMDB_KEY = TMDB_CONFIG.get("api_key", "")
TMDB_LANG = TMDB_CONFIG.get("language", "zh-CN")
TMDB_PROXY = TMDB_CONFIG.get("proxy", "") or None
CACHE_TTL = config.get("cache", {}).get("movie_ttl", 21600)
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


class TMDBService:
    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self):
        self._client = httpx.AsyncClient(proxy=TMDB_PROXY, timeout=15)
        self._cache = {}
        self._cache_time = {}

    async def get_trending_movies(self) -> list:
        return await self._fetch_cached("trending_movies", "/trending/movie/week")

    async def get_trending_tv(self) -> list:
        return await self._fetch_cached("trending_tv", "/trending/tv/week")

    async def get_top_rated_movies(self) -> list:
        return await self._fetch_cached("top_rated_movies", "/movie/top_rated")

    async def _fetch_cached(self, cache_key: str, endpoint: str) -> list:
        now = time.time()
        if cache_key in self._cache and (now - self._cache_time.get(cache_key, 0)) < CACHE_TTL:
            return self._cache[cache_key]

        cache_file = CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            mtime = cache_file.stat().st_mtime
            if (now - mtime) < CACHE_TTL:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                self._cache[cache_key] = data
                self._cache_time[cache_key] = mtime
                return data

        if not TMDB_KEY:
            return []

        try:
            resp = await self._client.get(
                f"{self.BASE_URL}{endpoint}",
                params={"api_key": TMDB_KEY, "language": TMDB_LANG, "page": 1},
            )
            if resp.status_code != 200:
                return self._cache.get(cache_key, [])

            results = resp.json().get("results", [])
            data = [self._format(item, endpoint) for item in results[:20]]

            cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self._cache[cache_key] = data
            self._cache_time[cache_key] = now
            return data
        except Exception:
            return self._cache.get(cache_key, [])

    def _format(self, item: dict, endpoint: str) -> dict:
        is_tv = "/tv" in endpoint
        return {
            "id": item.get("id"),
            "title": item.get("name" if is_tv else "title", ""),
            "original_title": item.get("original_name" if is_tv else "original_title", ""),
            "year": (item.get("first_air_date") or item.get("release_date") or "")[:4],
            "rating": round(item.get("vote_average", 0), 1),
            "overview": item.get("overview", ""),
            "poster_path": item.get("poster_path", ""),
            "poster_url": f"https://image.tmdb.org/t/p/w300{item['poster_path']}" if item.get("poster_path") else "",
            "media_type": "tv" if is_tv else "movie",
        }


tmdb_service = TMDBService()
