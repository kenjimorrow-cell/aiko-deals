#!/usr/bin/env python3
"""
每日旅遊特價整理器 — Playwright 版
來源：KKday、雄獅旅遊、易遊網
輸出：精美 HTML 頁面（含折扣碼），自動在瀏覽器開啟
"""

import json
import os
import re
import sys
import time
import subprocess
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from pathlib import Path

# ──────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
OUTPUT_DIR  = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

CODES     = CONFIG["discount_codes"]
AFFILIATES = CONFIG.get("affiliate_links", {})
BRAND     = CONFIG["branding"]


def build_url(deal_url: str, source: str) -> str:
    """幫指定來源的連結加上聯盟追蹤參數"""
    # 易遊網：先查預存的短連結對照表
    if source == "eztravel":
        ez_map = CONFIG.get("eztravel_affiliate_urls", {})
        short = ez_map.get(deal_url, "")
        if short:
            return short
    aff = AFFILIATES.get(source, "")
    if not aff or not deal_url or deal_url == "#":
        return deal_url
    sep = "&" if "?" in deal_url else "?"
    return f"{deal_url}{sep}{aff}"

DEST_EMOJI = {
    "東京": "🗼", "大阪": "🏯", "沖繩": "🌺", "北海道": "❄️",
    "九州": "♨️", "京都": "⛩️", "札幌": "❄️", "福岡": "🍜",
    "首爾": "🇰🇷", "釜山": "🎣", "泰國": "🐘", "曼谷": "🛕",
    "新加坡": "🦁", "馬來西亞": "🌴", "吉隆坡": "🏙️",
    "越南": "🍜", "峴港": "🏖️", "河內": "🎋", "胡志明": "🛵",
    "巴里島": "🌊", "香港": "🏙️", "澳門": "🎰", "帛琉": "🤿",
    "義大利": "🍕", "法國": "🥐", "英國": "🎡",
}

# 各目的地備援圖片（無縮圖時使用）
DEST_IMAGES = {
    "曼谷": "https://img1.cdn-eztravel.com.tw/images/1mc2w12000em9x3802E43_C_600_400_R5_Q80.jpg",
    "泰國": "https://img1.cdn-eztravel.com.tw/images/1mc2w12000em9x3802E43_C_600_400_R5_Q80.jpg",
    "清邁": "https://img1.cdn-eztravel.com.tw/images/0586912000sqcig1c0646_C_600_400_R5_Q80.jpg",
    "首爾": "https://img1.cdn-eztravel.com.tw/images/0580w12000som6dqsD611_C_600_400_R5_Q80.jpg",
    "韓國": "https://img1.cdn-eztravel.com.tw/images/0580w12000som6dqsD611_C_600_400_R5_Q80.jpg",
    "釜山": "https://img1.cdn-eztravel.com.tw/images/0580w12000som6dqsD611_C_600_400_R5_Q80.jpg",
    "香港": "https://img1.cdn-eztravel.com.tw/images/20030s000000hzn0n9310_C_600_400_R5_Q80.jpg",
    "東京": "https://img1.cdn-eztravel.com.tw/images/0221712000oahl31u544A_C_600_400_R5_Q80.jpg",
    "日本": "https://img1.cdn-eztravel.com.tw/images/0221712000oahl31u544A_C_600_400_R5_Q80.jpg",
    "富士": "https://img1.cdn-eztravel.com.tw/images/0221712000oahl31u544A_C_600_400_R5_Q80.jpg",
    "日光": "https://img1.cdn-eztravel.com.tw/images/0221712000oahl31u544A_C_600_400_R5_Q80.jpg",
    "伊豆": "https://img1.cdn-eztravel.com.tw/images/0221712000oahl31u544A_C_600_400_R5_Q80.jpg",
    "石垣島": "https://img1.cdn-eztravel.com.tw/images/0220h12000lj06m5s9364_C_600_400_R5_Q80.jpg",
    "沖繩":   "https://img1.cdn-eztravel.com.tw/images/0220h12000lj06m5s9364_C_600_400_R5_Q80.jpg",
    "大阪":   "https://img1.cdn-eztravel.com.tw/images/1mc0w12000me0dxct2E7F_C_600_400_R5_Q80.jpg",
    "福岡":   "https://img1.cdn-eztravel.com.tw/images/1mc5k12000pw5e5gf334B_C_600_400_R5_Q80.jpg",
}

DEST_RE = re.compile(
    r"(日本|東京|大阪|沖繩|北海道|九州|京都|札幌|福岡|石垣島|"
    r"首爾|釜山|韓國|泰國|曼谷|清邁|新加坡|馬來西亞|吉隆坡|"
    r"越南|峴港|河內|胡志明|巴里島|香港|澳門|帛琉)"
)

def get_emoji(text: str) -> str:
    for k, v in DEST_EMOJI.items():
        if k in text:
            return v
    return "🌍"

def clean_price(raw: str) -> str:
    nums = re.findall(r"\d[\d,]*", str(raw))
    if not nums:
        return ""
    return max(nums, key=lambda s: int(s.replace(",", ""))).replace(",", "")


# ══════════════════════════════════════════════
# 資料結構
# ══════════════════════════════════════════════
@dataclass
class Deal:
    source: str
    type: str            # flight / tour / ticket
    title: str
    destination: str
    price: str
    original_price: str = ""
    image_url: str = ""
    deal_url: str = ""
    discount_code: str = ""
    subtitle: str = ""
    tags: List[str] = field(default_factory=list)

    def price_int(self) -> int:
        try:
            return int(self.price.replace(",", ""))
        except Exception:
            return 0

    def discount_pct(self) -> int:
        if not self.original_price or not self.price:
            return 0
        try:
            orig = int(self.original_price.replace(",", ""))
            curr = self.price_int()
            if orig > curr > 0:
                return round((1 - curr / orig) * 100)
        except Exception:
            pass
        return 0


# ══════════════════════════════════════════════
# Playwright 爬蟲基礎
# ══════════════════════════════════════════════
def _run_playwright(script_fn) -> List[Deal]:
    """把 async Playwright 函式包成同步呼叫"""
    import asyncio
    try:
        return asyncio.run(script_fn())
    except Exception as e:
        print(f"  ⚠️  Playwright 執行失敗: {e}")
        return []


# ══════════════════════════════════════════════
# KKday 爬蟲（指定商品模式）
# ══════════════════════════════════════════════
class KKdayScraper:
    UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.0 Mobile/15E148 Safari/604.1"
    )

    def scrape(self) -> List[Deal]:
        curated = CONFIG.get("kkday_curated_deals", [])
        if not curated:
            return []
        print(f"  → Playwright 載入 KKday 指定商品（{len(curated)} 筆）...")
        return _run_playwright(lambda: self._async_scrape(curated))

    async def _async_scrape(self, curated: list) -> List[Deal]:
        import asyncio
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        async def fetch_one(item: dict) -> dict:
            # 手機 UA 可繞過 KKday 封鎖，每筆獨立開 browser 抓即時價格
            # 有 image_url 則跳過圖片抓取，但仍嘗試動態抓價格（config price 作備援）
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                ctx = await browser.new_context(locale="zh-TW", user_agent=self.UA)
                page = await ctx.new_page()
                stealth = Stealth()
                await stealth.apply_stealth_async(page)
                result = {"img": item.get("image_url", ""), "price": item.get("price", "")}
                try:
                    await page.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(2500)
                    data = await page.evaluate("""() => {
                        const og = document.querySelector('meta[property="og:image"]');
                        const img = og ? og.getAttribute('content') : '';
                        let price = '';
                        const priceEls = document.querySelectorAll(
                            '[class*="price"],[class*="Price"],[class*="amount"],[class*="Amount"]'
                        );
                        for (const el of priceEls) {
                            const m = (el.innerText || '').match(/(\\d[\\d,]+)/);
                            if (m) { price = m[1].replace(/,/g, ''); break; }
                        }
                        return { img, price };
                    }""")
                    if not item.get("image_url") and data.get("img"):
                        result["img"] = data["img"]
                    # 只在 config 沒有手動設定價格時才用動態抓取的價格
                    if data.get("price") and not item.get("price"):
                        result["price"] = data["price"]
                    print(f"    ✓ {item['url'].split('/')[-1][:30]}  price={result['price']}  img={'✓' if result['img'] else '✗'}")
                except Exception as e:
                    print(f"    ⚠️  {item['url'].split('/')[-1][:30]}: {e}")
                finally:
                    await page.close()
                    await browser.close()
            return {**item, **result}

        results = await asyncio.gather(*[fetch_one(i) for i in curated])

        deals = []
        for r in results:
            title = (r.get("title") or "KKday 優惠")[:45]
            dest  = r.get("destination", "")
            if not dest:
                m = DEST_RE.search(title)
                dest = m.group(1) if m else ""
            deals.append(Deal(
                source="kkday", type="ticket",
                title=title,
                destination=dest,
                price=clean_price(r.get("price", "")),
                original_price=clean_price(r.get("original_price", "")),
                image_url=r.get("img", "") or r.get("image_url", ""),
                deal_url=r.get("url", ""),
                discount_code=r.get("discount_code", ""),
            ))
        return deals


# ══════════════════════════════════════════════
# 雄獅旅遊 爬蟲
# ══════════════════════════════════════════════
class LionTravelScraper:
    URLS = [
        "https://www.liontravel.com",
        "https://www.liontravel.com/category/zh-tw/package",
    ]
    BASE = "https://www.liontravel.com"
    BOOKING_BASE = "https://sipincollection.com"

    def scrape(self) -> List[Deal]:
        print("  → Playwright 爬取雄獅旅遊...")
        return _run_playwright(self._async_scrape)

    async def _async_scrape(self) -> List[Deal]:
        from playwright.async_api import async_playwright
        debug = "--debug" in sys.argv
        deals = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                locale="zh-TW",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await ctx.new_page()

            for url in self.URLS:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(3500)

                    if debug:
                        title = await page.title()
                        print(f"    [debug] 頁面標題: {title}")
                        ss_path = OUTPUT_DIR / f"debug_lion_{url.split('/')[-1][:20] or 'home'}.png"
                        await page.screenshot(path=str(ss_path))
                        print(f"    [debug] 截圖存至: {ss_path}")
                        classes = await page.evaluate("""() => {
                          const all = Array.from(document.querySelectorAll('[class]'));
                          const found = new Set();
                          all.forEach(el => el.className.split(' ').forEach(c => {
                            if (/card|product|tour|item|package/i.test(c)) found.add(c);
                          }));
                          return Array.from(found).slice(0, 30);
                        }""")
                        print(f"    [debug] 相關 class: {classes}")

                    # 只抓含折扣標示的卡片（折/省/免小費/半價/%）
                    items = await page.evaluate("""() => {
                        const results = [];
                        const DEAL_RE = /折|省|免小費|半價|%|搶|限時|特惠/;
                        const links = Array.from(document.querySelectorAll('a.cardHref, a[class*="cardHref"]'))
                            .filter(a => DEAL_RE.test(a.innerText));
                        for (const linkEl of links.slice(0, 20)) {
                            const priceEl = linkEl.querySelector('.priceNum,[class*="priceNum"],[class*="price"]');
                            const imgEl   = linkEl.querySelector('img');
                            const rawText = (linkEl.innerText || '').trim();
                            const lines   = rawText.split('\\n').map(l => l.trim()).filter(l => l.length > 1);
                            // 第一行非純數字/TWD/NT$/起 的行當標題
                            const title   = lines.find(l => !/^(NT|TWD|\\d|起|免|含|\\$)/.test(l)) || lines[0] || '';
                            // 價格：先試元素，再從文字 regex 抓數字
                            let price = priceEl?.innerText?.trim() || '';
                            if (!price) {
                                const m = rawText.match(/(\\d{1,3}(?:,\\d{3})+|\\d{4,6})/g);
                                price = m ? m[0] : '';
                            }
                            results.push({
                                url:   linkEl.href,
                                title: title,
                                price: price,
                                img:   imgEl?.src || '',
                            });
                        }
                        return results;
                    }""")

                    print(f"    {url.split('/')[-1] or 'home'} → {len(items)} 筆商品")

                    for item in items:
                        title = (item.get("title") or "")[:40].strip()
                        link  = item.get("url", "")
                        if not title and not link:
                            continue
                        dest_m = DEST_RE.search(title)
                        deals.append(Deal(
                            source="lion", type="tour",
                            title=title or "雄獅優惠行程",
                            destination=dest_m.group(1) if dest_m else "",
                            price=clean_price(item.get("price", "")),
                            image_url=item.get("img", ""),
                            deal_url=link,
                        ))

                    if deals:
                        break

                except Exception as e:
                    print(f"    ⚠️  {url} 失敗: {e}")
                    continue

            await browser.close()

        seen = set()
        unique = []
        for d in deals:
            if d.title not in seen:
                seen.add(d.title)
                unique.append(d)
        return unique[:12]

    async def _text(self, el, selectors: list) -> str:
        for sel in selectors:
            found = await el.query_selector(sel)
            if found:
                txt = await found.inner_text()
                if txt and txt.strip():
                    return txt.strip()
        return ""

    async def _product_link(self, card, base: str, keywords: list) -> str:
        links = await card.query_selector_all("a[href]")
        for a in links:
            href = await a.get_attribute("href") or ""
            if any(k in href for k in keywords):
                if not href.startswith("http"):
                    href = base + href
                return href
        return ""

    async def _any_link(self, card, base: str) -> str:
        a = await card.query_selector("a[href]")
        href = await a.get_attribute("href") if a else ""
        if href and not href.startswith("http"):
            href = base + href
        return href or ""


# ══════════════════════════════════════════════
# 易遊網 爬蟲
# ══════════════════════════════════════════════
class EzTravelScraper:
    URLS = [
        "https://packages.eztravel.com.tw/",  # 機加酒自由行首頁
    ]
    BASE = "https://packages.eztravel.com.tw"

    def scrape(self) -> List[Deal]:
        print("  → Playwright 爬取易遊網...")
        return _run_playwright(self._async_scrape)

    async def _async_scrape(self) -> List[Deal]:
        from playwright.async_api import async_playwright
        debug = "--debug" in sys.argv
        deals = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                locale="zh-TW",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await ctx.new_page()

            for url in self.URLS:
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.evaluate("window.scrollTo(0, 600)")
                    await page.wait_for_timeout(3000)

                    if debug:
                        title = await page.title()
                        print(f"    [debug] 頁面標題: {title}")
                        ss_path = OUTPUT_DIR / f"debug_ez_{url.rstrip('/').split('/')[-1][:20] or 'home'}.png"
                        await page.screenshot(path=str(ss_path))
                        print(f"    [debug] 截圖存至: {ss_path}")

                    # packages.eztravel.com.tw: 機加酒商品連結格式 /roundtrip-XXX-YYY
                    items = await page.evaluate("""() => {
                        const results = [];
                        const seen = new Set();
                        // 機加酒連結（含 /roundtrip- 或 /oneway-）
                        const pkgLinks = Array.from(document.querySelectorAll('a[href]'))
                            .filter(a => /\\/roundtrip-|\\/oneway-/.test(a.href) && a.href.includes('packages.eztravel'));
                        for (const a of pkgLinks.slice(0, 20)) {
                            // 去掉 tracking 參數（rec_sid 等），保留乾淨 URL
                            const cleanUrl = a.href.split('?')[0];
                            if (seen.has(cleanUrl)) continue;
                            seen.add(cleanUrl);
                            const rawText  = (a.innerText || '').trim();
                            const lines    = rawText.split('\\n').map(l => l.trim()).filter(l => l);
                            const title    = lines[0] || '';
                            const priceMatch = rawText.match(/(\\d[\\d,]+)起/);
                            const price    = priceMatch ? priceMatch[1].replace(/,/g,'') : '';
                            const imgEl    = a.querySelector('img');
                            results.push({ url: cleanUrl, title, price, img: imgEl?.src || '' });
                        }
                        return results;
                    }""")

                    print(f"    packages → {len(items)} 筆商品")

                    for item in items:
                        title = (item.get("title") or "")[:40].strip()
                        link  = item.get("url", "")
                        if not title and not link:
                            continue
                        dest_m = DEST_RE.search(title)
                        deals.append(Deal(
                            source="eztravel", type="tour",
                            title=title or "易遊網機加酒",
                            destination=dest_m.group(1) if dest_m else "",
                            price=clean_price(item.get("price", "")),
                            image_url=item.get("img", ""),
                            deal_url=link,
                        ))

                except Exception as e:
                    print(f"    ⚠️  {url} 失敗: {e}")
                    continue

            await browser.close()

        # 清邁直接加入（CNX 頁面無法抓到正確連結，用 config 短連結）
        cnx_url = CONFIG.get("eztravel_affiliate_urls", {}).get(
            "https://packages.eztravel.com.tw/roundtrip-TPE-CNX", "")
        if cnx_url:
            deals.append(Deal(
                source="eztravel", type="tour",
                title="台北-清邁機票來回自由行",
                destination="清邁",
                price="",
                image_url=DEST_IMAGES.get("清邁", ""),
                deal_url="https://packages.eztravel.com.tw/roundtrip-TPE-CNX",
            ))

        seen = set()
        unique = []
        for d in deals:
            if d.title not in seen:
                seen.add(d.title)
                unique.append(d)

        # 排序：曼谷優先，清邁緊跟在後
        def sort_key(d):
            if d.destination == "曼谷" or "曼谷" in d.title:
                return 0
            if d.destination == "清邁" or "清邁" in d.title:
                return 1
            return 2
        unique.sort(key=sort_key)

        return unique[:12]


class HotelScraper:
    def scrape(self) -> List[Deal]:
        items = CONFIG.get("hotel_curated_deals", [])
        deals = []
        for item in items:
            deals.append(Deal(
                source="hotel",
                type="hotel",
                title=item.get("title", ""),
                destination=item.get("destination", ""),
                price=item.get("price", ""),
                subtitle=item.get("subtitle", ""),
                image_url=item.get("image_url", ""),
                deal_url=item.get("url", ""),
            ))
        return deals


# ══════════════════════════════════════════════
# HTML 生成器
# ══════════════════════════════════════════════
SOURCE_META = {
    "kkday":    {"label": "KKday",   "color": "#00C569", "icon": "🎫"},
    "lion":     {"label": "雄獅旅遊", "color": "#E30B14", "icon": "🦁"},
    "eztravel": {"label": "易遊網",   "color": "#0066CC", "icon": "✈️"},
    "hotel":    {"label": "易遊網飯店", "color": "#9B59B6", "icon": "🏨"},
}


def build_deal_card(deal: Deal, code: str) -> str:
    meta      = SOURCE_META.get(deal.source, {"label": deal.source, "color": "#888", "icon": "🌍"})
    emoji     = get_emoji(deal.destination or deal.title)
    dpct      = deal.discount_pct()
    # 優先用 deal 自身的折扣碼，沒有才用區段折扣碼
    code      = deal.discount_code or code
    has_code  = code and code not in ("NONE", "", "填入你的KKday折扣碼", "填入你的雄獅折扣碼", "填入你的易遊網折扣碼")
    aff       = AFFILIATES.get(deal.source, "")
    final_url = build_url(deal.deal_url or "#", deal.source)

    if deal.price and deal.price.isdigit():
        price_str = f"NT${int(deal.price):,}"
    else:
        price_str = "優惠中"

    orig_html = ""
    if deal.original_price and deal.original_price.isdigit() and int(deal.original_price) > deal.price_int():
        orig_html = f'<span class="orig-price">NT${int(deal.original_price):,}</span>'

    badge_html = ""
    if dpct >= 5:
        badge_html = f'<div class="badge">省{dpct}%</div>'
    elif has_code or aff:
        badge_html = '<div class="badge code-badge">優惠連結</div>'

    # 折扣碼區塊
    code_html = ""
    if has_code:
        code_html = f"""
      <div class="code-box" onclick="copyCode(event,'{code}')">
        <span class="code-label">折扣碼</span>
        <span class="code-value">{code}</span>
        <span class="copy-hint">點擊複製</span>
      </div>"""

    # URL 顯示區塊（點一下複製完整網址）
    url_display = final_url if final_url != "#" else ""
    url_html = ""
    if url_display:
        url_html = f"""
      <div class="url-row" onclick="copyCode(event,'{url_display}')">
        <span class="url-icon">🔗</span>
        <span class="url-text">{url_display}</span>
        <span class="url-copy">複製</span>
      </div>"""

    # 備援圖片：優先用爬到的，沒有就查目的地對照表
    img_src = deal.image_url
    if not img_src:
        for k, v in DEST_IMAGES.items():
            if k in deal.title or k in deal.destination:
                img_src = v
                break
    if img_src:
        img_html = f'<div class="card-img"><img src="{img_src}" loading="lazy" alt=""></div>'
    else:
        img_html = f'<div class="card-img card-img-ph">{emoji}</div>'

    return f"""<div class="deal-card">
    {badge_html}
    {img_html}
    <div class="card-body">
      <div class="src-tag" style="background:{meta['color']}">{meta['icon']} {meta['label']}</div>
      <h3 class="card-title">{deal.title}</h3>
      {f'<p class="card-subtitle">{deal.subtitle}</p>' if deal.subtitle else ''}
      <div class="card-price">
        {orig_html}
        <span class="deal-price">{price_str}</span>
        <span class="price-sfx">起</span>
      </div>
      {code_html}
      {url_html}
      {f'<a class="card-btn" href="{final_url}" target="_blank" rel="noopener">前往購買 →</a>' if final_url and final_url != "#" else '<div class="card-btn card-btn-na">連結待更新</div>'}
    </div>
  </div>"""


def build_section(title: str, icon: str, deals: List[Deal], code: str) -> str:
    if not deals:
        return ""
    cards = "\n  ".join(build_deal_card(d, code) for d in deals)
    return f"""<section class="section">
  <div class="sec-hdr">
    <span class="sec-icon">{icon}</span>
    <h2 class="sec-title">{title}</h2>
    <span class="sec-count">{len(deals)} 筆優惠</span>
  </div>
  <div class="cards-grid">
  {cards}
  </div>
</section>"""


def generate_html(kkday: List[Deal], lion: List[Deal], ez: List[Deal], hotels: List[Deal] = None) -> str:
    today    = datetime.today()
    date_str = today.strftime("%Y 年 %m 月 %d 日")
    weekday  = ["一", "二", "三", "四", "五", "六", "日"][today.weekday()]
    ts       = today.strftime("%H:%M")
    total    = len(kkday) + len(lion) + len(ez)

    kkday_code = CODES.get("kkday", "")
    lion_code  = CODES.get("lion", "")
    ez_code    = CODES.get("eztravel", "")

    # Hero 折扣碼區
    hero_codes = ""
    for src, code, label in [
        ("kkday", kkday_code, "KKday"),
        ("lion",  lion_code,  "雄獅"),
        ("eztravel", ez_code, "易遊網"),
    ]:
        c = code
        if c and c not in ("NONE", "", "填入你的KKday折扣碼", "填入你的雄獅折扣碼", "填入你的易遊網折扣碼"):
            meta = SOURCE_META.get(src, {})
            hero_codes += f"""
        <div class="hero-code" onclick="copyCode(event,'{c}')">
          <div class="hc-src" style="color:{meta.get('color','#aaa')}">{label}</div>
          <div class="hc-val">{c}</div>
          <div class="hc-hint">點擊複製</div>
        </div>"""

    sections = ""
    sections += build_section("台灣飯店特惠",       "🏨", hotels or [], "")
    sections += build_section("KKday 景點門票特惠", "🎫", kkday, kkday_code)
    sections += build_section("雄獅旅遊 行程優惠",  "🦁", lion,  lion_code)
    sections += build_section("易遊網 超值行程",    "✈️", ez,    ez_code)

    no_deals = '<div class="no-deals">😔 今日暫無特價資訊，請稍後再試</div>' if not sections.strip() else ""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<link rel="manifest" href="/aiko-deals/manifest.json">
<link rel="apple-touch-icon" href="/aiko-deals/apple-touch-icon.png">
<meta name="theme-color" content="#9a4a20">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="愛可推薦">
<meta property="og:title" content="愛可推薦｜每日旅遊特惠精選">
<meta property="og:description" content="跟著愛可出發，最便宜的行程都在這！KKday、雄獅、易遊網每日最新優惠整理。">
<meta property="og:image" content="https://kenjimorrow-cell.github.io/aiko-deals/og-image.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://kenjimorrow-cell.github.io/aiko-deals/">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://kenjimorrow-cell.github.io/aiko-deals/og-image.jpg">
<title>今日旅遊特惠 {today.strftime('%Y/%m/%d')} | {BRAND['name']}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,"Noto Sans TC","PingFang TC",sans-serif;background:#fdf6ee;color:#3d2010;min-height:100vh}}

/* Hero */
.hero{{background:linear-gradient(135deg,#7a3b1e,#b06030,#c87840);color:#fff;padding:40px 20px 48px;text-align:center;position:relative;overflow:hidden}}
.hero::before{{content:'';position:absolute;inset:0;background:radial-gradient(circle at 20% 80%,rgba(255,180,80,.15),transparent 50%),radial-gradient(circle at 80% 20%,rgba(255,220,120,.1),transparent 50%)}}
.hero>*{{position:relative}}
.hero-emoji{{font-size:52px;display:block;margin-bottom:12px}}
.hero-date{{font-size:13px;color:rgba(255,235,200,.6);margin-bottom:8px;letter-spacing:.8px}}
.hero h1{{font-size:clamp(26px,7vw,42px);font-weight:900;line-height:1.15;margin-bottom:10px}}
.hero h1 span{{color:#f5c87a}}
.hero-sub{{font-size:15px;color:rgba(255,235,200,.8);margin-bottom:28px}}
.hero-codes{{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin-bottom:20px}}
.hero-code{{background:rgba(255,255,255,.12);border:1px solid rgba(255,220,160,.3);border-radius:14px;padding:12px 20px;min-width:130px;cursor:pointer;transition:background .15s}}
.hero-code:hover{{background:rgba(255,255,255,.2)}}
.hc-src{{font-size:11px;font-weight:700;margin-bottom:4px;letter-spacing:.5px;color:rgba(255,220,160,.8)}}
.hc-val{{font-size:20px;font-weight:900;color:#f5c87a;letter-spacing:1.5px}}
.hc-hint{{font-size:10px;color:rgba(255,220,160,.45);margin-top:3px}}
.hero-stats{{font-size:12px;color:rgba(255,220,160,.45)}}

/* Section */
.section{{max-width:1200px;margin:32px auto;padding:0 16px}}
.sec-hdr{{display:flex;align-items:center;gap:10px;margin-bottom:18px;padding-bottom:12px;border-bottom:2px solid #e8d0b4}}
.sec-icon{{font-size:24px}}
.sec-title{{font-size:20px;font-weight:800;flex:1;color:#5a2e10}}
.sec-count{{font-size:12px;background:#f2e4d0;color:#8a5830;padding:3px 12px;border-radius:20px;font-weight:600}}

/* Cards */
.cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:20px}}
.deal-card{{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(120,60,20,.08);position:relative;display:flex;flex-direction:column;transition:transform .2s,box-shadow .2s;border:1px solid #f0e0cc}}
.deal-card:hover{{transform:translateY(-4px);box-shadow:0 10px 28px rgba(120,60,20,.14)}}
.badge{{position:absolute;top:12px;right:12px;background:#c0392b;color:#fff;font-size:11px;font-weight:800;padding:3px 10px;border-radius:20px;z-index:2}}
.code-badge{{background:#c07a20}}
.card-img{{width:100%;height:180px;overflow:hidden;background:linear-gradient(135deg,#c07840,#e0a060)}}
.card-img img{{width:100%;height:100%;object-fit:cover}}
.card-img-ph{{display:flex;align-items:center;justify-content:center;font-size:70px}}
.card-body{{padding:16px;display:flex;flex-direction:column;flex:1;gap:10px}}
.src-tag{{display:inline-block;color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;align-self:flex-start;letter-spacing:.3px}}
.card-title{{font-size:15px;font-weight:700;line-height:1.4;color:#3d2010;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-subtitle{{font-size:12px;color:#7a5a3a;margin:3px 0 0;line-height:1.4}}
.card-price{{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap}}
.orig-price{{font-size:13px;color:#b09070;text-decoration:line-through}}
.deal-price{{font-size:26px;font-weight:900;color:#b83820;line-height:1}}
.price-sfx{{font-size:12px;color:#b09070}}

/* Code Box */
.code-box{{background:linear-gradient(135deg,#fdf0dc,#fae5c0);border:1.5px dashed #c8963c;border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:8px;cursor:pointer;transition:background .15s}}
.code-box:hover{{background:linear-gradient(135deg,#fae5c0,#f5d9a8)}}
.code-label{{font-size:11px;font-weight:700;color:#7a4f2e;white-space:nowrap}}
.code-value{{font-size:16px;font-weight:900;color:#7a4f2e;letter-spacing:1.5px;flex:1;text-align:center}}
.copy-hint{{font-size:10px;color:#a0693a;white-space:nowrap}}
.url-row{{display:flex;align-items:center;gap:6px;background:#faf2e8;border:0.5px solid #e8d8c0;border-radius:8px;padding:8px 10px;cursor:pointer;transition:background .15s;overflow:hidden}}
.url-row:hover{{background:#f2e8d8}}
.url-icon{{font-size:13px;flex-shrink:0}}
.url-text{{font-size:11px;color:#8a6848;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;font-family:monospace}}
.url-copy{{font-size:10px;font-weight:700;color:#9a5020;flex-shrink:0;white-space:nowrap}}

/* CTA */
.card-btn{{display:block;text-align:center;background:linear-gradient(135deg,#b06030,#d0884a);color:#fff;text-decoration:none;font-size:13px;font-weight:700;padding:11px;border-radius:10px;margin-top:auto;transition:opacity .2s}}
.card-btn:hover{{opacity:.88}}
.card-btn-na{{background:#f0e0cc;color:#b09070;cursor:default}}

/* Misc */
.no-deals{{text-align:center;padding:80px 20px;color:#b09070;font-size:16px}}
footer{{text-align:center;padding:30px 20px 50px;color:#b09070;font-size:12px;line-height:2}}
footer strong{{color:#8a5830}}
.toast{{position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(16px);background:#5a2e10;color:#fdf6ee;padding:10px 28px;border-radius:30px;font-size:13px;font-weight:600;opacity:0;transition:all .3s;pointer-events:none;z-index:999}}
.toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}

@media(max-width:600px){{
  .cards-grid{{grid-template-columns:1fr}}
  .hero h1{{font-size:22px}}
  .hero-codes{{flex-direction:column;align-items:center}}
}}
</style>
</head>
<body>

<div class="hero">
  <span class="hero-emoji">✈️</span>
  <h1>今日旅遊<span>特惠精選</span></h1>
  <p class="hero-sub">{BRAND['tagline']}</p>
  {f'<div class="hero-codes">{hero_codes}</div>' if hero_codes else ''}
</div>

{sections}
{no_deals}

<footer>
  <strong>{BRAND['name']}</strong> 每日早上 9:00 自動整理<br>
  以上價格僅供參考，實際以各平台官網為準 · {today.strftime('%Y/%m/%d %H:%M')} 更新
</footer>
<div class="toast" id="toast"></div>

<script>
function copyCode(e, code) {{
  e.stopPropagation();
  const t = document.getElementById('toast');
  const show = (msg) => {{
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2400);
  }};
  if (navigator.clipboard) {{
    navigator.clipboard.writeText(code).then(() => show('✅ 已複製折扣碼：' + code));
  }} else {{
    const ta = document.createElement('textarea');
    ta.value = code;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    show('✅ 已複製折扣碼：' + code);
  }}
}}
</script>
<script>
if ('serviceWorker' in navigator) {{
  window.addEventListener('load', () => {{
    navigator.serviceWorker.register('/aiko-deals/sw.js');
  }});
}}
</script>
</body>
</html>"""


# ══════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════
def main():
    today = datetime.today()
    print(f"\n{'─'*50}")
    print(f"  旅遊特價整理器  {today.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'─'*50}\n")

    print("[1/4] 台灣飯店特惠")
    hotel_deals = HotelScraper().scrape()
    print(f"  ✓ {len(hotel_deals)} 筆\n")

    print("[2/4] KKday 景點門票特惠")
    kkday_deals = KKdayScraper().scrape()
    print(f"  ✓ {len(kkday_deals)} 筆\n")

    print("[3/4] 雄獅旅遊 行程優惠")
    lion_deals = LionTravelScraper().scrape()
    print(f"  ✓ {len(lion_deals)} 筆\n")

    print("[4/4] 易遊網 超值行程")
    ez_deals = EzTravelScraper().scrape()
    print(f"  ✓ {len(ez_deals)} 筆\n")

    # 生成 HTML
    html = generate_html(kkday_deals, lion_deals, ez_deals, hotel_deals)

    fname   = f"deals_{today.strftime('%Y-%m-%d')}.html"
    outpath = OUTPUT_DIR / fname
    latest  = OUTPUT_DIR / "latest.html"

    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)
    with open(latest, "w", encoding="utf-8") as f:
        f.write(html)

    # 儲存 JSON 備份
    all_deals = hotel_deals + kkday_deals + lion_deals + ez_deals
    json_path = OUTPUT_DIR / f"deals_{today.strftime('%Y-%m-%d')}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([asdict(d) for d in all_deals], f, ensure_ascii=False, indent=2)

    total = len(all_deals)
    print(f"📄 HTML 已儲存：{outpath}")
    print(f"📊 JSON 已儲存：{json_path}")
    print(f"✨ 完成！共 {total} 筆特價\n")

    # 自動推到 GitHub Pages
    _push_to_github(html, today)

    if "--no-open" not in sys.argv:
        subprocess.run(["open", str(latest)], check=False)
        print("🌐 已在瀏覽器開啟")


def _push_to_github(html: str, today):
    """把今天的頁面推到 GitHub Pages"""
    index_path = OUTPUT_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    try:
        git = ["git", "-C", str(OUTPUT_DIR)]
        subprocess.run(git + ["add", "index.html", "og-image.jpg", "manifest.json", "sw.js", "icon-192.png", "icon-512.png", "apple-touch-icon.png"], check=True, capture_output=True)
        msg = f"每日旅遊特惠 {today.strftime('%Y-%m-%d')}"
        result = subprocess.run(git + ["commit", "-m", msg], capture_output=True, text=True)
        if "nothing to commit" in result.stdout + result.stderr:
            print("📡 GitHub Pages：今日內容已是最新，略過推送")
            return
        subprocess.run(git + ["push", "origin", "main"], check=True, capture_output=True)
        print("📡 GitHub Pages 已更新：https://kenjimorrow-cell.github.io/aiko-deals/")
    except Exception as e:
        print(f"⚠️  GitHub Pages 推送失敗（不影響本機頁面）：{e}")


if __name__ == "__main__":
    main()
