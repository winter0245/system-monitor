# RSS 新闻源调试记录

> 调试时间：2026-06-12

## 调试结果

### 可用源

| 源 | URL | 条数 | 状态 |
|---|---|---|---|
| 36氪 | `https://36kr.com/feed` | 30 | ✅ 稳定 |
| 虎嗅 | `https://rss.huxiu.com/` | 123 | ✅ 稳定，量大 |
| IT之家 | `https://www.ithome.com/rss/` | 60 | ✅ 稳定 |
| 少数派 | `https://sspai.com/feed` | 10 | ✅ 稳定，量少 |
| Hacker News | `https://hnrss.org/frontpage` | 待测 | 需代理 |

### 不可用源

| 源 | URL | 原因 |
|---|---|---|
| 极客公园 | `https://www.geekpark.net/rss` | 服务器断开连接，RSS 已废弃 |
| 极客公园(RSSHub) | `https://rsshub.app/geekpark/breakingnews` | Cloudflare 403 拦截 |

## 待测源（需代理或进一步验证）

| 分类 | 源 | URL | 说明 |
|---|---|---|---|
| 金融 | 华尔街见闻 | `https://plink.anyfeeder.com/weixin/wallstreetcn` | anyfeeder 代理 |
| 金融 | 华尔街日报 | `https://plink.anyfeeder.com/wsj/cn` | anyfeeder 代理 |
| 国际 | BBC中文 | `https://plink.anyfeeder.com/bbc/cn` | anyfeeder 代理 |
| 国际 | 路透中文 | `https://plink.anyfeeder.com/reuters/cn` | anyfeeder 代理 |
| 国际 | 联合早报 | `https://plink.anyfeeder.com/zaobao/realtime/china` | anyfeeder 代理 |
| 生活 | 知乎热榜 | `https://rsshub.app/zhihu/hotlist` | RSSHub，可能被拦截 |
| 开发 | 阮一峰 | `https://www.ruanyifeng.com/blog/atom.xml` | 待测 |
| 开发 | 掘金前端 | `https://rsshub.app/juejin/category/frontend` | RSSHub |

## 参考来源

掘金文章：[订阅人数最多的中文RSS源推荐](https://juejin.cn/post/7459966392429101067)

完整源列表见文章内容，已提取关键源到 `config.yaml` 中。

## 备注

- `plink.anyfeeder.com` 是一个 RSS 代理服务，可以获取微信公众号等无原生 RSS 的源
- `rsshub.app` 公共实例容易被 Cloudflare 拦截，生产环境建议自建 RSSHub
- 极客公园 RSS 已完全不可用，已从配置中移除
