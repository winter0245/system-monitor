"""
调试脚本：直接用 Cookie 和 Headers 抓取目标 PT 站点
用法: python debug_raw.py
"""
import asyncio
import httpx
import re

URL = "https://www.hddolby.com/index.php"

COOKIES = {
    "cf_clearance": "sRSX.wfJaFjvVKAmhYKAdYKKR1KFSE9AdfAS1KuzmIw-1781486270-1.2.1.1-8gxBmzee0eTyHJk5zamFFYqQ.d6YIZ_xno4WxEeEZMNgzYHNeRVrd8c23G24EajnnTCTObYsCarGNf6GubtEcHMbks8El1Dr3sNW3.agsjNa_u84R_W6mxZe8Rs63dNNhSmgGVer0AMqV6bAMIFzHgsn24dUXGGyaEa3MN9hxnjZJ.86UhVLSMrRXc3rjopd56TJWouVI7.RlBwjCTq93UsHKHAD75CMhHbfMRY9eSHVw.tpsi8cAxGRmmHi2kuQ23k_5IKtE.j_EU8wuqI7uOWriGvYfn9qg8FPVceuh5FS3J.6QjmmCosRQ8j.mSrK0rBScYsJzUA8XEy9oOXY1cNK8oPDgNLtDYyv4yRMrAMQPvwK3XKlSpIaGRCGJcJTIZR8RHciq5Kqu5jvL0g5HJa8PQHrqxqUiz9DixmcPj8",
    "c_secure_uid": "NDQxMzA%3D",
    "c_secure_pass": "d01da5fb3e20b8123fc05a38d1b909bb",
    "c_secure_ssl": "eWVhaA%3D%3D",
    "c_secure_tracker_ssl": "bm9wZQ%3D%3D",
    "c_secure_login": "bm9wZQ%3D%3D",
}

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "referer": "https://www.hddolby.com/login.php",
    "sec-ch-ua": '"Microsoft Edge";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-full-version": '"149.0.4022.69"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"15.0.0"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
}


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


async def main():
    print(f"=== 调试 HDDolby ===")
    print(f"URL: {URL}")

    try:
        async with httpx.AsyncClient(cookies=COOKIES, timeout=30, follow_redirects=True, verify=False) as client:
            resp = await client.get(URL, headers=HEADERS)
            print(f"\nStatus: {resp.status_code}")
            print(f"Final URL: {resp.url}")

            tm = re.search(r"<title[^>]*>(.+?)</title>", resp.text, re.I | re.S)
            print(f"Title: {tm.group(1).strip() if tm else 'N/A'}")

            # 去掉 script / style
            clean = re.sub(r"<script[^>]*>.*?</script>", " ", resp.text, flags=re.I | re.S)
            clean = re.sub(r"<style[^>]*>.*?</style>", " ", clean, flags=re.I | re.S)
            clean = re.sub(r"<[^>]+>", " ", clean)
            clean = re.sub(r"&nbsp;", " ", clean)
            clean = re.sub(r"\s+", " ", clean).strip()

            patterns = [
                (r"上传量\s*[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))", "上传量"),
                (r"下载量\s*[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB|TiB|GiB|MiB|KiB|B))", "下载量"),
                (r"分享率\s*[：:]\s*([\d.,]+)", "分享率"),
                (r"做种积分\s*[：:]\s*([\d.,]+\s*K?)", "做种积分"),
                (r"积分\s*[：:]\s*([\d.,]+\s*K?)", "积分"),
                (r"魔力值\s*[：:]\s*([\d.,]+\s*K?)", "魔力值"),
                (r"茉莉[：:]\s*([\d.,]+\s*K?)", "茉莉(魔力)"),
                (r"当前活动\s*[：:]\s*(\d+)\s+\d+", "做种数"),
                (r"做种活动\s*[：:]\s*(\d+)\s+\d+", "做种数"),
                (r"当前活动\s*[：:]\s*\d+\s+(\d+)", "下载数"),
                (r"做种活动\s*[：:]\s*\d+\s+(\d+)", "下载数"),
                (r"鲸币[^：:]*[：:]\s*([\d.,]+\s*K?)", "鲸币"),
                (r"当前做种\s*[：:]\s*(\d+)", "做种数"),
                (r"当前下载\s*[：:]\s*(\d+)", "下载数"),
                (r"[Uu]ploaded\s*[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB))", "Uploaded"),
                (r"[Dd]ownloaded\s*[：:]\s*([\d.,]+\s*(?:TB|GB|MB|KB))", "Downloaded"),
            ]

            print("\n=== 解析结果 ===")
            found = False
            for pat, label in patterns:
                m = re.search(pat, clean, re.I)
                if m:
                    val = m.group(1).strip()
                    if label in ("上传量", "下载量", "Uploaded", "Downloaded"):
                        print(f"  {label}: {val} = {_parse_bytes(val)} bytes")
                    elif label in ("做种积分", "茉莉(魔力)", "魔力值", "积分"):
                        print(f"  {label}: {val} = {_parse_number(val)}")
                    else:
                        print(f"  {label}: {val}")
                    found = True
            if not found:
                print("  (未匹配到数据)")

            print("\n=== 页面文本前 2000 字符 ===")
            print(clean[:2000])

            # 也打印用户信息行（通常在顶栏）
            user_line = re.search(r"(欢迎回来.*?)(当前|首页|论坛|搜索|导航)", clean, re.I)
            if user_line:
                print(f"\n=== 用户信息行 ===")
                print(user_line.group(1))

    except Exception as e:
        print(f"请求失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
