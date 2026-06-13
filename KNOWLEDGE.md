# NAS Monitor 项目知识库

## 服务器信息

| 项目 | 值 |
|------|-----|
| NAS 地址 | 192.168.0.110 |
| SSH 用户 | winter |
| SSH 密码 | xue921130 |
| CPU | Intel(R) N100 (4核4线程) |
| 架构 | x86_64 |

## 服务凭证

| 服务 | 地址 | 用户名 | 密码 |
|------|------|--------|------|
| qBittorrent | http://192.168.0.110:8080 | winter | winter921130 |
| Transmission | http://192.168.0.110:9091 | winter | winter921130 |
| NAS Monitor | http://192.168.0.110:8900 | - | - |

## API Key

| 服务 | Key |
|------|-----|
| TMDB API | 0cbe71a76ac796db842ab7e8c1cc085c |
| 豆瓣 Frodo API Key | 0dad551ec0f84ed02907ff5c42e8ec70 |

## 技术栈

- 后端: Python 3.9+ / FastAPI / uvicorn
- 前端: 纯 HTML/CSS/JS（暗色主题、响应式）
- 部署: systemd 服务 / Docker Compose
- 端口: 8900

## 功能模块

1. **系统监控** — CPU/内存/磁盘/网络实时图表（WebSocket 2s 推送）
2. **种子任务** — qBittorrent + Transmission 统一管理、限速调度
3. **影视推荐** — TMDB 热门 + 豆瓣高分（6h 缓存）
4. **新闻资讯** — RSS 聚合（6 个分类，30min 刷新）

## 限速规则

| 时间段 | 下载 | 上传 |
|--------|------|------|
| 08:00-23:00 | 5120 KB/s | 2048 KB/s |
| 23:00-08:00 | 不限 | 不限 |

手动限速解除后有 180 分钟冷却期（不参与调度）。

## 部署方式

### Docker
```bash
docker-compose up -d
```

### systemd
```bash
cp nas-monitor.service /etc/systemd/system/
systemctl enable --now nas-monitor
```

### 直接运行
```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8900
```

## 目录结构

```
system-monitor/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 加载 config.yaml
│   ├── routers/             # API 路由
│   │   ├── system.py        # 系统监控 + WebSocket
│   │   ├── torrent.py       # BT 下载管理
│   │   ├── movie.py         # 影视推荐
│   │   └── news.py          # 新闻资讯
│   ├── services/            # 业务逻辑
│   │   ├── system_service.py     # psutil 采集
│   │   ├── qbittorrent_service.py
│   │   ├── transmission_service.py
│   │   ├── speed_scheduler.py    # 限速调度
│   │   ├── tmdb_service.py       # TMDB API
│   │   ├── douban_service.py     # 豆瓣 API
│   │   └── news_service.py       # RSS 聚合
│   └── static/
│       └── index.html       # 前端单页
├── config.yaml              # 用户配置（不入 git）
├── cache/                   # 缓存目录（不入 git）
├── docker-compose.yml
├── Dockerfile
├── nas-monitor.service      # systemd 服务
├── nas-monitor.bat          # Windows 启动脚本
├── nas-monitor.log          # 运行日志
└── requirements.txt
```
