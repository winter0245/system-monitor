# NAS Monitor

一个轻量级的 NAS 综合监控面板，提供系统资源监控、下载客户端管理、影视推荐、新闻聚合和 PT 站点数据追踪功能。

## 功能概览

### 系统监控
- CPU 使用率、型号、核心数实时显示
- 内存使用情况（已用 / 总量）
- 磁盘分区使用率及空间详情
- 网络实时流量图表（SVG 绘制，WebSocket 推送，2 秒刷新）
- 系统运行时间、操作系统信息

### 种子任务管理
- 同时支持 **qBittorrent** 和 **Transmission** 两种下载客户端
- 种子列表展示（名称、进度、速度、做种/下载数、ETA 等）
- 按活跃/全部筛选，支持关键词搜索
- 限速管理：手动限速（支持定时自动解除）、解除限速
- 一键暂停/恢复全部种子
- 定时限速调度：按时间段自动切换限速规则（如白天不限速、晚间限速）

### 影视推荐
- **TMDB** 热门电影、热门剧集、高分电影
- **豆瓣** 热门电影、热门剧集、正在上映
- 海报展示，评分信息，支持点击跳转豆瓣详情页
- 图片代理解决豆瓣 CDN 防盗链问题

### 新闻聚合
- 多源 RSS 订阅，支持分类浏览（科技、财经、生活、娱乐、国际、开发）
- 按来源筛选
- 定时后台刷新，手动刷新
- 文件缓存，减少重复请求

### PT 站点管理
- 站点配置（URL、Cookie、访问频率/时间）
- 使用 **Playwright** 模拟浏览器访问，自动解析上传量、下载量、分享率、魔力值、做种积分、做种数等数据
- 支持多种 NexusPHP 站点及定制解析规则（Audiences、KeepFRDS、PterClub、HHCLUB 等）
- 定时自动访问 + 手动触发，每日随机偏移模拟真人习惯
- 数据快照存储，支持查看今日变化量（增量）
- 用户链接跳转记录，辅助 PT 站保号
- 访问日志（Playwright 访问 / 链接跳转分开展示）
- 站点状态监控（正常 / 超时未更新）

## 技术栈

| 层面 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python) |
| 前端 | 原生 HTML/CSS/JS，单页应用，响应式布局 |
| 实时通信 | WebSocket |
| 数据存储 | SQLite（PT 站点数据） |
| 浏览器自动化 | Playwright |
| 系统信息采集 | psutil |
| HTTP 客户端 | httpx |
| RSS 解析 | feedparser |
| 配置管理 | YAML |

## 项目结构

```
system-monitor/
├── app/
│   ├── main.py                  # FastAPI 入口，路由注册，后台任务
│   ├── config.py                # 配置文件加载
│   ├── routers/
│   │   ├── system.py            # 系统监控 API + WebSocket
│   │   ├── torrent.py           # 种子客户端管理 API
│   │   ├── movie.py             # TMDB / 豆瓣影视 API + 图片代理
│   │   ├── news.py              # 新闻聚合 API
│   │   └── pt_site.py           # PT 站点管理 API
│   ├── services/
│   │   ├── system_service.py    # 系统信息采集、网络速率追踪
│   │   ├── qbittorrent_service.py   # qBittorrent API 封装
│   │   ├── transmission_service.py  # Transmission RPC 封装
│   │   ├── speed_scheduler.py   # 限速调度引擎
│   │   ├── tmdb_service.py      # TMDB API 封装
│   │   ├── douban_service.py    # 豆瓣 API 封装（含签名）
│   │   ├── news_service.py      # RSS 新闻抓取与缓存
│   │   ├── pt_monitor_service.py    # Playwright 站点访问与数据解析
│   │   ├── pt_site_service.py   # SQLite 数据库管理（站点/快照/日志）
│   │   └── pt_scheduler.py      # PT 站点定时调度
│   └── static/
│       └── index.html           # 前端单页应用
├── config_example.yaml          # 配置模板
├── requirements.txt             # Python 依赖
├── data/                        # SQLite 数据库目录（自动创建）
├── cache/                       # 缓存目录（自动创建）
└── .gitignore
```

## 快速开始

### 1. 环境要求

- Python 3.9+
- 操作系统：Windows / Linux / macOS

### 2. 安装依赖

```bash
pip install -r requirements.txt --break-system-packages
```

安装 Playwright 浏览器：

```bash
playwright install chromium
```

### 3. 配置

复制配置模板并编辑：

```bash
cp config_example.yaml config.yaml
```

编辑 `config.yaml`，至少需要配置以下内容：

- **qBittorrent / Transmission**：下载客户端连接信息
- **TMDB API Key**：在 [TMDB 设置页](https://www.themoviedb.org/settings/api) 免费申请
- **PT 站点**：通过 Web 界面添加（Cookie 等信息存储在 SQLite 中）

可选配置：

- `speed_limit.schedule`：时间段限速规则
- `news.sources`：自定义 RSS 新闻源
- `pt.visit_schedule`：PT 站点访问频率对应的时间点

### 4. 启动

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8900
```

或者直接运行：

```bash
python -m app.main
```

启动后访问 `http://localhost:8900` 即可打开监控面板。

### 5. 配置 PT 站点

PT 站点的 Cookie 等敏感信息不在 `config.yaml` 中，而是通过 Web 界面的「PT 管理」标签页进行添加和管理，数据存储在本地 SQLite 数据库中。

在 PT 管理页面点击「添加站点」，填写：
- 站点 ID（英文标识，如 `mteam`）
- 站点名称
- 站点首页 URL
- Cookie（从浏览器开发者工具中复制）
- 访问频率（1-4 次/天）或自定义时间

## 配置说明

### 限速调度

```yaml
speed_limit:
  remove_cooldown: 180  # 手动解除限速后的冷却时间（分钟），期间不参与调度
  schedule:
    - name: "白天不限速"
      start: "00:00"
      end: "11:30"
      download: 0   # 0 = 不限速，单位 KB/s
      upload: 0
    - name: "午间限速"
      start: "11:30"
      end: "13:30"
      download: 512000
      upload: 512
```

规则按顺序匹配，支持跨午夜时间段（如 `start: "23:00"`, `end: "08:00"`）。手动限速优先级高于定时规则。

### PT 访问调度

每个站点可配置每天 1-4 次访问，或自定义时间列表。系统会在每个时间点前后随机偏移（基于日期+站点+时间点的 MD5 哈希），模拟真人访问习惯，降低被检测风险。

```yaml
pt:
  visit_schedule:
    2:  # 每天 2 次
      - time: "09:00"
        window: 45  # 在 08:15-09:45 之间随机执行
      - time: "21:00"
        window: 45
```

## API 概览

| 路由 | 说明 |
|------|------|
| `GET /api/system/info` | 系统基本信息 |
| `GET /api/system/stats` | 系统实时状态（CPU/内存/网络/磁盘） |
| `WS /api/system/ws` | WebSocket 实时推送（2 秒间隔） |
| `GET /api/torrent/qb/list` | qBittorrent 种子列表 |
| `GET /api/torrent/tr/list` | Transmission 种子列表 |
| `POST /api/torrent/{client}/speed-limit` | 设置限速 |
| `POST /api/torrent/{client}/speed-limit/remove` | 解除限速 |
| `GET /api/torrent/speed-schedule` | 查看限速调度状态 |
| `GET /api/movies/trending` | TMDB 热门影视 |
| `GET /api/movies/douban/movie-hot` | 豆瓣热门电影 |
| `GET /api/movies/img-proxy` | 图片代理 |
| `GET /api/news` | 获取新闻 |
| `POST /api/news/refresh` | 手动刷新新闻 |
| `GET /api/pt/sites` | PT 站点列表 |
| `POST /api/pt/sites` | 添加 PT 站点 |
| `POST /api/pt/scan` | 手动触发扫描 |
| `GET /api/pt/schedule` | 查看调度信息 |
| `GET /api/pt/logs` | 访问日志 |

## License

MIT
