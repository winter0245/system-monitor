from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.qbittorrent_service import qb_service
from app.services.transmission_service import tr_service
from app.services.speed_scheduler import scheduler, REMOVE_COOLDOWN

router = APIRouter()


class SpeedLimitRequest(BaseModel):
    download: int = 0  # KB/s
    upload: int = 0    # KB/s
    duration: int = 0  # 分钟，0=永久（直到下个时间段规则接管）


# ===== qBittorrent =====

@router.get("/qb/list")
async def qb_list():
    try:
        torrents = await qb_service.get_torrents()
        transfer = await qb_service.get_transfer_info()
        speed_limit = await qb_service.get_speed_limit()
        active = sum(1 for t in torrents if t["state"] == "downloading")
        seeding = sum(1 for t in torrents if t["state"] == "seeding")
        paused = sum(1 for t in torrents if t["state"] == "paused")
        return {
            "client": "qbittorrent",
            "stats": {**transfer, "active": active, "seeding": seeding, "paused": paused, "speed_limit": speed_limit},
            "torrents": torrents,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"qBittorrent connection error: {str(e)}")


@router.post("/qb/speed-limit")
async def qb_set_speed_limit(req: SpeedLimitRequest):
    try:
        scheduler.set_manual_override("qb", req.download, req.upload, req.duration)
        await qb_service.set_speed_limit(req.download, req.upload)
        dur_text = f" ({req.duration}分钟后自动解除)" if req.duration > 0 else ""
        return {"success": True, "message": f"qB 限速: ↓{req.download}KB/s ↑{req.upload}KB/s{dur_text}"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/qb/speed-limit/remove")
async def qb_remove_speed_limit():
    try:
        scheduler.set_manual_override("qb", 0, 0, duration_minutes=REMOVE_COOLDOWN)
        await qb_service.remove_speed_limit()
        return {"success": True, "message": f"qB 限速已解除（{REMOVE_COOLDOWN}分钟内不参与调度）"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/qb/pause-all")
async def qb_pause_all():
    try:
        await qb_service.pause_all()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/qb/resume-all")
async def qb_resume_all():
    try:
        await qb_service.resume_all()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ===== Transmission =====

@router.get("/tr/list")
async def tr_list():
    try:
        torrents = await tr_service.get_torrents()
        session_stats = await tr_service.get_session_stats()
        speed_limit = await tr_service.get_speed_limit()
        active = sum(1 for t in torrents if t["state"] == "downloading")
        seeding = sum(1 for t in torrents if t["state"] == "seeding")
        paused = sum(1 for t in torrents if t["state"] == "paused")
        return {
            "client": "transmission",
            "stats": {
                "download_speed": session_stats["download_speed"],
                "upload_speed": session_stats["upload_speed"],
                "active": active,
                "seeding": seeding,
                "paused": paused,
                "speed_limit": speed_limit,
            },
            "torrents": torrents,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transmission connection error: {str(e)}")


@router.post("/tr/speed-limit")
async def tr_set_speed_limit(req: SpeedLimitRequest):
    try:
        scheduler.set_manual_override("tr", req.download, req.upload, req.duration)
        await tr_service.set_speed_limit(req.download, req.upload)
        dur_text = f" ({req.duration}分钟后自动解除)" if req.duration > 0 else ""
        return {"success": True, "message": f"TR 限速: ↓{req.download}KB/s ↑{req.upload}KB/s{dur_text}"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/tr/speed-limit/remove")
async def tr_remove_speed_limit():
    try:
        scheduler.set_manual_override("tr", 0, 0, duration_minutes=REMOVE_COOLDOWN)
        await tr_service.remove_speed_limit()
        return {"success": True, "message": f"TR 限速已解除（{REMOVE_COOLDOWN}分钟内不参与调度）"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/tr/pause-all")
async def tr_pause_all():
    try:
        await tr_service.pause_all()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/tr/resume-all")
async def tr_resume_all():
    try:
        await tr_service.resume_all()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/speed-schedule")
async def speed_schedule_status():
    return scheduler.get_status()
