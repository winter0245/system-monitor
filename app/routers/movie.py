from fastapi import APIRouter, Query
from fastapi.responses import Response
import httpx

from app.services.tmdb_service import tmdb_service
from app.services.douban_service import douban_service

router = APIRouter()


@router.get("/img-proxy")
async def img_proxy(url: str = Query(...)):
    """图片代理，解决豆瓣等 CDN 的 Referer 防盗链"""
    # 根据域名决定 Referer
    referer = None
    if "doubanio.com" in url:
        referer = "https://movie.douban.com/"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if referer:
        headers["Referer"] = referer

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/webp"),
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except Exception:
        return Response(status_code=404)


@router.get("/trending")
async def trending():
    movies = await tmdb_service.get_trending_movies()
    tv = await tmdb_service.get_trending_tv()
    return {"movies": movies, "tv": tv}


@router.get("/top-rated")
async def top_rated():
    movies = await tmdb_service.get_top_rated_movies()
    return {"movies": movies}


@router.get("/trending/movies")
async def trending_movies():
    return await tmdb_service.get_trending_movies()


@router.get("/trending/tv")
async def trending_tv():
    return await tmdb_service.get_trending_tv()


@router.get("/douban/movie-hot")
async def douban_movie_hot():
    return await douban_service.get_movie_hot()


@router.get("/douban/movie-showing")
async def douban_movie_showing():
    return await douban_service.get_movie_showing()


@router.get("/douban/tv-hot")
async def douban_tv_hot():
    return await douban_service.get_tv_hot()


@router.get("/douban/tv-domestic")
async def douban_tv_domestic():
    return await douban_service.get_tv_domestic()
