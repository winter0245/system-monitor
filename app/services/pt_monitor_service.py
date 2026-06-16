"""
PT 站点 Playwright 监控 Service
- 用 Playwright 无头浏览器模拟真实用户访问
- 从页面解析上传量、下载量、做种积分、魔力值等
- 支持模拟浏览行为（随机点击页面链接）
"""

import asyncio
import logging
import random
import re
from typing import Optional, Tuple
from datetime import datetime

from app.services.pt_site_service import db

logger = logging.getLogger(__name__)

# 解析策略：每个站点页面结构不同，定义解析规则
# 规则格式：(指标名, 正则表达式列表, 单位换算)
# 数据解析会尝试多个正则，取第一个匹配成功的


def _parse_bytes(text: str) -> int:
    """将 '12.8 TB'、'86.2 GB'、'500 MB' 等转换为字节"""
    if not text:
        return 0
    text = text.strip().upper().replace(",", "")
    match = re.match(r"([\d.]+)\s*(TB|GB|MB|KB|B|TIB|GIB|MIB|KIB)", text)
    if not match:
        # 尝试纯数字
        try:
            return int(float(text))
        except ValueError:
            return 0
    value = float(match.group(1))
    unit = match.group(2)
    multipliers = {
        "B": 1, "KB": 1024, "KIB": 1024,
        "MB": 1024 ** 2, "MIB": 1024 ** 2,
        "GB": 1024 ** 3, "GIB": 1024 ** 3,
        "TB": 1024 ** 4, "TIB": 1024 ** 4,
    }
    return int(value * multipliers.get(unit, 1))


def _parse_number(text: str) -> float:
    """从文本中提取数字，支持 K (千) / M (百万) / B (十亿) 后缀"""
    if not text:
        return 0
    text = text.strip().replace(",", "").replace(" ", "").upper()
    # 处理后缀
    multiplier = 1
    if text.endswith("K"):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
    match = re.search(r"[\d.]+", text)
    return float(match.group()) * multiplier if match else 0


# 通用的数据提取模式
# 优先匹配紧凑格式（NexusPHP风格: "上传量: 4.509 TB 下载量: 640.81 GB 分享率: 7.205"）
DATA_PATTERNS = {
    "upload": [
        r"上传量\s*[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))",
        r"上传[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))",
        r"Uploaded[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))",
    ],
    "download": [
        r"下载量\s*[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))",
        r"下载[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))",
        r"Downloaded[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))",
    ],
    "share_ratio": [
        r"分享率\s*[：:]\s*([\d.,]+)",
        r"Ratio[：:]\s*([\d.,]+)",
    ],
    "seed_points": [
        r"做种积分\s*[：:]\s*([\d.,]+\s*K?)",
        r"种子积分[：:]\s*([\d.,]+\s*K?)",
        r"Seed\s*Points?[：:]\s*([\d.,]+\s*K?)",
    ],
    "bonus_points": [
        r"茉莉[：:]\s*([\d.,]+\s*K?)",
        r"魔力值[：:]\s*([\d.,]+\s*K?)",
        r"鲸币[^：:]*[：:]\s*([\d.,]+\s*K?)",
        r"Bonus[：:]\s*([\d.,]+\s*K?)",
        r"猫粮[：:]\s*([\d.,]+\s*K?)",
        r"银币[：:]\s*([\d.,]+\s*K?)",
        r"金币[：:]\s*([\d.,]+\s*K?)",
        r"积分\s*[：:]\s*([\d.,]+\s*K?)",
    ],
    "seeding_count": [
        r"当前活动\s*[：:]\s*(\d+)\s+\d+",
        r"做种活动\s*[：:]\s*(\d+)\s+\d+",
        r"做种数[：:]\s*(\d+)",
        r"做种[：:]\s*(\d+)",
        r"当前做种\s*[：:]\s*(\d+)",
        r"Seeding[：:]\s*(\d+)",
    ],
    "leeching_count": [
        r"当前活动\s*[：:]\s*\d+\s+(\d+)",
        r"做种活动\s*[：:]\s*\d+\s+(\d+)",
        r"下载数[：:]\s*(\d+)",
        r"下载中[：:]\s*(\d+)",
        r"当前下载\s*[：:]\s*(\d+)",
        r"Leeching[：:]\s*(\d+)",
    ],
}


def parse_page_data(page_text: str) -> dict:
    """从页面文本中解析 PT 数据"""
    result = {
        "upload_bytes": 0,
        "download_bytes": 0,
        "share_ratio": 0.0,
        "seed_points": 0.0,
        "bonus_points": 0.0,
        "seeding_count": 0,
        "leeching_count": 0,
        "raw_data": {},
    }

    # 移除多余空白，方便正则匹配
    text = re.sub(r"\s+", " ", page_text)

    # 先尝试 NexusPHP 紧凑格式（无标签，如 audiences.me）
    # 格式: {ratio} {upload TB/GB} {download TB/GB} {bonus} {seed_points} ↑ {seeding} / ↓ {leeching}
    nexus_match = re.search(
        r"([\d.]+)\s+([\d.,]+\s*(?:TB|GB|MB))\s+([\d.,]+\s*(?:TB|GB|MB))\s+([\d.,]+)\s+([\d.,]+)\s*↑\s*([\d,]+)\s*/\s*↓\s*([\d,]+)",
        text,
    )
    if nexus_match:
        result["share_ratio"] = float(nexus_match.group(1))
        result["upload_bytes"] = _parse_bytes(nexus_match.group(2))
        result["download_bytes"] = _parse_bytes(nexus_match.group(3))
        result["bonus_points"] = _parse_number(nexus_match.group(4))
        result["seed_points"] = _parse_number(nexus_match.group(5))
        result["seeding_count"] = int(nexus_match.group(6).replace(",", ""))
        result["leeching_count"] = int(nexus_match.group(7).replace(",", ""))
        result["raw_data"] = {
            "share_ratio": nexus_match.group(1),
            "upload": nexus_match.group(2),
            "download": nexus_match.group(3),
            "bonus_points": nexus_match.group(4),
            "seed_points": nexus_match.group(5),
            "seeding_count": nexus_match.group(6),
            "leeching_count": nexus_match.group(7),
            "format": "nexusphp_compact",
        }
        return result

    # 回退到带标签的通用格式
    # bonus_points 优先匹配具体名称（茉莉/魔力值/鲸币），seed_points 匹配通用"积分"
    # 先做 bonus — 因为 bonus 的关键词更具体，不会和种子积分混淆
    for pattern in DATA_PATTERNS["bonus_points"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            result["bonus_points"] = _parse_number(value)
            result["raw_data"]["bonus_points"] = value
            break

    for key, patterns in DATA_PATTERNS.items():
        if key == "bonus_points":
            continue  # 已处理
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if key in ("upload", "download"):
                    result[f"{key}_bytes"] = _parse_bytes(value)
                elif key in ("share_ratio", "seed_points"):
                    result[key] = _parse_number(value)
                elif key in ("seeding_count", "leeching_count"):
                    result[key] = int(_parse_number(value))
                result["raw_data"][key] = value
                break

    return result


async def monitor_site(site: dict, simulate_browsing: bool = True) -> dict:
    """
    用 Playwright 模拟访问一个 PT 站点，解析数据。
    返回: { success, site_id, data, message }
    """
    site_id = site["id"]
    site_name = site["name"]
    url = site["url"]
    cookie_str = site.get("cookie", "")

    if not url:
        return {"success": False, "site_id": site_id, "data": None, "message": "站点 URL 为空"}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("[PT] playwright 未安装，请执行: pip install playwright && playwright install chromium")
        return {"success": False, "site_id": site_id, "data": None, "message": "Playwright 未安装"}

    result = {"success": False, "site_id": site_id, "data": None, "message": ""}

    async with async_playwright() as p:
        # 使用 Chromium，设置常见反检测参数
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
            ],
        )

        # 随机 User-Agent（如果没有自定义则随机选一个）
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        ]
        user_agent = site.get("user_agent") or random.choice(ua_list)

        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            bypass_csp=True,
            # 模拟真实浏览器的 HTTP 头
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "sec-ch-ua": '"Chromium";v="132", "Not)A;Brand";v="99"',
                "sec-ch-ua-arch": '"x86"',
                "sec-ch-ua-bitness": '"64"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "Upgrade-Insecure-Requests": "1",
                "Referer": site["url"].rsplit("/", 1)[0] + "/login.php",
            },
        )

        # 如果配置了 cookie，注入 cookie
        if cookie_str:
            cookies = _parse_cookie_string(cookie_str, url)
            if cookies:
                await context.add_cookies(cookies)

        page = await context.new_page()

        # 隐藏 webdriver 属性 — 反自动化检测
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            window.chrome = { runtime: {} };
            // 伪造成常见屏幕分辨率
            Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
            Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
            // 移除 PhantomJS / Headless Chrome 痕迹
            delete navigator.__proto__.webdriver;
            // CF 检测
            if (navigator.userAgent.includes('Headless')) {
                Object.defineProperty(navigator, 'userAgent', { get: () => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36' });
            }
        """)

        try:
            logger.info(f"[PT] 开始访问 {site_name} ({url})")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 检测 Cloudflare / WAF 挑战页面
            await _handle_waf_challenge(page, site_name)

            # 等待页面加载完成
            await asyncio.sleep(random.uniform(2, 4))

            # 模拟浏览行为
            if simulate_browsing:
                await _simulate_browsing(page)

            # 获取页面文本内容用于解析
            page_text = await page.evaluate("() => document.body.innerText")
            # 也获取 title 用于辅助判断
            page_title = await page.title()

            # 解析数据
            parsed = parse_page_data(page_text)
            parsed["raw_data"]["page_title"] = page_title
            parsed["raw_data"]["url"] = page.url  # 记录实际跳转后的 URL

            logger.info(f"[PT] {site_name} 解析完成: upload={parsed['upload_bytes']}, download={parsed['download_bytes']}, ratio={parsed['share_ratio']}")

            result["success"] = True
            result["data"] = parsed
            result["message"] = "访问成功"

        except Exception as e:
            error_msg = str(e)[:200]
            logger.warning(f"[PT] {site_name} 访问失败: {error_msg}")
            result["success"] = False
            result["message"] = error_msg

        finally:
            await browser.close()

    return result


async def _handle_waf_challenge(page, site_name: str):
    """
    检测并处理 Cloudflare / WAF 盾
    - CF 的 JavaScript 挑战页面会自动在浏览器中执行并通过
    - CF Turnstile / hCaptcha 需要手动处理
    - 等待最多 15 秒让挑战自动完成
    """
    try:
        # 等待一下让可能的 JS 挑战执行
        await asyncio.sleep(2)

        title = await page.title()

        # Cloudflare "Just a moment..." 或 "Checking your browser"
        if "just a moment" in title.lower() or "checking" in title.lower():
            logger.info(f"[PT] {site_name} 遇到 Cloudflare 挑战，等待自动通过...")
            # CF JS 挑战通常 5 秒内自动通过
            try:
                await page.wait_for_function(
                    """() => {
                        const title = document.title.toLowerCase();
                        return !title.includes('just a moment') && !title.includes('checking');
                    }""",
                    timeout=15000,
                )
                logger.info(f"[PT] {site_name} Cloudflare 挑战已通过")
            except Exception:
                logger.warning(f"[PT] {site_name} Cloudflare 挑战等待超时，尝试继续...")

        # 检测 Turnstile / hCaptcha（需要人工）
        has_captcha = await page.evaluate("""
            () => {
                return !!document.querySelector('.cf-turnstile, iframe[src*="hcaptcha"], iframe[src*="recaptcha"], .challenge-form');
            }
        """)
        if has_captcha:
            logger.warning(f"[PT] {site_name} 检测到验证码 (Turnstile/hCaptcha)，无法自动通过")

    except Exception as e:
        logger.debug(f"[PT] WAF 检测出错: {e}")


async def _simulate_browsing(page, max_clicks: int = 3):
    """
    模拟浏览行为：
    - 随机滚动页面
    - 随机点击几个页面内链接
    让行为看起来更像真实用户，提升保号效果
    """
    try:
        # 1. 随机滚动
        for _ in range(random.randint(2, 5)):
            scroll_y = random.randint(200, 800)
            await page.evaluate(f"window.scrollBy(0, {scroll_y})")
            await asyncio.sleep(random.uniform(0.5, 1.5))

        # 2. 随机点击站内链接（避免跳离站点）
        links = await page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a[href]');
                const results = [];
                anchors.forEach(a => {
                    const href = a.getAttribute('href');
                    // 过滤掉外部链接、javascript、#锚点
                    if (href && !href.startsWith('javascript') && !href.startsWith('#') &&
                        !href.startsWith('http') && href !== '/') {
                        results.push(href);
                    }
                });
                return results;
            }
        """)

        if links:
            click_count = min(random.randint(1, max_clicks), len(links))
            for _ in range(click_count):
                link = random.choice(links)
                try:
                    await page.click(f'a[href="{link}"]', timeout=5000)
                    await asyncio.sleep(random.uniform(1, 3))
                    # 回退
                    await page.go_back(timeout=5000)
                    await asyncio.sleep(random.uniform(0.5, 1))
                except Exception:
                    pass  # 点击/回退失败忽略，不影响主流程
    except Exception as e:
        logger.debug(f"[PT] 模拟浏览出错: {e}")


def _parse_cookie_string(cookie_str: str, url: str) -> list:
    """解析 cookie 字符串为 Playwright 格式"""
    cookies = []
    domain = ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.split(":")[0] if parsed.netloc else ""
    except Exception:
        pass

    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip()
        value = value.strip()
        if key and value:
            cookie = {
                "name": key,
                "value": value,
                "domain": domain,
                "path": "/",
            }
            cookies.append(cookie)
    return cookies
