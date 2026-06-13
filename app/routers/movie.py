from fastapi import APIRouter

from app.services.tmdb_service import tmdb_service
from app.services.douban_service import douban_service

router = APIRouter()


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
