from fastapi import APIRouter

from app.services.news_service import news_service

router = APIRouter()


@router.get("")
async def get_news(category: str = None):
    items = news_service.get_news(category)
    return {"category": category or "all", "items": items}


@router.get("/categories")
async def get_categories():
    return {"categories": news_service.get_categories()}


@router.post("/refresh")
async def refresh_news(category: str = None):
    if category:
        await news_service.refresh_category(category)
    else:
        await news_service.refresh_all()
    return {"success": True, "last_refresh": news_service.get_last_refresh()}


@router.get("/status")
async def news_status():
    return {"last_refresh": news_service.get_last_refresh()}
