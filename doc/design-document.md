# NAS Monitor - 系统监控大盘设计文档

## 基本信息

- **项目名称**：NAS Monitor
- **创建时间**：2026-06-12 15:42
- **部署环境**：Debian NAS 主机
- **技术栈**：Python (FastAPI) + 纯 H5 前端
- **访问方式**：局域网 Web 访问，响应式适配 PC/移动端

---

## 1. 项目概述

一个轻量级 NAS 服务器监控大盘，提供系统资源监控、BT 下载任务管理、影视内容推荐和新闻资讯聚合四大功能模块。

### 1.1 核心目标

- 实时掌握 NAS 系统资源状态
- 统一管理 qBittorrent 和 Transmission 下载任务
- 浏览热门影视推荐，辅助下载决策
- 聚合多源新闻资讯

### 1.2 设计原则

- **轻量部署**：单 Python 进程，无需数据库
- **零依赖前端**：纯 HTML/CSS/JS，不引入框架
- **暗色主题**：参考 VueTorrent 深色 UI 风格
- **响应式**：移动端和 PC 端均可良好使用

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    浏览器 (H5)                        │
│  ┌──────┬──────────┬──────────┬──────────┐          │
│  │Tab1  │  Tab2    │  Tab3    │  Tab4    │          │
│  │监控  │  种子    │  影视    │  新闻    │          │
│  └──┬───┴────┬─────┴────┬─────┴────┬─────┘          │
│     │ WS     │ REST     │ REST     │ REST           │
└─────┼────────┼──────────┼──────────┼────────────────┘
      │        │          │          │
┌─────┼────────┼──────────┼──────────┼────────────────┐
│     ▼        ▼          ▼          ▼     FastAPI     │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐               │
│  │System│ │Torrent│ │Movie │ │News  │               │
│  │Module│ │Module │ │Module│ │Module│               │
│  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘               │
│     │        │        │        │                    │
│     ▼        ▼        ▼        ▼                    │
│  psutil   qB API   TMDB API  RSS Feeds             │
│           TR RPC   豆瓣 RSS                         │
└─────────────────────────────────────────────────────┘
```

### 2.1 目录结构

```
system-monitor/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置文件
│   ├── routers/
│   │   ├── system.py        # 系统监控 API
│   │   ├── torrent.py       # 种子任务 API
│   │   ├── movie.py         # 影视推荐 API
│   │   └── news.py          # 新闻资讯 API
│   ├── services/
│   │   ├── system_service.py
│   │   ├── qbittorrent_service.py
│   │   ├── transmission_service.py
│   │   ├── tmdb_service.py
│   │   └── news_service.py
│   └── static/
│       └── index.html       # 单页前端
├── config.yaml              # 用户配置
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 3. 功能模块详细设计

### 3.1 Tab1 - 系统监控

#### 数据采集

| 指标 | 采集方式 | 刷新频率 |
|------|---------|---------|
| CPU 使用率 | `psutil.cpu_percent(interval=1)` | 2s |
| 内存使用 | `psutil.virtual_memory()` | 5s |
| 磁盘使用 | `psutil.disk_usage()` | 30s |
| 网络流量 | `psutil.net_io_counters()` | 2s |
| 系统信息 | `platform` + `psutil.boot_time()` | 启动时 |

#### 数据推送

- **协议**：WebSocket (`/ws/system`)
- **格式**：JSON
- **推送间隔**：2 秒

#### 数据结构

```json
{
  "cpu": {
    "percent": 23.5,
    "cores": 6,
    "threads": 12,
    "model": "Intel i5-12400",
    "freq_current": 2400
  },
  "memory": {
    "percent": 62.3,
    "used_gb": 20.1,
    "total_gb": 32.0
  },
  "network": {
    "download_speed": 47448064,
    "upload_speed": 13421772,
    "download_today": 137975824384,
    "upload_today": 38862249984
  },
  "disks": [
    {
      "device": "/dev/sda1",
      "label": "系统盘",
      "type": "NVMe",
      "used_gb": 186,
      "total_gb": 500,
      "percent": 37.2
    }
  ],
  "uptime": "15d 7h 23m"
}
```

#### 前端展示

- 4 个数值卡片（CPU / 内存 / 下载速度 / 上传速度）
- SVG 实时流量折线图（保留最近 30 分钟数据点）
- 磁盘使用进度条列表

---

### 3.2 Tab2 - 种子任务

#### 3.2.1 qBittorrent 集成

**API 基础**：qBittorrent WebUI API v2

| 功能 | API 端点 | 方法 |
|------|---------|------|
| 登录 | `/api/v2/auth/login` | POST |
| 获取任务列表 | `/api/v2/torrents/info` | GET |
| 获取全局速度 | `/api/v2/transfer/info` | GET |
| 设置限速 | `/api/v2/transfer/setDownloadLimit` | POST |
| 解除限速 | `/api/v2/transfer/setDownloadLimit` (0) | POST |
| 暂停全部 | `/api/v2/torrents/pause` | POST |
| 恢复全部 | `/api/v2/torrents/resume` | POST |

#### 3.2.2 Transmission 集成

**API 基础**：Transmission RPC (JSON-RPC)

| 功能 | RPC Method | 说明 |
|------|-----------|------|
| 获取任务列表 | `torrent-get` | fields 指定需要的字段 |
| 获取会话信息 | `session-get` | 包含速度统计 |
| 设置限速 | `session-set` | speed-limit-down-enabled + speed-limit-down |
| 解除限速 | `session-set` | speed-limit-down-enabled: false |
| 暂停全部 | `torrent-stop` | ids: 空数组=全部 |
| 恢复全部 | `torrent-start` | ids: 空数组=全部 |

#### 3.2.3 统一数据模型

```json
{
  "client": "qbittorrent",
  "stats": {
    "download_speed": 25165824,
    "upload_speed": 11141120,
    "active": 3,
    "seeding": 1,
    "paused": 1,
    "speed_limit": {
      "enabled": false,
      "download": 0,
      "upload": 0
    }
  },
  "torrents": [
    {
      "hash": "abc123...",
      "name": "Oppenheimer.2023.2160p.UHD.BluRay.x265",
      "size": 73543163904,
      "progress": 0.73,
      "download_speed": 15938355,
      "upload_speed": 2202009,
      "peers": 142,
      "seeds": 86,
      "eta": 1500,
      "state": "downloading",
      "category": "电影",
      "added_on": "2026-06-10T14:30:00Z",
      "ratio": 0.45
    }
  ]
}
```

#### 3.2.4 限速控制 API

```
POST /api/torrent/{client}/speed-limit
Body: { "download": 5120, "upload": 2048 }  // KB/s, 0=不限

POST /api/torrent/{client}/speed-limit/remove
```

#### 3.2.5 前端交互

- 顶部子标签切换 qB / TR，各自独立面板
- 每个面板：速度统计栏 + 限速状态 + 工具栏 + 任务列表
- 限速按钮弹出 Modal，可单独对 qB 或 TR 设置
- 任务卡片展示：名称、大小、进度条、速度、peers、ETA、状态标签
- 数据刷新间隔：5 秒（REST 轮询）

---

### 3.3 Tab3 - 影视推荐

#### 数据来源

| 来源 | 用途 | 接入方式 | 费用 |
|------|------|---------|------|
| TMDB API | 热门电影/剧集、评分、海报 | REST API (Key) | 免费 |
| 豆瓣 | 高分推荐、中文评分 | RSS + 爬虫备用 | 免费 |

#### TMDB API 使用

```
GET /3/trending/movie/week?api_key=xxx&language=zh-CN
GET /3/trending/tv/week?api_key=xxx&language=zh-CN
GET /3/movie/top_rated?api_key=xxx&language=zh-CN
```

#### 豆瓣数据获取

- 主要方式：豆瓣 RSS (`https://www.douban.com/feed/review/movie`)
- 备用方式：第三方豆瓣 API 或定期爬取豆瓣 Top250

#### 数据缓存

- 缓存策略：内存缓存 + 文件持久化
- 刷新频率：每 6 小时更新一次
- 缓存文件：`cache/movies.json`、`cache/tv.json`

#### 数据结构

```json
{
  "trending_movies": [
    {
      "id": 872585,
      "title": "奥本海默",
      "original_title": "Oppenheimer",
      "year": 2023,
      "rating": 8.9,
      "genres": ["剧情", "传记"],
      "poster_url": "https://image.tmdb.org/t/p/w300/xxx.jpg",
      "overview": "..."
    }
  ],
  "trending_tv": [...],
  "douban_top": [...]
}
```

#### 前端展示

- 横向滚动卡片列表
- 三个区域：热门电影 / 热门剧集 / 豆瓣高分
- 海报图 + 评分角标 + 标题 + 年份/类型
- 点击可展开详情（简介、演员等）

---

### 3.4 Tab4 - 新闻资讯

#### 数据来源 (RSS)

| 分类 | 来源 | RSS 地址 |
|------|------|---------|
| 科技 | 36氪 | `https://36kr.com/feed` |
| 科技 | Hacker News | `https://hnrss.org/frontpage` |
| 科技 | The Verge | `https://www.theverge.com/rss/index.xml` |
| 金融 | 华尔街见闻 | `https://wallstreetcn.com/rss` |
| 金融 | FT 中文网 | RSS Feed |
| 生活 | 澎湃新闻 | RSS Feed |
| 娱乐 | 豆瓣电影 | `https://www.douban.com/feed/review/movie` |
| 国际 | Reuters | `https://www.reutersagency.com/feed/` |
| 国际 | BBC 中文 | `https://feeds.bbci.co.uk/zhongwen/simp/rss.xml` |

#### 备选方案

如果 RSS 不稳定，可接入：
- **NewsAPI** (`newsapi.org`)：免费版每天 100 次请求，支持分类
- **GNews API** (`gnews.io`)：免费版每天 100 次请求

#### 数据缓存

- 刷新频率：每 30 分钟
- 缓存策略：按分类独立缓存
- 去重：按标题 hash 去重

#### 数据结构

```json
{
  "category": "科技",
  "items": [
    {
      "title": "OpenAI 发布 GPT-5...",
      "url": "https://...",
      "source": "36氪",
      "published": "2026-06-12T13:00:00Z",
      "summary": "...",
      "thumbnail": "https://..."
    }
  ]
}
```

#### 前端展示

- 顶部分类标签切换（全部/科技/金融/生活/娱乐/国际）
- 新闻卡片列表：缩略图 + 标题 + 来源 + 时间
- 点击跳转原文

---

## 4. API 设计总览

### 4.1 REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/system/info` | 获取系统基础信息（一次性） |
| WS | `/ws/system` | 实时系统监控数据流 |
| GET | `/api/torrent/qb/list` | qBittorrent 任务列表 |
| GET | `/api/torrent/qb/stats` | qBittorrent 全局统计 |
| POST | `/api/torrent/qb/speed-limit` | qB 设置限速 |
| POST | `/api/torrent/qb/speed-limit/remove` | qB 解除限速 |
| POST | `/api/torrent/qb/pause-all` | qB 暂停全部 |
| POST | `/api/torrent/qb/resume-all` | qB 恢复全部 |
| GET | `/api/torrent/tr/list` | Transmission 任务列表 |
| GET | `/api/torrent/tr/stats` | Transmission 全局统计 |
| POST | `/api/torrent/tr/speed-limit` | TR 设置限速 |
| POST | `/api/torrent/tr/speed-limit/remove` | TR 解除限速 |
| POST | `/api/torrent/tr/pause-all` | TR 暂停全部 |
| POST | `/api/torrent/tr/resume-all` | TR 恢复全部 |
| GET | `/api/movies/trending` | 热门影视列表 |
| GET | `/api/movies/douban` | 豆瓣推荐 |
| GET | `/api/news?category=tech` | 新闻列表（按分类） |

### 4.2 WebSocket

| 端点 | 用途 | 推送频率 |
|------|------|---------|
| `/ws/system` | 系统监控实时数据 | 2s |

---

## 5. 配置文件设计

```yaml
# config.yaml
server:
  host: 0.0.0.0
  port: 8900

qbittorrent:
  url: http://localhost:8080
  username: admin
  password: adminadmin

transmission:
  url: http://localhost:9091
  username: ""
  password: ""

tmdb:
  api_key: "your_tmdb_api_key"
  language: "zh-CN"
  proxy: "http://127.0.0.1:7890"  # HTTP 代理，留空则直连

news:
  refresh_interval: 1800  # 秒
  proxy: "http://127.0.0.1:7890"  # 国际源代理，留空则直连
  sources:
    tech:
      - name: "36氪"
        url: "https://36kr.com/feed"
      - name: "Hacker News"
        url: "https://hnrss.org/frontpage"
      - name: "The Verge"
        url: "https://www.theverge.com/rss/index.xml"
    finance:
      - name: "华尔街见闻"
        url: "https://wallstreetcn.com/rss"
    life:
      - name: "澎湃新闻"
        url: "https://www.thepaper.cn/rss"
    entertainment:
      - name: "豆瓣电影"
        url: "https://www.douban.com/feed/review/movie"
    international:
      - name: "BBC 中文"
        url: "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"
      - name: "Reuters"
        url: "https://www.reutersagency.com/feed/"

cache:
  movie_ttl: 21600   # 6小时
  news_ttl: 1800     # 30分钟
```

---

## 6. 技术依赖

### 6.1 Python 依赖

```txt
fastapi==0.111.0
uvicorn==0.30.0
websockets==12.0
psutil==5.9.8
httpx==0.27.0
pyyaml==6.0.1
feedparser==6.0.11
apscheduler==3.10.4
```

### 6.2 说明

| 包 | 用途 |
|----|------|
| fastapi + uvicorn | Web 框架 + ASGI 服务器 |
| websockets | WebSocket 实时推送 |
| psutil | 系统资源采集 |
| httpx | 异步 HTTP 客户端（调用 qB/TR/TMDB API） |
| pyyaml | 配置文件解析 |
| feedparser | RSS 解析 |
| apscheduler | 定时任务（刷新缓存） |

---

## 7. 部署方案

### 7.1 Docker 部署（推荐）

```yaml
# docker-compose.yml
version: "3.8"
services:
  nas-monitor:
    build: .
    ports:
      - "8900:8900"
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./cache:/app/cache
    restart: unless-stopped
    network_mode: host  # 需要访问本机 qB/TR 服务
```

### 7.2 直接运行

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8900
```

### 7.3 Systemd 服务

```ini
[Unit]
Description=NAS Monitor Dashboard
After=network.target

[Service]
Type=simple
User=nas
WorkingDirectory=/opt/nas-monitor
ExecStart=/opt/nas-monitor/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8900
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 8. 安全考虑

| 项目 | 措施 |
|------|------|
| 访问控制 | 仅监听局域网，可配置 Basic Auth |
| 敏感信息 | config.yaml 不入版本控制，密码不明文展示 |
| API 调用 | qB/TR 凭证仅后端持有，前端不直接访问 |
| CORS | 默认只允许同源请求 |

---

## 9. 开发计划

| 阶段 | 内容 | 预计耗时 |
|------|------|---------|
| Phase 1 | 后端框架 + 系统监控模块 + WebSocket | 1天 |
| Phase 2 | qBittorrent + Transmission 集成 | 1天 |
| Phase 3 | 影视推荐模块 (TMDB + 豆瓣) | 0.5天 |
| Phase 4 | 新闻资讯模块 (RSS 聚合) | 0.5天 |
| Phase 5 | 前端联调 + 响应式优化 | 1天 |
| Phase 6 | Docker 部署 + 测试 | 0.5天 |

---

## 10. 待确认事项

1. qBittorrent WebUI 地址和端口？（默认 `localhost:8080`）
2. Transmission RPC 地址和端口？（默认 `localhost:9091`）
3. TMDB API Key（需要去 themoviedb.org 免费注册）
4. 是否需要 Basic Auth 保护大盘访问？
5. 新闻源是否有其他偏好？
6. 是否需要移动端 PWA 支持（离线访问、桌面图标）？

---

## 11. Demo 预览

设计 Demo 文件：`doc/system-monitor-demo.html`

直接浏览器打开即可查看 UI 效果，包含模拟数据的四个 Tab 完整交互。
