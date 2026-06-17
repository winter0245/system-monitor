"""
PT 站点 Playwright 监控 Service
"""

import asyncio
import logging
import random
import re
from typing import Optional, Tuple
from datetime import datetime
from urllib.parse import urlparse

from app.config import config
from app.services.pt_site_service import db

logger = logging.getLogger(__name__)


def _parse_bytes(text: str) -> int:
    """将 '12.8 TB'、'86.2 GB'、'500 MB' 等转换为字节"""
    if not text:
        return 0
    text = text.strip().upper().replace(",", "")
    match = re.match(r"([\d.]+)\s*(TB|GB|MB|KB|B|TIB|GIB|MIB|KIB)", text)
    if not match:
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


# 通用标签式正则（对大部分 NexusPHP 站有效）
DEFAULT_PATTERNS = {
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
        r"魔力值\s*(?:\[[^\]]*\])?\s*[：:]\s*([\d.,]+)",
        r"魔力值[：:]\s*([\d.,]+\s*K?)",
        r"鲸币[^：:]*[：:]\s*([\d.,]+\s*K?)",
        r"Bonus[：:]\s*([\d.,]+\s*K?)",
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
        r"\|\s*(\d+)\s+\d+",
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

FIELD_KEYS = ["upload", "download", "share_ratio", "seed_points", "bonus_points", "seeding_count", "leeching_count"]


# ========== 站点解析规则（硬编码，按域名前缀匹配） ==========

def _parse_audiences_me(text: str) -> Optional[dict]:
    """audiences.me — NexusPHP 紧凑格式，无标签"""
    m = re.search(
        r"([\d.]+)\s+([\d.,]+\s*(?:TB|GB|MB))\s+([\d.,]+\s*(?:TB|GB|MB))\s+([\d.,]+)\s+([\d.,]+)\s*↑\s*([\d,]+)\s*/\s*↓\s*([\d,]+)",
        text,
    )
    if not m:
        return None
    return {
        "upload_bytes": _parse_bytes(m.group(2)),
        "download_bytes": _parse_bytes(m.group(3)),
        "share_ratio": float(m.group(1)),
        "bonus_points": _parse_number(m.group(4)),
        "seed_points": _parse_number(m.group(5)),
        "seeding_count": int(m.group(6).replace(",", "")),
        "leeching_count": int(m.group(7).replace(",", "")),
    }


def _parse_keepfrds(text: str) -> Optional[dict]:
    """pt.keepfrds.com — 魔力值带 [使用] 按钮，做种数用 | x y 格式"""
    # 上传/下载/分享率用通用正则，仅覆盖魔力值和做种数
    bonus_match = re.search(r"魔力值\s*(?:\[[^\]]*\])?\s*[：:]\s*([\d.,]+)", text)
    seed_match = re.search(r"\|\s*(\d+)\s+\d+", text)
    if not bonus_match and not seed_match:
        return None
    return {
        "bonus_points": _parse_number(bonus_match.group(1)) if bonus_match else 0,
        "seeding_count": int(seed_match.group(1)) if seed_match else 0,
    }


def _parse_pterclub(text: str) -> Optional[dict]:
    """pterclub.net (猫站) — 积分叫"猫粮"而非"魔力值"，做种/下载格式为 Torrents seeding X Torrents leeching Y"""
    bonus_match = re.search(r"猫粮.*?[：:]\s*([\d.,]+)", text)
    seed_match = re.search(r"Torrents?\s*seeding\s*(\d+)", text, re.IGNORECASE)
    leech_match = re.search(r"Torrents?\s*leeching\s*(\d+)", text, re.IGNORECASE)
    if not bonus_match and not seed_match:
        return None
    return {
        "bonus_points": _parse_number(bonus_match.group(1)) if bonus_match else 0,
        "seeding_count": int(seed_match.group(1)) if seed_match else 0,
        "leeching_count": int(leech_match.group(1)) if leech_match else 0,
    }


def _parse_hhclub(text: str) -> Optional[dict]:
    """HHCLUB (憨憨) — 首页数据不全，需跳转个人中心；积分叫"憨豆" """
    bonus_match = re.search(r"憨豆[：:]\s*([\d.,]+)", text)
    seed_points_match = re.search(r"做种积分[：:]\s*([\d.,]+)", text)
    seed_match = re.search(r"做种数\s*(\d+)", text)
    leech_match = re.search(r"下载数\s*(\d+)", text)
    return {
        "bonus_points": _parse_number(bonus_match.group(1)) if bonus_match else 0,
        "seed_points": _parse_number(seed_points_match.group(1)) if seed_points_match else 0,
        "seeding_count": int(seed_match.group(1)) if seed_match else 0,
        "leeching_count": int(leech_match.group(1)) if leech_match else 0,
    }


# 域名前缀 -> 解析函数
_SITE_PARSERS = [
    ("audiences.me", _parse_audiences_me),
    ("pt.keepfrds.com", _parse_keepfrds),
    ("pterclub.net", _parse_pterclub),
    ("hhanclub", _parse_hhclub),
]

# 需要跳转到个人中心再解析的站点：域名前缀 -> (查找链接的选择器, 备用 href 正则)
_NAVIGATE_TO_USER = {
    "hhanclub": (r'个人中心', r'userdetails\.php\?id=\d+'),
}


def _get_domain(url: str) -> str:
    """从 URL 提取域名"""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _get_site_parser(url: str):
    """根据站点 URL 返回专属解析函数"""
    domain = _get_domain(url)
    for prefix, parser in _SITE_PARSERS:
        if prefix in domain:
            return parser
    return None


def _parse_default(text: str) -> dict:
    """默认标签式解析"""
    result = {
        "upload_bytes": 0, "download_bytes": 0, "share_ratio": 0.0,
        "seed_points": 0.0, "bonus_points": 0.0,
        "seeding_count": 0, "leeching_count": 0,
    }

    # bonus_points 优先
    for pattern in DEFAULT_PATTERNS["bonus_points"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["bonus_points"] = _parse_number(match.group(1))
            break

    for key in FIELD_KEYS:
        if key == "bonus_points":
            continue
        for pattern in DEFAULT_PATTERNS[key]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if key in ("upload", "download"):
                    result[f"{key}_bytes"] = _parse_bytes(value)
                elif key in ("share_ratio", "seed_points"):
                    result[key] = _parse_number(value)
                elif key in ("seeding_count", "leeching_count"):
                    result[key] = int(_parse_number(value))
                break

    return result


def parse_page_data(page_text: str, site_url: str = "") -> dict:
    """从页面文本中解析 PT 数据，根据 URL 域名选择解析器"""
    text = re.sub(r"\s+", " ", page_text)

    # 1. 检查是否有域名专属解析器
    parser = _get_site_parser(site_url) if site_url else None
    if parser:
        parsed = parser(text)
        if parsed:
            # 专属解析器可能只返回部分字段，用默认解析补全
            defaults = _parse_default(text)
            defaults.update(parsed)
            return {**defaults, "raw_data": {"site_parser": parser.__name__}}

    # 2. 兜底：默认标签式
    return {**_parse_default(text), "raw_data": {}}



async def _navigate_to_user_center(page, site_name: str, link_text: str, href_pattern: str):
    """
    在页面中查找"个人中心"链接并点击跳转，等待页面加载后返回。
    """
    # 方法1：按链接文本查找（innerText 包含指定文字）
    try:
        link = page.locator(f'a:has-text("{link_text}")').first
        if await link.count() > 0:
            logger.info(f"[PT] {site_name} 点击「{link_text}」跳转到个人中心...")
            await link.click(timeout=5000)
            await asyncio.sleep(random.uniform(2, 4))
            return
    except Exception:
        pass

    # 方法2：按 href 正则查找
    try:
        links = await page.evaluate(f"""
            () => {{
                const anchors = document.querySelectorAll('a[href]');
                for (const a of anchors) {{
                    if (/{href_pattern}/.test(a.getAttribute('href'))) {{
                        return a.getAttribute('href');
                    }}
                }}
                return null;
            }}
        """)
        if links:
            logger.info(f"[PT] {site_name} 跳转到 {links} ...")
            await page.goto(links, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(random.uniform(2, 4))
            return
    except Exception:
        pass

    logger.warning(f"[PT] {site_name} 未找到个人中心链接")


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

            # 某些站点首页数据不全，需要跳转到个人中心
            domain = _get_domain(site["url"])
            for prefix, (link_text, _href_pattern) in _NAVIGATE_TO_USER.items():
                if prefix in domain:
                    try:
                        await _navigate_to_user_center(page, site_name, link_text, _href_pattern)
                    except Exception as e:
                        logger.warning(f"[PT] {site_name} 跳转个人中心失败: {e}，使用首页数据")
                    break

            # 获取页面文本内容用于解析
            page_text = await page.evaluate("() => document.body.innerText")
            # 也获取 title 用于辅助判断
            page_title = await page.title()

            # 解析数据
            parsed = parse_page_data(page_text, site["url"])
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
