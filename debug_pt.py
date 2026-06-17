"""
调试脚本：用 httpx 抓取 PT 站点页面，分析解析效果
用法: python3 debug_pt.py [站点ID，默认SSD]
"""
import sqlite3
import httpx
import asyncio
import re
import sys

import os
DB_PATH = os.environ.get("PT_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pt_sites.db"))


def load_site(site_id: str) -> dict:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM pt_sites WHERE id=?", (site_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def parse_cookies(cookie_str: str) -> dict:
    cookies = {}
    if cookie_str:
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookies[k.strip()] = v.strip()
    return cookies


async def debug_site(site_id: str):
    site = load_site(site_id)
    if not site:
        print(f"站点 {site_id} 不存在")
        return

    cookies = parse_cookies(site.get("cookie", ""))
    print(f"=== {site['name']} ({site['id']}) ===")
    print(f"URL: {site['url']}")
    print(f"Cookie keys: {list(cookies.keys())}")
    print()

    try:
        async with httpx.AsyncClient(
            cookies=cookies, timeout=30, follow_redirects=True, verify=False
        ) as client:
            resp = await client.get(
                site["url"],
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            print(f"Status: {resp.status_code}")
            print(f"Final URL: {resp.url}")

            # Title
            tm = re.search(r"<title[^>]*>(.+?)</title>", resp.text, re.I | re.S)
            print(f"Title: {tm.group(1).strip() if tm else 'N/A'}")

            # 去掉 script / style
            clean = re.sub(
                r"<script[^>]*>.*?</script>", " ", resp.text, flags=re.I | re.S
            )
            clean = re.sub(
                r"<style[^>]*>.*?</style>", " ", clean, flags=re.I | re.S
            )
            clean = re.sub(r"<[^>]+>", " ", clean)
            clean = re.sub(r"&nbsp;", " ", clean)
            clean = re.sub(r"\s+", " ", clean).strip()

            # 数据解析 — 使用与 pt_monitor_service 相同的模式
            def _parse_bytes(t: str) -> int:
                if not t: return 0
                t = t.strip().upper().replace(",", "")
                m = re.match(r"([\d.]+)\s*(TB|GB|MB|KB|B|TIB|GIB|MIB|KIB)", t)
                if not m:
                    try: return int(float(t))
                    except: return 0
                v, u = float(m.group(1)), m.group(2)
                mul = {"B":1,"KB":1024,"KIB":1024,"MB":1024**2,"MIB":1024**2,"GB":1024**3,"GIB":1024**3,"TB":1024**4,"TIB":1024**4}
                return int(v * mul.get(u, 1))

            def _parse_number(t: str) -> float:
                if not t: return 0
                t = t.strip().replace(",","").replace(" ","").upper()
                mult = 1
                if t.endswith("K"): mult, t = 1000, t[:-1]
                elif t.endswith("M"): mult, t = 1_000_000, t[:-1]
                elif t.endswith("B"): mult, t = 1_000_000_000, t[:-1]
                m = re.search(r"[\d.]+", t)
                return float(m.group()) * mult if m else 0

            patterns = [
                (r"上传量\s*[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))", "上传量"),
                (r"下载量\s*[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))", "下载量"),
                (r"分享率\s*[：:]\s*([\d.,]+)", "分享率"),
                (r"做种积分\s*[：:]\s*([\d.,]+\s*K?)", "做种积分"),
                (r"猫粮\s*(?:\[[^\]]*\])?\s*[：:]\s*([\d.,]+)", "猫粮(魔力)"),
                (r"魔力值\s*(?:\[[^\]]*\])?\s*[：:]\s*([\d.,]+)", "魔力值"),
                (r"积分\s*[：:]\s*([\d.,]+\s*K?)", "积分"),
                (r"茉莉[：:]\s*([\d.,]+\s*K?)", "茉莉(魔力)"),
                (r"Torrents?\s*seeding\s*(\d+)", "做种数(猫站)"),
                (r"Torrents?\s*leeching\s*(\d+)", "下载数(猫站)"),
                (r"做种活动\s*[：:]\s*(\d+)\s+\d+", "做种数(TTG)"),
                (r"当前活动\s*[：:]\s*(\d+)\s+\d+", "做种数(SSD)"),
                (r"做种活动\s*[：:]\s*\d+\s+(\d+)", "下载数(TTG)"),
                (r"当前活动\s*[：:]\s*\d+\s+(\d+)", "下载数(SSD)"),
            ]

            print("\n=== 解析结果 ===")
            found = False
            for pat, label in patterns:
                m = re.search(pat, clean, re.I)
                if m:
                    val = m.group(1).strip()
                    if label in ("上传量", "下载量"):
                        print(f"  {label}: {val} = {_parse_bytes(val)} bytes")
                    elif label in ("做种积分", "茉莉(魔力)"):
                        print(f"  {label}: {val} = {_parse_number(val)}")
                    else:
                        print(f"  {label}: {val}")
                    found = True
            if not found:
                print("  (未匹配到数据)")

            print("\n=== 页面文本前 1500 字符 ===")
            print(clean[:1500])

    except Exception as e:
        print(f"请求失败: {e}")


if __name__ == "__main__":
    site_id = sys.argv[1] if len(sys.argv) > 1 else "SSD"
    asyncio.run(debug_site(site_id))
