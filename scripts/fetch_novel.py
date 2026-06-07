"""
小说爬取脚本

从网络小说站爬取小说文本，输出纯文本 .txt，可直接对接注释引擎。
通用自动检测模式，无需为每个站点写配置。

内置反爬检测：自动识别 Cloudflare、验证码、登录墙、VIP、字体加密等保护机制，
对不可爬的站点给出明确拒绝原因。

用法：
    python scripts/fetch_novel.py <目录页URL>
    python scripts/fetch_novel.py <URL> --threads 5 --proxy http://127.0.0.1:7890
    python scripts/fetch_novel.py <URL> --start 10 --end 50
    python scripts/fetch_novel.py <URL> --resume
"""

import argparse
import json
import random
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cloudscraper
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup, Comment

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DELAY = 0.5
DEFAULT_THREADS = 3
DEFAULT_BATCH = 50
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
MAX_CONSECUTIVE_FAILS = 10  # 连续失败 N 章自动中止

# cloudscraper 懒加载单例（用于绕过 Cloudflare JS 挑战）
_cloud_scraper = None


def _get_cloud_scraper():
    global _cloud_scraper
    if _cloud_scraper is None:
        _cloud_scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False},
            delay=5,
        )
    return _cloud_scraper

# ── 已知不可爬站点 ──────────────────────────────────────────────
# 大型正版平台 / 反爬极其严格的站点，直接拒绝，不浪费时间

KNOWN_BLOCKED_SITES = {
    # 起点中文网 / 阅文系
    "qidian.com": "起点中文网（阅文集团）：正版付费平台，全部章节需登录+VIP，反爬极严",
    "read.qidian.com": "起点中文网阅读页：需登录，反爬极严",
    "yuewen.com": "阅文集团：版权保护严格，技术反爬完善",
    "qqbook.qidian.com": "起点QQ阅读：需登录",
    # 纵横中文网
    "zongheng.com": "纵横中文网：正版付费平台，章节需VIP，反爬严格",
    "book.zongheng.com": "纵横中文网：需登录+VIP",
    # 番茄小说（字节跳动）
    "fanqienovel.com": "番茄小说（字节跳动）：大厂反爬，JS渲染，字体加密",
    "fqnovel.com": "番茄小说：同上",
    # 书旗小说（阿里）
    "shuqi.com": "书旗小说（阿里）：大厂反爬，需登录",
    "shuqi.xin": "书旗小说：同上",
    # 掌阅
    "zhangyue.com": "掌阅：正版付费平台，反爬严格",
    "ireader.com": "掌阅iReader：需登录+付费",
    # 晋江文学城
    "jjwxc.net": "晋江文学城：版权保护严格，防盗章节机制完善",
    "jjwxc.com": "晋江文学城：同上",
    # 七猫小说
    "qimao.com": "七猫小说：大厂产品，JS渲染+字体加密",
    # 飞卢小说
    "faloo.com": "飞卢小说：反爬严格，VIP章节多",
    # 刺猬猫
    "ciweimao.com": "刺猬猫：反爬严格，付费内容多",
    # 塔读文学
    "tadu.com": "塔读文学：需登录+付费",
    # 咪咕阅读
    "migu.cn": "咪咕阅读（中国移动）：大厂反爬，需登录",
    # 网易云阅读
    "yuedu.163.com": "网易云阅读：需登录+付费",
    # 豆瓣阅读
    "read.douban.com": "豆瓣阅读：付费内容，反爬严格",
}


# ── 通用选择器库 ────────────────────────────────────────────────

CONTENT_SELECTORS = [
    "#content", "#chaptercontent", "#BookText", "#booktext",
    "#htmlContent", "#text_c", "#novelcontent",
    ".content", ".chapter-content", ".read-content",
    ".novel-content", ".text-wrap", ".articlecontent",
    ".word_read",
    "[itemprop='articleBody']",
]

TOC_SELECTORS = [
    "#list dl a", "#list a", ".listmain a",
    ".book_list a", ".mulu a", "#catalog a",
    ".volume a", "div.volume a",
    "ul.chapter-list a", ".chapter-list a",
    ".section-list a",  # 22biqu 等站点
    "dd a", "table a[href*='.html']",
]

AD_KEYWORDS = [
    "百度搜索", "最新章节", "请百度搜索", "手机阅读",
    "加入书签", "推荐票", "月票", "天才一秒", "笔趣阁",
    "本章未完", "点击下一页", "手机用户请浏览", "请记住本书",
    "www.", ".com", ".net", ".org",
    "记住网址", "手机端", "app下载", "最快更新",
    "本章未完，请点击下一页继续", "阅读最新章节",
    "上一章", "下一章", "章节目录", "保存书签",
]


# ── 反爬检测 ────────────────────────────────────────────────────

class AntiCrawlDetected(Exception):
    """反爬机制检测到，无法继续。"""
    def __init__(self, reason: str, details: str = ""):
        self.reason = reason
        self.details = details
        super().__init__(reason)


def check_blocked_site(url: str) -> str | None:
    """
    检查 URL 是否属于已知不可爬站点。
    返回拒绝原因字符串，或 None（可尝试）。
    """
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()

    for domain, reason in KNOWN_BLOCKED_SITES.items():
        if domain in hostname:
            return reason

    return None


def detect_anti_crawl(text: str, status_code: int = 200,
                      headers: dict | None = None) -> None:
    """
    检测页面中的反爬机制。检测到则抛出 AntiCrawlDetected。

    检测项：
    1. HTTP 状态码（403/429/503）
    2. Cloudflare / WAF 挑战
    3. 验证码
    4. 登录墙
    5. VIP 付费墙
    6. 字体加密
    7. JS 渲染检测（页面过短 = 内容由 JS 生成）
    """
    headers = headers or {}
    text_lower = text.lower() if text else ""

    # ── 1. HTTP 状态码（先检查是否为 Cloudflare 挑战，再下结论）──
    if status_code in (403, 503, 520, 521, 522):
        # Cloudflare 专用错误码 520/521/522 直接视为 CF 挑战
        if status_code in (520, 521, 522):
            raise AntiCrawlDetected(
                f"Cloudflare 拦截（HTTP {status_code}）",
                "目标网站使用了 Cloudflare 防护，服务器返回异常。\n"
                "将尝试使用 cloudscraper 自动绕过，若失败则建议：\n"
                "  1. 使用代理 --proxy 分散请求\n"
                "  2. 增大 --delay（如 --delay 3）降低请求频率\n"
                "  3. 稍后重试（IP 冷却后可能恢复）"
            )
        # 403/503 可能是 Cloudflare 挑战页面，先检查内容
        cf_challenge = [
            "challenge-platform", "cf-challenge", "__cf_chl",
            "window.location.href", "cf-turnstile",
        ]
        is_cf = any(kw in text_lower for kw in cf_challenge)
        if is_cf:
            raise AntiCrawlDetected(
                "Cloudflare JS 挑战（HTTP " + str(status_code) + "）",
                "目标网站使用了 Cloudflare 反爬保护，需要浏览器执行 JS 才能通过。\n"
                "将尝试使用 cloudscraper 自动绕过，若失败则建议：\n"
                "  1. 使用代理 --proxy 分散请求\n"
                "  2. 增大 --delay（如 --delay 3）降低请求频率\n"
                "  3. 稍后重试（IP 冷却后可能恢复）"
            )
        if status_code == 403:
            raise AntiCrawlDetected(
                "访问被拒绝（HTTP 403 Forbidden）",
                "目标网站拒绝了访问，可能原因：IP 被封、需要登录、或地区限制。\n"
                "建议：使用代理 --proxy 或更换网络。"
            )

    if status_code == 429:
        raise AntiCrawlDetected(
            "请求过于频繁（HTTP 429 Too Many Requests）",
            "目标网站检测到爬虫行为并限流。\n"
            "建议：增大 --delay（如 --delay 3），或使用代理分散请求。"
        )
    if status_code == 401:
        raise AntiCrawlDetected(
            "需要登录（HTTP 401 Unauthorized）",
            "目标网站要求登录才能访问。本工具不支持登录功能。"
        )
    if status_code == 402:
        raise AntiCrawlDetected(
            "需要付费（HTTP 402 Payment Required）",
            "目标内容为付费内容。"
        )

    # 去掉 <script>/<style> 标签再检测，避免 analytics 脚本误判
    visible = re.sub(r'<script[^>]*>.*?</script>', '', text,
                     flags=re.DOTALL | re.IGNORECASE)
    visible = re.sub(r'<style[^>]*>.*?</style>', '', visible,
                     flags=re.DOTALL | re.IGNORECASE)
    visible_lower = visible.lower()

    # ── 2. Cloudflare / WAF ──
    cf_indicators = [
        "cf-browser-verification", "cf_chl_opt", "cf-challenge-running",
        "cf-please-wait", "checking your browser", "cf-mitigated",
        "_cf_chl", "turnstile", "ddos-guard", "ddosguard",
        "cf-challenge-platform", "chal-",
    ]
    for indicator in cf_indicators:
        if indicator in visible_lower:
            raise AntiCrawlDetected(
                "Cloudflare / WAF 防护",
                "目标网站使用了 Cloudflare 或类似 WAF 防护，需要浏览器 JS 执行才能通过。\n"
                "将尝试使用 cloudscraper 自动绕过，若失败则建议手动在浏览器中访问后下载。"
            )

    # ── 3. 验证码 ──
    captcha_indicators = [
        "captcha", "recaptcha", "hcaptcha", "验证码",
        "geetest", "极验", "行为验证", "slider-captcha",
        "请完成安全验证", "请拖动滑块", "请点选",
        "twocaptcha", "anticaptcha",
    ]
    for indicator in captcha_indicators:
        if indicator in visible_lower:
            raise AntiCrawlDetected(
                "验证码拦截",
                "目标网站要求输入验证码才能访问。\n"
                "本工具无法自动通过验证码。建议手动在浏览器中访问。"
            )

    # ── 4. 登录墙 ──
    login_indicators = [
        "请登录后阅读", "登录后查看", "请先登录",
        "login-required", "need-login", "auth-wall",
        "会员登录", "用户登录后", "登录后可",
    ]
    login_form = re.search(
        r'<form[^>]*(login|signin|auth)[^>]*>',
        text_lower
    )
    for indicator in login_indicators:
        if indicator in text_lower:
            raise AntiCrawlDetected(
                "需要登录",
                "目标网站要求登录才能查看内容。本工具不支持登录功能。"
            )
    if login_form:
        # 再确认有 password 输入框
        if re.search(r'type=["\']password["\']', text_lower):
            raise AntiCrawlDetected(
                "需要登录",
                "目标网站要求登录才能查看内容（检测到登录表单）。本工具不支持登录功能。"
            )

    # ── 5. VIP 付费墙 ──
    vip_indicators = [
        "开通vip", "vip章节", "付费章节", "订阅章节",
        "购买本章", "购买全文", "充值", "书币",
        "本章为付费内容", "本章需订阅", "解锁全文",
        "开通会员", "会员可阅读", "付费阅读",
        r"千字\d+书币", "起点币", "纵横币",
    ]
    for indicator in vip_indicators:
        if re.search(indicator, text_lower):
            raise AntiCrawlDetected(
                "VIP / 付费章节",
                "目标网站的章节需要 VIP 或付费才能阅读。\n"
                "本工具不支持付费购买。建议使用正版渠道阅读。"
            )

    # 以下检测需要较完整的页面内容
    if not text or len(text) < 100:
        return

    # ── 6. 字体加密 ──
    font_indicators = [
        "@font-face", "font-family: 'anti", "font-family: 'secret",
        "font-family: 'encrypted", "font-family: 'custom",
        "unicode-range:", "woff2?\\?v=",
    ]
    # 字体加密的典型特征：正文中有大量无意义符号或用 CSS 替换
    if re.search(r"@font-face\s*\{[^}]{50,}\}", text):
        # 进一步确认：如果正文区域有大量非常规 Unicode 字符
        content_match = re.search(
            r'<div[^>]*id=["\']content["\'][^>]*>(.*?)</div>',
            text, re.DOTALL
        )
        if content_match:
            content_text = content_match.group(1)
            # 统计非中文、非英文、非标点的异常字符
            weird_chars = re.findall(r'[-]', content_text)
            if len(weird_chars) > 20:
                raise AntiCrawlDetected(
                    "字体加密",
                    "目标网站使用了字体加密技术，将文字替换为自定义字体符号。\n"
                    "即使下载成功，内容也会是乱码。本工具无法解密字体加密。"
                )

    # ── 7. JS 渲染检测 ──
    # 如果页面 body 很短但有大量 script 标签，内容可能是 JS 动态加载的
    body_match = re.search(r'<body[^>]*>(.*?)</body>', text, re.DOTALL | re.IGNORECASE)
    if body_match:
        body_content = body_match.group(1)
        body_text_only = re.sub(r'<script[^>]*>.*?</script>', '', body_content,
                                flags=re.DOTALL | re.IGNORECASE)
        body_text_only = re.sub(r'<[^>]+>', '', body_text_only).strip()
        script_count = len(re.findall(r'<script', body_content, re.IGNORECASE))

        if len(body_text_only) < 100 and script_count >= 3:
            raise AntiCrawlDetected(
                "JS 动态渲染",
                "目标网站的内容由 JavaScript 动态生成，需要浏览器引擎才能获取。\n"
                "本工具只能抓取静态 HTML 内容。"
            )


def check_chapter_protected(text: str) -> bool:
    """检查章节内容是否被反爬保护（返回 True = 被保护）。"""
    if not text:
        return False
    text_lower = text.lower()
    quick_checks = [
        "请登录", "vip章节", "付费章节", "订阅本章",
        "开通vip", "请先登录", "验证码",
    ]
    return any(kw in text_lower for kw in quick_checks)


# ── HTTP ────────────────────────────────────────────────────────

def create_session(proxy: str | None = None) -> cffi_requests.Session:
    """创建 HTTP 会话，使用 curl_cffi 模拟 Chrome TLS 指纹。"""
    session = cffi_requests.Session(impersonate="chrome131")

    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })

    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    return session


def set_referer(session, url: str):
    """设置 Referer 为目标站点首页，模拟站内跳转。"""
    base = base_url_of(url)
    session.headers["Referer"] = base + "/"


def fetch_page(session, url: str, encoding: str | None = None,
               check_anti_crawl: bool = True) -> BeautifulSoup:
    """获取并解析网页，带反爬检测和自动重试。Cloudflare 挑战自动回退 cloudscraper。"""
    set_referer(session, url)
    last_err = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            # 随机延迟抖动（避免固定节奏被识别）
            if attempt > 0:
                jitter = random.uniform(0.5, 1.5)
                time.sleep(RETRY_BACKOFF * attempt * jitter)

            resp = session.get(url, timeout=30)

            # 限流：自动退避
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                print(f"\n  [限流] 收到 429，等待 {retry_after} 秒后重试...")
                time.sleep(retry_after)
                if attempt < MAX_RETRIES:
                    continue

            if resp.status_code in (500, 502, 503, 504) and attempt < MAX_RETRIES:
                continue

            # 反爬检测
            if check_anti_crawl:
                detect_anti_crawl(
                    resp.text, resp.status_code,
                    dict(resp.headers) if hasattr(resp, 'headers') else None
                )

            resp.raise_for_status()
            break

        except AntiCrawlDetected as e:
            # Cloudflare JS 挑战 → 尝试 cloudscraper 绕过
            if "Cloudflare" in e.reason:
                print(f"\n  [Cloudflare] 检测到 JS 挑战，尝试 cloudscraper 绕过...")
                try:
                    return _fetch_with_cloudscraper(url, encoding)
                except Exception as cs_err:
                    print(f"\n  [Cloudflare] cloudscraper 也失败了: {cs_err}")
            raise
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                continue
            raise last_err

    # 编码处理
    if encoding:
        resp.encoding = encoding
    elif hasattr(resp, "apparent_encoding") and resp.apparent_encoding and \
            resp.apparent_encoding.lower() != "iso-8859-1":
        resp.encoding = resp.apparent_encoding

    text = resp.text
    if len(text) < 100:
        for enc in ("utf-8", "gbk", "gb2312", "gb18030"):
            if enc == (encoding or "").lower():
                continue
            try:
                resp.encoding = enc
                text = resp.text
                if len(text) >= 100:
                    break
            except Exception:
                continue

    return BeautifulSoup(text, "lxml")


def _fetch_with_cloudscraper(url: str, encoding: str | None = None) -> BeautifulSoup:
    """使用 cloudscraper 绕过 Cloudflare JS 挑战，返回解析后的 BeautifulSoup。"""
    scraper = _get_cloud_scraper()
    resp = scraper.get(url, timeout=45)
    resp.raise_for_status()

    # 编码处理：优先使用指定编码，否则自动检测
    if encoding:
        resp.encoding = encoding
    elif resp.apparent_encoding and resp.apparent_encoding.lower() != "iso-8859-1":
        resp.encoding = resp.apparent_encoding

    text = resp.text
    if len(text) < 100:
        for enc in ("utf-8", "gbk", "gb2312", "gb18030"):
            if enc == (encoding or "").lower():
                continue
            try:
                resp.encoding = enc
                text = resp.text
                if len(text) >= 100:
                    break
            except Exception:
                continue

    # 对 cloudscraper 的结果也做反爬检测（可能拿到验证码页）
    detect_anti_crawl(text, resp.status_code, dict(resp.headers))

    return BeautifulSoup(text, "lxml")


# ── 工具 ────────────────────────────────────────────────────────

def base_url_of(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def clean_book_title(raw: str) -> str:
    for sep in ["-", "—", "_", "|", "最新章节", "全文阅读", "无弹窗"]:
        if sep in raw:
            raw = raw.split(sep)[0]
    return re.sub(r"\s+", "", raw).strip() or "未知小说"


def safe_dirname(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip("_. ") or "novel"


def detect_selectors(soup: BeautifulSoup) -> tuple:
    """自动检测正文和目录选择器。"""
    content_sel = None
    for sel in CONTENT_SELECTORS:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) >= 200:
            content_sel = sel
            break

    toc_sel = None
    for sel in TOC_SELECTORS:
        if len(soup.select(sel)) >= 10:
            toc_sel = sel
            break

    return content_sel, toc_sel, "h1"


# ── 目录解析 ────────────────────────────────────────────────────

def parse_toc(session, url: str) -> tuple:
    """
    解析目录页。返回 (book_title, chapters, content_sel, encoding)。
    """
    # 1. 先检查是否为已知不可爬站点
    block_reason = check_blocked_site(url)
    if block_reason:
        raise AntiCrawlDetected("目标站点不可爬取", block_reason)

    print(f"[目录] 正在解析: {url}")
    encoding = None

    try:
        soup = fetch_page(session, url, check_anti_crawl=True)
    except AntiCrawlDetected as e:
        print(f"\n[拒绝] 反爬机制拦截：{e.reason}")
        if e.details:
            print(f"  {e.details}")
        raise

    # 2. 检测是否为书籍详情页（非目录页），如果是则跳转到章节目录
    base = base_url_of(url)
    toc_link = None
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text in ("章节目录", "目录", "全部章节"):
            href = a.get("href", "").strip()
            if href and ".html" not in href:
                if href.startswith("/"):
                    toc_link = base + href
                elif not href.startswith("http"):
                    toc_link = urllib.parse.urljoin(url, href)
                else:
                    toc_link = href
                break
    if toc_link and toc_link != url:
        print(f"[目录] 检测到章节目录页，跳转: {toc_link}")
        soup = fetch_page(session, toc_link, check_anti_crawl=True)
        url = toc_link

    # 3. 如果不是目录第一页，沿"上一页"链跳转到第一页
    for _ in range(20):  # 最多跳 20 次，防止死循环
        prev_url = None
        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True) == "上一页":
                href = a.get("href", "").strip()
                if href:
                    if href.startswith("/"):
                        prev_url = base + href
                    elif not href.startswith("http"):
                        prev_url = urllib.parse.urljoin(url, href)
                    else:
                        prev_url = href
                break
        if not prev_url:
            break  # 没有"上一页"，已在首页

        # 判断是否已在第一页：URL 以 /1/ 结尾且"上一页"是其父路径
        if (url.rstrip("/").endswith("/1")
                and url.rstrip("/").startswith(prev_url.rstrip("/"))):
            break

        print(f"[目录] 当前非首页，跳转: {prev_url}")
        url = prev_url
        soup = fetch_page(session, url, check_anti_crawl=True)

    # 4. 沿"上一页"链可能跳到了详情页，再次检测章节目录链接
    toc_link = None
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text in ("章节目录", "目录", "全部章节"):
            href = a.get("href", "").strip()
            if href and ".html" not in href:
                if href.startswith("/"):
                    toc_link = base + href
                elif not href.startswith("http"):
                    toc_link = urllib.parse.urljoin(url, href)
                else:
                    toc_link = href
                break
    if toc_link and toc_link != url:
        print(f"[目录] 跳转到章节目录: {toc_link}")
        soup = fetch_page(session, toc_link, check_anti_crawl=True)
        url = toc_link

    # 3. 页面级反爬检测（JS 渲染、字体加密等）
    # fetch_page 已处理 HTTP 级检测，这里补充内容级检测
    page_text = str(soup)

    # 提取书名
    title_tag = soup.find("title")
    book_title = clean_book_title(title_tag.get_text(strip=True)) if title_tag else "未知小说"

    # 自动检测选择器
    content_sel, toc_sel, _ = detect_selectors(soup)

    # 如果没有检测到目录选择器，可能页面被保护
    if not toc_sel:
        # 再做一次反爬检测（有些站点 TOC 页也需要 JS）
        body_text = soup.get_text(strip=True)
        if len(body_text) < 200:
            raise AntiCrawlDetected(
                f"页面内容过少（{len(body_text)} 字），可能是 JS 动态渲染",
                "本工具只能抓取静态 HTML 内容"
            )
        print("[警告] 未检测到目录选择器，尝试从全部链接中提取章节")

    # 提取章节链接（跟随目录分页）
    chapters = []
    seen = set()
    toc_pages_visited = set()
    current_toc_url = url

    for _ in range(50):  # 最多 50 页目录，防止死循环
        if current_toc_url in toc_pages_visited:
            break
        toc_pages_visited.add(current_toc_url)

        if current_toc_url != url:
            print(f"[目录] 翻页: {current_toc_url}")
            try:
                soup = fetch_page(session, current_toc_url, check_anti_crawl=True)
            except Exception as e:
                print(f"[目录] 翻页失败: {e}")
                break

        links = soup.select(toc_sel) if toc_sel else []
        if len(links) < 5:
            links = [a for a in soup.find_all("a", href=True)
                     if re.search(r"\d+\.html?", a.get("href", ""))
                     and len(a.get_text(strip=True)) >= 2]

        for a in links:
            href = a.get("href", "").strip()
            title = a.get_text(strip=True)
            if not href or not title or href in ("#", "javascript:void(0)", "javascript:;"):
                continue

            if href.startswith("//"):
                href = urllib.parse.urlparse(url).scheme + ":" + href
            elif href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                href = urllib.parse.urljoin(url, href)

            if href in seen:
                continue
            seen.add(href)
            chapters.append({"index": len(chapters), "title": title, "url": href})

        # 查找目录"下一页"链接（排除章节分页的"下一页"）
        next_toc_url = None
        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True) != "下一页":
                continue
            href = a.get("href", "").strip()
            if not href or href in ("#", "javascript:void(0)", "javascript:;"):
                continue
            # 目录分页 URL 通常不含 .html（如 /biqu5403/2/）
            if ".html" in href:
                continue
            if href.startswith("//"):
                href = urllib.parse.urlparse(url).scheme + ":" + href
            elif href.startswith("/"):
                href = base + href
            elif not href.startswith("http"):
                href = urllib.parse.urljoin(url, href)
            next_toc_url = href
            break

        if not next_toc_url:
            break
        current_toc_url = next_toc_url

    # 按章节号排序（处理目录页乱序的情况）
    def _chapter_sort_key(ch):
        m = re.search(r'第\s*(\d+)\s*章', ch["title"])
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)', ch["title"])
        if m:
            return int(m.group(1))
        return ch["index"]  # 无数字则保持原序

    chapters.sort(key=_chapter_sort_key)
    for i, ch in enumerate(chapters):
        ch["index"] = i

    print(f"[目录] 书名: {book_title}，共 {len(chapters)} 章")
    if content_sel:
        print(f"[检测] 正文选择器: {content_sel}")
    return book_title, chapters, content_sel, encoding


# ── 章节下载 ────────────────────────────────────────────────────

def _extract_content(soup, content_sel: str | None):
    """从页面提取正文元素，清理标签后返回文本。"""
    if content_sel:
        el = soup.select_one(content_sel)
    else:
        el = None
        for sel in CONTENT_SELECTORS:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) >= 50:
                break
            el = None
    if not el:
        return None
    for tag in el.find_all(["script", "style", "ins", "iframe"]):
        tag.decompose()
    for c in el.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()
    return el


def _find_next_page(soup, current_url: str) -> str | None:
    """查找"下一页"链接（章节内翻页，非下一章）。"""
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text not in ("下一页", "下一章"):
            continue
        href = a["href"].strip()
        if not href or href in ("#", "javascript:void(0)", "javascript:;"):
            continue
        # 拼接为绝对 URL
        if href.startswith("//"):
            href = urllib.parse.urlparse(current_url).scheme + ":" + href
        elif href.startswith("/"):
            href = base_url_of(current_url) + href
        elif not href.startswith("http"):
            href = urllib.parse.urljoin(current_url, href)
        # "下一章" 可能是章节内分页（如 820807_1.html）或真正的下一章
        # 只跟随分页模式的链接（当前 URL 的 _N 变体）
        if text == "下一章":
            cur_base = re.sub(r"(_\d+)?\.html?$", "", current_url)
            nxt_base = re.sub(r"(_\d+)?\.html?$", "", href)
            if cur_base != nxt_base:
                continue  # 不是同一章节的分页，跳过
        return href
    return None


def download_chapter(session, chapter: dict,
                     content_sel: str | None, encoding: str | None) -> dict:
    url = chapter["url"]
    idx = chapter["index"]
    try:
        soup = fetch_page(session, url, encoding, check_anti_crawl=True)

        # 优先取 .reader-main 内的 h1.title，避免取到站点名称
        h1 = (soup.select_one(".reader-main h1.title")
              or soup.select_one(".reader-main h1")
              or soup.select_one("h1.title"))
        if h1:
            h1_text = h1.get_text(strip=True)
            # 过滤掉站点名（通常很短且不含章节关键字）
            if len(h1_text) > 4 or re.search(r'第.*章|chapter|\d+', h1_text, re.I):
                title = h1_text
            else:
                title = chapter["title"]
        else:
            title = chapter["title"]

        el = _extract_content(soup, content_sel)
        if not el:
            return {"index": idx, "title": title, "content": "", "error": "未找到正文"}

        text = clean_chapter_text(el.get_text(separator="\n"))

        # 跟随章节内分页（"下一页"链接）
        for _ in range(20):  # 最多 20 页，防止死循环
            next_url = _find_next_page(soup, url)
            if not next_url:
                break
            url = next_url
            soup = fetch_page(session, url, encoding, check_anti_crawl=True)
            el = _extract_content(soup, content_sel)
            if not el:
                break
            page_text = clean_chapter_text(el.get_text(separator="\n"))
            if page_text:
                text += "\n" + page_text

        if not text or len(text) < 10:
            return {"index": idx, "title": title, "content": "",
                    "error": "正文内容为空"}

        # 章节级保护检测
        if check_chapter_protected(text):
            return {"index": idx, "title": title, "content": "",
                    "error": "该章节需要登录或付费"}

        return {"index": idx, "title": title, "content": text, "error": None}

    except AntiCrawlDetected as e:
        return {"index": idx, "title": chapter["title"], "content": "",
                "error": f"反爬拦截: {e.reason}"}
    except Exception as e:
        return {"index": idx, "title": chapter["title"], "content": "",
                "error": str(e)}


def clean_chapter_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(kw in line for kw in AD_KEYWORDS):
            continue
        if re.match(r"^https?://\S+$", line) or re.match(r"^www\.\S+$", line):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── 进度管理 ────────────────────────────────────────────────────

def save_progress(path: Path, downloaded: dict, written_idx: int, total: int):
    # 不持久化失败的章节，续传时会重新下载
    clean = {k: v for k, v in downloaded.items() if not v.get("error")}
    data = {
        "downloaded": {str(k): v for k, v in clean.items()},
        "written_up_to": written_idx,
        "total": total,
    }
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(path)


def load_progress(path: Path) -> tuple:
    if not path.exists():
        return {}, 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        dl = {int(k): v for k, v in data.get("downloaded", {}).items()}
        return dl, data.get("written_up_to", 0)
    except Exception:
        return {}, 0


# ── 主流程 ──────────────────────────────────────────────────────

def fetch_novel(url: str, output_dir: str | None = None,
                start: int | None = None, end: int | None = None,
                delay: float = DEFAULT_DELAY, threads: int = DEFAULT_THREADS,
                batch: int = DEFAULT_BATCH, resume: bool = False,
                encoding: str | None = None,
                proxy: str | None = None,
                progress_callback=None) -> Path:

    session = create_session(proxy)

    try:
        book_title, chapters, content_sel, detected_enc = parse_toc(session, url)
    except AntiCrawlDetected:
        raise
    except Exception as e:
        raise RuntimeError(f"解析目录失败: {e}") from e

    enc = encoding or detected_enc

    if not chapters:
        raise RuntimeError("未找到任何章节链接")

    # 章节范围
    if start is not None or end is not None:
        s = (start or 1) - 1
        e = end or len(chapters)
        chapters = chapters[s:e]
        for i, ch in enumerate(chapters):
            ch["index"] = i
        if not progress_callback:
            print(f"[范围] 第 {s + 1} ~ {e} 章，共 {len(chapters)} 章")

    if progress_callback:
        progress_callback(0, len(chapters), "toc", {
            "title": book_title,
            "total_chapters": len(chapters),
        })

    # 输出目录
    safe_title = safe_dirname(book_title)
    if output_dir:
        out_dir = Path(output_dir)
        if not out_dir.is_absolute():
            out_dir = DATA_DIR / output_dir
    else:
        out_dir = DATA_DIR / safe_title
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{safe_title}.txt"
    progress_path = out_dir / "progress.json"

    # 断点续传
    downloaded, written_up_to = ({}, 0)
    if resume:
        downloaded, written_up_to = load_progress(progress_path)
        # 清除之前失败的章节，让它们可以被重新下载
        failed_indices = [k for k, v in downloaded.items() if v.get("error")]
        for k in failed_indices:
            del downloaded[k]
        if downloaded and not progress_callback:
            print(f"[续传] 已下载 {len(downloaded)} 章，已写入 {written_up_to} 章"
                  + (f"，清除 {len(failed_indices)} 个失败记录" if failed_indices else ""))

    to_download = [ch for ch in chapters if ch["index"] not in downloaded]
    if not to_download:
        if not progress_callback:
            print("[续传] 所有章节已下载，直接写入")
    else:
        if not progress_callback:
            print(f"[下载] 待下载 {len(to_download)} 章，并发 {threads} 线程")

    total = len(chapters)
    failed = 0
    consecutive_fails = 0
    lock = threading.Lock()
    t0 = time.time()

    def do_download(ch):
        nonlocal failed
        # 随机延迟抖动 ±30%
        jitter = delay * random.uniform(0.7, 1.3)
        time.sleep(jitter)

        r = download_chapter(session, ch, content_sel, enc)
        with lock:
            if r["error"]:
                failed += 1
            else:
                downloaded[ch["index"]] = r
        return r

    next_write = written_up_to

    def write_batch():
        nonlocal next_write
        parts = []
        while next_write < total and next_write in downloaded:
            r = downloaded[next_write]
            if r.get("error"):
                # 跳过失败章节，不阻塞后续章节写入
                next_write += 1
                continue
            if r.get("content"):
                parts.append(f"【{r['title']}】\n{r['content']}")
            next_write += 1

        if not parts:
            return 0

        mode = "a" if next_write > len(parts) else "w"
        if next_write == len(parts) and not resume:
            mode = "w"

        with open(output_path, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n\n")
            f.write("\n\n".join(parts))

        save_progress(progress_path, downloaded, next_write, total)
        return len(parts)

    # 续传：写入积压
    if resume and written_up_to < len(downloaded):
        parts = []
        idx = written_up_to
        while idx < total and idx in downloaded:
            r = downloaded[idx]
            if r.get("error"):
                # 跳过失败章节，不阻塞后续章节写入
                idx += 1
                continue
            if r.get("content"):
                parts.append(f"【{r['title']}】\n{r['content']}")
            idx += 1

        if parts:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(parts))
            next_write = idx
            save_progress(progress_path, downloaded, next_write, total)
            print(f"[续传] 写入积压 {len(parts)} 章，已写入至第 {next_write} 章")

    done_count = 0
    aborted = False

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {}
        for ch in to_download:
            f = pool.submit(do_download, ch)
            futures[f] = ch

        for future in as_completed(futures):
            ch = futures[future]
            r = future.result()
            done_count += 1

            downloaded[ch["index"]] = r
            if r["error"]:
                consecutive_fails += 1
                if not progress_callback:
                    print(f"\n  [失败] 第 {ch['index'] + 1} 章 {ch['title'][:20]}: {r['error']}")
            else:
                consecutive_fails = 0

            # 连续失败检测
            if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                msg = (f"连续 {consecutive_fails} 章下载失败，"
                       f"可能原因：IP 被封、反爬机制升级、站点不可用。")
                if not progress_callback:
                    print(f"\n\n[中止] {msg}")
                    print(f"  建议：更换代理 --proxy 或稍后重试 --resume。")
                if progress_callback:
                    progress_callback(done_count, total, "error", {"message": msg})
                aborted = True
                pool.shutdown(wait=False, cancel_futures=True)
                break

            # 进度回调
            elapsed = time.time() - t0
            speed = done_count / elapsed if elapsed > 0 else 0
            if progress_callback:
                progress_callback(done_count, total, "download", {
                    "chapter": ch["title"][:30],
                    "failed": failed,
                    "speed": round(speed, 1),
                    "error": r["error"],
                })
            else:
                pct = done_count / total * 100
                sys.stderr.write(
                    f"\r[下载] {done_count}/{total} ({pct:.0f}%) "
                    f"| {speed:.1f} 章/秒 | 失败 {failed}"
                )
                sys.stderr.flush()

            if next_write in downloaded:
                write_batch()

        if not aborted:
            write_batch()

    elapsed = time.time() - t0
    if not progress_callback:
        sys.stderr.write("\r" + " " * 70 + "\r")
        sys.stderr.flush()

    # 元数据
    downloaded_count = len([r for r in downloaded.values() if not r.get("error")])
    size_kb = output_path.stat().st_size / 1024 if output_path.exists() else 0

    meta = {
        "title": book_title,
        "chapters_total": total,
        "chapters_downloaded": downloaded_count,
        "chapters_failed": failed,
        "aborted": aborted,
        "source_url": url,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "file_size_kb": round(size_kb, 1),
    }
    meta_path = out_dir / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    if failed == 0 and not aborted and progress_path.exists():
        progress_path.unlink()

    if progress_callback:
        progress_callback(total, total, "complete", {
            "title": book_title,
            "downloaded": downloaded_count,
            "total": total,
            "failed": failed,
            "aborted": aborted,
            "size_kb": round(size_kb, 1),
            "elapsed": round(elapsed, 1),
            "output_dir": str(out_dir),
            "output_file": str(output_path),
        })
    else:
        print(f"[完成] {book_title}")
        print(f"  章节: {downloaded_count}/{total} 成功"
              + (f"，{failed} 失败" if failed else "")
              + ("（中止）" if aborted else ""))
        print(f"  大小: {size_kb:.1f} KB")
        print(f"  耗时: {elapsed:.1f} 秒")
        print(f"  输出: {out_dir}/")

    return out_dir


# ── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="从网络小说站爬取小说文本（通用自动检测，内置反爬防护）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/fetch_novel.py https://www.example.com/book/12345/
  python scripts/fetch_novel.py <URL> --threads 5 --delay 1
  python scripts/fetch_novel.py <URL> --proxy http://127.0.0.1:7890
  python scripts/fetch_novel.py <URL> --start 10 --end 50 --resume
""")
    parser.add_argument("url", help="小说目录页 URL")
    parser.add_argument("-o", "--output-dir", help="输出目录名（默认用书名）")
    parser.add_argument("--start", type=int, help="起始章节（从 1 开始）")
    parser.add_argument("--end", type=int, help="结束章节（包含）")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS,
                        help=f"并发下载线程数（默认 {DEFAULT_THREADS}）")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH,
                        help=f"每多少章写入一次文件（默认 {DEFAULT_BATCH}）")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"请求间隔秒数（默认 {DEFAULT_DELAY}）")
    parser.add_argument("--resume", action="store_true", help="断点续传")
    parser.add_argument("--encoding", help="强制指定编码（如 gbk, utf-8）")
    parser.add_argument("--proxy", help="HTTP 代理（如 http://127.0.0.1:7890）")
    args = parser.parse_args()

    if not args.url.startswith(("http://", "https://")):
        print("[错误] URL 需以 http:// 或 https:// 开头")
        sys.exit(1)

    fetch_novel(
        url=args.url,
        output_dir=args.output_dir,
        start=args.start,
        end=args.end,
        delay=args.delay,
        threads=args.threads,
        batch=args.batch,
        resume=args.resume,
        encoding=args.encoding,
        proxy=args.proxy,
    )


if __name__ == "__main__":
    main()
