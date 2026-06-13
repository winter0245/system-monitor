import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.config import config
from app.routers import system, torrent, movie, news
from app.services.news_service import news_service
from app.services.speed_scheduler import speed_limit_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

NEWS_INTERVAL = config.get("news", {}).get("refresh_interval", 1800)


async def news_refresh_loop():
    await news_service.refresh_all()
    while True:
        await asyncio.sleep(NEWS_INTERVAL)
        await news_service.refresh_all()


@asynccontextmanager
async def lifespan(app: FastAPI):
    news_task = asyncio.create_task(news_refresh_loop())
    speed_task = asyncio.create_task(speed_limit_loop())
    yield
    news_task.cancel()
    speed_task.cancel()


app = FastAPI(title="NAS Monitor", version="1.0.0", lifespan=lifespan)

app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(torrent.router, prefix="/api/torrent", tags=["torrent"])
app.include_router(movie.router, prefix="/api/movies", tags=["movies"])
app.include_router(news.router, prefix="/api/news", tags=["news"])

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index():
    return FileResponse(static_dir / "index.html")
