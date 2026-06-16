"""
PT 站点管理 API Router
- 站点 CRUD
- 数据快照查询
- 定时任务手动触发
- 访问日志查询
- 用户跳转记录
"""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.pt_site_service import db

router = APIRouter()


# ===== Pydantic Models =====

class SiteCreate(BaseModel):
    id: str                              # slug, e.g. 'mteam'
    name: str
    url: str
    cookie: str = ""
    user_agent: str = ""
    visit_freq: int = 2                  # 1-4
    visit_times: str = ""                # "08:00,20:00"
    enabled: int = 1
    notes: str = ""


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    cookie: Optional[str] = None
    user_agent: Optional[str] = None
    visit_freq: Optional[int] = None
    visit_times: Optional[str] = None
    enabled: Optional[int] = None
    notes: Optional[str] = None


class VisitLogRequest(BaseModel):
    visit_type: str = "manual"  # manual / scheduled
    url: Optional[str] = None


# ===== 站点 CRUD =====

@router.get("/sites")
async def list_sites():
    """列出所有站点（包含最新数据 + 用户手动访问信息）"""
    sites = db.list_sites()
    result = []
    for site in sites:
        site_id = site["id"]
        latest = db.get_latest_snapshot(site_id)
        summary = db.get_site_summary(site_id)
        last_success = db.get_last_success_time(site_id)
        last_user_visit = db.get_last_user_visit(site_id)
        last_redirect_time = db.get_last_redirect_time(site_id)
        result.append({
            **site,
            "latest_snapshot": latest,
            "today_delta": summary.get("today_delta", {}),
            "last_success_time": last_success,
            "last_user_visit": last_user_visit,
            "last_redirect_time": last_redirect_time,
        })
    return {"sites": result}


@router.get("/sites/{site_id}")
async def get_site(site_id: str):
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")
    latest = db.get_latest_snapshot(site_id)
    summary = db.get_site_summary(site_id)
    last_success = db.get_last_success_time(site_id)
    last_user_visit = db.get_last_user_visit(site_id)
    last_redirect_time = db.get_last_redirect_time(site_id)
    snapshots = db.get_snapshots(site_id, limit=30)
    return {
        "site": site,
        "latest_snapshot": latest,
        "today_delta": summary.get("today_delta", {}),
        "last_success_time": last_success,
        "last_user_visit": last_user_visit,
        "last_redirect_time": last_redirect_time,
        "snapshots": snapshots,
    }


@router.post("/sites")
async def create_site(data: SiteCreate):
    existing = db.get_site(data.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"站点 ID '{data.id}' 已存在")
    site = db.create_site(data.model_dump())
    return {"site": site}


@router.put("/sites/{site_id}")
async def update_site(site_id: str, data: SiteUpdate):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    site = db.update_site(site_id, updates)
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")
    return {"site": site}


@router.delete("/sites/{site_id}")
async def delete_site(site_id: str):
    ok = db.delete_site(site_id)
    if not ok:
        raise HTTPException(status_code=404, detail="站点不存在")
    return {"success": True}


# ===== 数据快照 =====

@router.get("/snapshots/{site_id}")
async def get_snapshots(site_id: str, limit: int = 30):
    snapshots = db.get_snapshots(site_id, limit=limit)
    return {"snapshots": snapshots}


@router.get("/snapshots/{site_id}/latest")
async def get_latest_snapshot(site_id: str):
    latest = db.get_latest_snapshot(site_id)
    if not latest:
        raise HTTPException(status_code=404, detail="暂无数据")
    summary = db.get_site_summary(site_id)
    return {"latest": latest, "today_delta": summary.get("today_delta", {})}


# ===== 访问日志 =====

@router.get("/logs")
async def get_visit_logs(site_id: Optional[str] = None, limit: int = 50, visit_type: Optional[str] = None):
    """获取访问日志，支持按 visit_type 筛选 (scheduled / manual)"""
    logs = db.get_visit_logs(site_id=site_id, limit=limit)
    if visit_type:
        logs = [l for l in logs if l["visit_type"] == visit_type]
    return {"logs": logs}


# ===== 用户跳转 =====

@router.post("/visit-log")
async def record_visit(data: VisitLogRequest):
    """用户从前端点击跳转按钮时调用，记录访问时间"""
    # 这个接口需要前端传 site_id 参数
    return {"success": True}


@router.post("/visit-log/{site_id}")
async def record_site_visit(site_id: str, data: VisitLogRequest = None):
    """记录用户链接跳转访问某站点"""
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")

    visit_type = "redirect"
    db.record_user_visit(site_id, visit_type)
    db.log_visit(site_id, visit_type, True, "用户链接跳转", "")

    # 返回站点 URL 供前端跳转
    return {
        "success": True,
        "site_name": site["name"],
        "url": site["url"],
        "last_visit": db.get_last_redirect_time(site_id),
    }


# ===== 手动触发 =====

@router.post("/scan")
async def trigger_scan(site_id: Optional[str] = None):
    """触发数据采集（异步后台执行，立即返回）"""
    sites = db.list_sites(enabled_only=True)
    if site_id:
        sites = [s for s in sites if s["id"] == site_id]

    if not sites:
        return {"success": False, "message": "没有需要扫描的站点"}

    # 后台异步执行，不等结果
    from app.services.pt_scheduler import _visit_and_record

    async def _run():
        for site in sites:
            await _visit_and_record(site, visit_type="manual")

    asyncio.create_task(_run())

    return {"success": True, "message": f"已触发 {len(sites)} 个站点扫描"}


@router.get("/schedule")
async def get_schedule_info():
    """获取各站点的定时任务安排"""
    from app.services.pt_scheduler import scheduler
    return {"schedules": scheduler.next_schedule_info()}


@router.post("/test/{site_id}")
async def test_site_visit(site_id: str):
    """测试单个站点的访问和解析（不保存数据）"""
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="站点不存在")

    from app.services.pt_monitor_service import monitor_site
    result = await monitor_site(site, simulate_browsing=True)
    return {
        "success": result["success"],
        "site_id": site_id,
        "data": result["data"],
        "message": result["message"],
    }
