import time
import json
import logging
from pathlib import Path
import feedparser
import httpx

from app.config import config

logger = logging.getLogger(__name__)

NEWS_CONFIG = config.get("news", {})
NEWS_PROXY = NEWS_CONFIG.get("proxy", "") or None
CACHE_TTL = config.get("cache", {}).get("news_ttl", 1800)
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

INTERNATIONAL_SOURCES = {"BBC中文", "Reuters", "The Verge", "路透中文", "联合早报"}


class NewsService:
    def __init__(self):
        self._cache = {}
        self._last_refresh = 0

    def _get_sources(self) -> dict:
        return NEWS_CONFIG.get("sources", {})

    def get_news(self, category: str = None) -> list:
        if category and category in self._cache:
            return self._cache[category]
        if category:
            return self._load_from_file(category)

        all_news = []
        sources = self._get_sources()
        for cat in sources:
            items = self._cache.get(cat) or self._load_from_file(cat)
            all_news.extend(items)
        all_news.sort(key=lambda x: x.get("published_ts", 0), reverse=True)
        return all_news[:50]

    def _load_from_file(self, category: str) -> list:
        cache_file = CACHE_DIR / f"news_{category}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                self._cache[category] = data
                return data
            except Exception:
                pass
        return []

    async def refresh_all(self):
        """后台定时调用，刷新所有分类"""
        logger.info("[News] 开始刷新所有新闻源...")
        sources = self._get_sources()
        for cat, src_list in sources.items():
            await self._refresh_category(cat, src_list)
        self._last_refresh = time.time()
        logger.info("[News] 刷新完成")

    async def refresh_category(self, category: str):
        """手动刷新单个分类"""
        sources = self._get_sources()
        if category in sources:
            await self._refresh_category(category, sources[category])

    async def _refresh_category(self, category: str, sources: list):
        items = []
        for source in sources:
            fetched = await self._fetch_feed(source, category)
            items.extend(fetched)

        items.sort(key=lambda x: x.get("published_ts", 0), reverse=True)
        items = items[:20]

        cache_file = CACHE_DIR / f"news_{category}.json"
        cache_file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        self._cache[category] = items
        logger.info(f"[News] {category}: 获取 {len(items)} 条")

    async def _fetch_feed(self, source: dict, category: str) -> list:
        name = source.get("name", "")
        url = source.get("url", "")
        if not url:
            return []

        try:
            use_proxy = NEWS_PROXY if name in INTERNATIONAL_SOURCES else None
            async with httpx.AsyncClient(proxy=use_proxy, timeout=15) as client:
                resp = await client.get(url, headers={"User-Agent": "NAS-Monitor/1.0"})
                if resp.status_code != 200:
                    logger.warning(f"[News] {name} HTTP {resp.status_code}")
                    return []
                content = resp.text

            feed = feedparser.parse(content)
            items = []
            for entry in feed.entries[:10]:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                pub_ts = time.mktime(published) if published else 0

                items.append({
                    "title": entry.get("title", "").strip(),
                    "url": entry.get("link", ""),
                    "source": name,
                    "category": category,
                    "published": entry.get("published") or entry.get("updated") or "",
                    "published_ts": pub_ts,
                    "summary": (entry.get("summary") or "")[:200].strip(),
                })
            return items
        except Exception as e:
            logger.warning(f"[News] {name} 抓取失败: {e}")
            return []

    def get_categories(self) -> list:
        return list(self._get_sources().keys())

    def get_last_refresh(self) -> float:
        return self._last_refresh


news_service = NewsService()
