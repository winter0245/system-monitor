import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.system_service import get_system_info, get_system_stats, network_tracker

router = APIRouter()


@router.get("/info")
async def system_info():
    return get_system_info()


@router.get("/stats")
async def system_stats():
    stats = get_system_stats()
    speed = network_tracker.get_speed()
    stats["network"]["download_speed"] = speed["download_speed"]
    stats["network"]["upload_speed"] = speed["upload_speed"]
    return stats


@router.get("/network/history")
async def network_history():
    return network_tracker.get_history()


@router.websocket("/ws")
async def system_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            stats = get_system_stats()
            speed = network_tracker.get_speed()
            stats["network"]["download_speed"] = speed["download_speed"]
            stats["network"]["upload_speed"] = speed["upload_speed"]
            await websocket.send_json(stats)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception:
        await websocket.close()
