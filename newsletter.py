# -*- coding: utf-8 -*-
"""
공급망 노동인권 뉴스레터 v4
- 네이버 뉴스 API 다중 키워드 수집 + 중복 제거 + 주요 언론사 우선
- 6개 NGO/단체 사이트 최신 콘텐츠 스크래핑
- 대시보드 + 썸네일
- Gmail SMTP 발송
"""

import os, re, html, smtplib, requests, hashlib
from datetime import datetime
from collections import Counter
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime

# ── 설정 ──────────────────────────────────────────────────────────────────────
KEYWORDS = [
    "삼성전자 공급망",
    "삼성전자 협력사",
    "기업인권",
    "삼성 하청",
    "애플 하청",
    "강제노동 기업",
    "분쟁광물",
    "삼성 지속가능경영",
    "삼성 ESG",

    "공급망 실사",
    "아동 노동",
    "ILO",
    "forced labor",
    "위구르",
]
MAX_PER_KEYWORD = 5
MAX_NEWS        = 20  # 네이버 뉴스 최대
MAX_SITE        = 3   # 사이트당 최대 아티클

# 모니터링 사이트
MONITOR_SITES = [
    {
        "name": "Electronics Watch",
        "url":  "https://electronicswatch.org/en/",
        "color": "#0891b2",
        "icon":  "🖥️",
    },
    {
        "name": "Good Electronics",
        "url":  "https://goodelectronics.org/",
        "color": "#059669",
        "icon":  "♻️",
    },

    {
        "name": "IndustriALL",
        "url":  "https://www.industriall-union.org/",
        "color": "#dc2626",
        "icon":  "⚙️",
    },

    {
        "name": "Sherpa",
        "url":  "https://www.asso-sherpa.org/home",
        "color": "#b45309",
        "icon":  "⚖️",
    },
]

NAVER_CLIENT_ID     = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
GMAIL_USER          = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD  = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENTS          = [r.strip() for r in os.environ["RECIPIENTS"].split(",") if r.strip()]

MEDIA_PRIORITY = {
    "yonhapnews.co.kr": 1, "yna.co.kr": 1,
    "reuters.com": 1, "ap.org": 1, "bbc.com": 1,
    "chosun.com": 2, "joins.com": 2, "joongang.co.kr": 2,
    "donga.com": 2, "hani.co.kr": 2, "khan.co.kr": 2,
    "hankyung.com": 3, "mk.co.kr": 3, "sedaily.com": 3,
    "bloomberg.com": 2, "ft.com": 2, "wsj.com": 2,
    "nytimes.com": 2, "theguardian.com": 2,
}

CATEGORY_COLOR = {
    "삼성전자 공급망":   "#1428a0",
    "삼성전자 협력사":   "#1428a0",
    "기업인권":          "#7c3aed",
    "삼성 하청":         "#1428a0",
    "애플 하청":         "#555555",
    "강제노동 기업":     "#dc2626",
    "분쟁광물":          "#b45309",
    "삼성 지속가능경영": "#1428a0",
    "삼성 ESG":          "#1428a0",

    "공급망 실사":       "#0891b2",
    "아동 노동":         "#dc2626",
    "ILO":               "#7c3aed",
    "forced labor":      "#dc2626",
    "위구르":            "#dc2626",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def clean(text: str) -> str:
    text = html.unescape(text)
    return re.sub(r"<[^>]+>", "", text).strip()

def fmt_date(pub: str) -> str:
    try:
        return parsedate_to_datetime(pub).strftime("%Y.%m.%d %H:%M")
    except Exception:
        return pub

def get_domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else ""

def media_rank(url: str) -> int:
    domain = get_domain(url)
    for k, v in MEDIA_PRIORITY.items():
        if k in domain:
            return v
    return 9

def article_id(title: str) -> str:
    t = re.sub(r"[^\w]", "", title.lower())
    return hashlib.md5(t.encode()).hexdigest()

def get_thumbnail(url: str) -> str:
    try:
        r = requests.get(url, timeout=4, headers=HEADERS)
        m = re.search(r'og:image["\s]+content=["\']([^"\']+)["\']', r.text)
        if not m:
            m = re.search(r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', r.text)
        if m:
            img = m.group(1)
            if img.startswith("http"):
                return img
    except Exception:
        pass
    return ""


# ── 1. 네이버 뉴스 수집 ────────────────────────────────────────────────────────
def collect_news():
    pool = {}
    for kw in KEYWORDS:
        url = "https://openapi.naver.com/v1/search/news.json"
        headers_naver = {
            "X-Naver-Client-Id":     NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        }
        params = {"query": kw, "display": MAX_PER_KEYWORD, "sort": "date"}
        try:
            resp = requests.get(url, headers=headers_naver, params=params, timeout=10)
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as e:
            print(f"  오류 [{kw}]: {e}")
            continue

        print(f"  [뉴스/{kw}] {len(items)}건")
        for item in items:
            title = clean(item.get("title", ""))
            link  = item.get("originallink") or item.get("link", "")
            rank  = media_rank(link)
            tid   = article_id(title)
            if tid not in pool:
                pool[tid] = {"item": item, "keywords": [kw], "rank": rank}
            else:
                pool[tid]["keywords"].append(kw)
                if rank < pool[tid]["rank"]:
                    pool[tid]["item"] = item
                    pool[tid]["rank"] = rank

    sorted_articles = sorted(pool.values(), key=lambda x: x["rank"])
    return sorted_articles[:MAX_NEWS]


# ── 2. 사이트 스크래핑 ────────────────────────────────────────────────────────
def scrape_site(site: dict) -> list:
    """사이트에서 최신 링크+제목 추출"""
    results = []
    try:
        resp = requests.get(site["url"], timeout=10, headers=HEADERS)
        resp.raise_for_status()
        page = resp.text

        # <a href="...">제목</a> 패턴에서 기사 링크 추출
        links = re.findall(r'<a[^>]+href=["\']([^"\'#][^"\']*)["\'][^>]*>\s*([^<]{15,120})\s*</a>', page)

        seen_titles = set()
        base = re.match(r'https?://[^/]+', site["url"]).group(0)

        for href, title in links:
            title = clean(title).strip()
            if len(title) < 15:
                continue
            # 노동인권 관련 키워드 필터
            keywords_en = ["labor", "labour", "worker", "supply chain", "human rights",
                           "forced", "child", "factory", "union", "wage", "safety",
                           "samsung", "apple", "electronics", "mining", "carbon",
                           "environment", "due diligence", "ESG", "trade"]
            keywords_ko = ["노동", "인권", "공급망", "근로자", "강제", "아동", "공장", "임금", "안전"]
            combined = title.lower()
            is_relevant = any(kw in combined for kw in keywords_en + keywords_ko)
            if not is_relevant:
                continue

            # 절대 URL 변환
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = base + href
            else:
                continue

            title_id = article_id(title)
            if title_id in seen_titles:
                continue
            seen_titles.add(title_id)

            results.append({
                "title": title,
                "url":   full_url,
                "site":  site,
            })
            if len(results) >= MAX_SITE:
                break

    except Exception as e:
        print(f"  오류 [{site['name']}]: {e}")

    print(f"  [{site['name']}] {len(results)}건")
    return results

def collect_sites():
    all_results = []
    for site in MONITOR_SITES:
        all_results.extend(scrape_site(site))
    return all_results


# ── 3. HTML 생성 ──────────────────────────────────────────────────────────────
def build_html(news_articles: list, site_articles: list, date_str: str) -> str:
    total_news  = len(news_articles)
    total_sites = len(site_articles)

    # 키워드 카운터
    kw_counter = Counter()
    for a in news_articles:
        for kw in a["keywords"]:
            kw_counter[kw] += 1
    top5 = kw_counter.most_common(5)
    top3 = kw_counter.most_common(3)
    max_cnt = top5[0][1] if top5 else 1

    # 바 차트
    kw_bars = ""
    for kw, cnt in top5:
        pct   = int(cnt / max_cnt * 100)
        color = CATEGORY_COLOR.get(kw, "#6b7280")
        kw_bars += f"""
        <div style="margin-bottom:9px;">
          <div style="display:flex;justify-content:space-between;
                      font-size:12px;color:#374151;margin-bottom:3px;">
            <span>{kw}</span>
            <span style="font-weight:700;color:{color};">{cnt}건</span>
          </div>
          <div style="background:#e5e7eb;border-radius:4px;height:7px;">
            <div style="background:{color};width:{pct}%;height:7px;border-radius:4px;"></div>
          </div>
        </div>"""

    hot_tags = "".join([
        f'<span style="background:{CATEGORY_COLOR.get(kw,"#6b7280")};color:#fff;'
        f'font-size:11px;font-weight:700;padding:3px 11px;border-radius:20px;'
        f'margin:3px 3px 3px 0;display:inline-block;">#{kw}</span>'
        for kw, _ in top3
    ])

    # 뉴스 기사 카드
    news_html = ""
    for i, a in enumerate(news_articles, 1):
        item   = a["item"]
        title  = clean(item.get("title", ""))
        desc   = clean(item.get("description", ""))
        url    = item.get("originallink") or item.get("link", "#")
        pub    = fmt_date(item.get("pubDate", ""))
        kws    = list(dict.fromkeys(a["keywords"]))
        domain = get_domain(url)
        thumb  = get_thumbnail(url)

        kw_tags = "".join([
            f'<span style="background:{CATEGORY_COLOR.get(kw,"#6b7280")}18;'
            f'color:{CATEGORY_COLOR.get(kw,"#6b7280")};font-size:10px;font-weight:700;'
            f'padding:2px 8px;border-radius:12px;margin-right:4px;">{kw}</span>'
            for kw in kws[:3]
        ])

        if thumb:
            body = f"""
            <div style="display:flex;gap:14px;align-items:flex-start;">
              <img src="{thumb}" width="96" height="68"
                   style="border-radius:8px;object-fit:cover;flex-shrink:0;"
                   onerror="this.style.display='none'">
              <div style="flex:1;min-width:0;">
                <a href="{url}" target="_blank"
                   style="font-size:14px;font-weight:700;color:#111827;
                          text-decoration:none;line-height:1.5;display:block;
                          margin-bottom:5px;">{title}</a>
                <p style="font-size:12px;color:#6b7280;line-height:1.6;margin:0;">
                  {desc[:120]}{"..." if len(desc)>120 else ""}</p>
              </div>
            </div>"""
        else:
            body = f"""
            <a href="{url}" target="_blank"
               style="font-size:14px;font-weight:700;color:#111827;
                      text-decoration:none;line-height:1.5;display:block;
                      margin-bottom:5px;">{title}</a>
            <p style="font-size:12px;color:#6b7280;line-height:1.6;margin:0;">
              {desc[:180]}{"..." if len(desc)>180 else ""}</p>"""

        news_html += f"""
        <div style="background:#fff;border-radius:12px;padding:16px 18px;
                    margin-bottom:10px;border:1px solid #e8ecf4;
                    box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <div style="display:flex;align-items:center;margin-bottom:10px;gap:6px;">
            <span style="background:#1428a0;color:#fff;font-size:10px;
                         font-weight:700;padding:2px 8px;border-radius:4px;">#{i}</span>
            <span style="font-size:11px;color:#9ca3af;">{domain}</span>
            <span style="font-size:11px;color:#9ca3af;margin-left:auto;">{pub}</span>
          </div>
          {body}
          <div style="margin-top:10px;">{kw_tags}</div>
        </div>"""

    # 사이트 섹션 — 사이트별로 묶어서 표시
    sites_html = ""
    site_groups = {}
    for a in site_articles:
        name = a["site"]["name"]
        site_groups.setdefault(name, {"site": a["site"], "items": []})
        site_groups[name]["items"].append(a)

    for name, group in site_groups.items():
        site  = group["site"]
        items = group["items"]
        color = site["color"]
        icon  = site["icon"]

        items_html = ""
        for item in items:
            thumb = get_thumbnail(item["url"])
            if thumb:
                items_html += f"""
                <div style="display:flex;gap:12px;align-items:flex-start;
                            padding:12px 0;border-bottom:1px solid #f3f4f6;">
                  <img src="{thumb}" width="80" height="56"
                       style="border-radius:6px;object-fit:cover;flex-shrink:0;"
                       onerror="this.style.display='none'">
                  <div>
                    <a href="{item['url']}" target="_blank"
                       style="font-size:13px;font-weight:700;color:#111827;
                              text-decoration:none;line-height:1.5;display:block;">
                      {item['title']}</a>
                  </div>
                </div>"""
            else:
                items_html += f"""
                <div style="padding:10px 0;border-bottom:1px solid #f3f4f6;">
                  <a href="{item['url']}" target="_blank"
                     style="font-size:13px;font-weight:700;color:#111827;
                            text-decoration:none;line-height:1.5;display:block;">
                    {item['title']}</a>
                </div>"""

        sites_html += f"""
        <div style="background:#fff;border-radius:12px;padding:16px 18px;
                    margin-bottom:10px;border:1px solid #e8ecf4;
                    box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="font-size:16px;">{icon}</span>
            <span style="font-size:13px;font-weight:700;color:{color};">{name}</span>
            <a href="{site['url']}" target="_blank"
               style="font-size:11px;color:#9ca3af;margin-left:auto;text-decoration:none;">
              바로가기 →</a>
          </div>
          {items_html}
        </div>"""

    if not sites_html:
        sites_html = '<div style="color:#9ca3af;font-size:13px;padding:16px;">오늘 업데이트된 관련 콘텐츠가 없습니다.</div>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>공급망 노동인권 뉴스레터</title>
</head>
<body style="margin:0;padding:0;background:#f0f4ff;
             font-family:'Apple SD Gothic Neo','Noto Sans KR',Arial,sans-serif;">
<div style="max-width:680px;margin:0 auto;padding:24px 16px;">

  <!-- 헤더 -->
  <div style="background:linear-gradient(135deg,#1428a0 0%,#0a1172 100%);
              border-radius:16px;padding:32px;margin-bottom:16px;text-align:center;">
    <div style="display:inline-block;background:rgba(255,255,255,0.15);
                color:#a8c8ff;font-size:10px;font-weight:700;letter-spacing:2px;
                padding:4px 14px;border-radius:20px;margin-bottom:12px;">
      LABOR RIGHTS · SUPPLY CHAIN MONITORING
    </div>
    <div style="color:#fff;font-size:22px;font-weight:800;
                line-height:1.3;margin-bottom:6px;">공급망 노동인권 뉴스레터</div>
    <div style="color:#a8c8ff;font-size:13px;">{date_str}</div>
  </div>

  <!-- 대시보드 -->
  <div style="background:#fff;border-radius:16px;padding:22px;
              margin-bottom:16px;border:1px solid #e8ecf4;
              box-shadow:0 2px 8px rgba(0,0,0,0.06);">
    <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:16px;">
      📊 오늘의 뉴스 대시보드</div>
    <div style="display:flex;gap:10px;margin-bottom:20px;">
      <div style="flex:1;background:#f0f4ff;border-radius:10px;padding:14px;text-align:center;">
        <div style="font-size:26px;font-weight:800;color:#1428a0;">{total_news}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:2px;">언론 기사</div>
      </div>
      <div style="flex:1;background:#f0fdf4;border-radius:10px;padding:14px;text-align:center;">
        <div style="font-size:26px;font-weight:800;color:#059669;">{total_sites}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:2px;">단체 업데이트</div>
      </div>
      <div style="flex:1;background:#faf5ff;border-radius:10px;padding:14px;text-align:center;">
        <div style="font-size:26px;font-weight:800;color:#7c3aed;">{len(KEYWORDS)}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:2px;">모니터링 키워드</div>
      </div>
    </div>
    <div style="font-size:11px;font-weight:700;color:#9ca3af;
                margin-bottom:10px;text-transform:uppercase;letter-spacing:1px;">
      키워드별 기사 수</div>
    {kw_bars}
    <div style="margin-top:14px;">
      <div style="font-size:11px;font-weight:700;color:#9ca3af;margin-bottom:8px;">
        🔥 오늘의 핫 키워드</div>
      {hot_tags}
    </div>
  </div>

  <!-- 뉴스 기사 -->
  <div style="font-size:13px;font-weight:700;color:#374151;
              margin-bottom:10px;padding-left:2px;">
    📰 주요 언론 기사 TOP {total_news}
  </div>
  {news_html}

  <!-- 단체/기관 업데이트 -->
  <div style="font-size:13px;font-weight:700;color:#374151;
              margin:20px 0 10px;padding-left:2px;">
    🌐 노동인권 단체 최신 업데이트
  </div>
  {sites_html}

  <!-- 푸터 -->
  <div style="text-align:center;padding:20px;color:#9ca3af;font-size:11px;line-height:1.8;">
    <p>네이버 뉴스 API · Electronics Watch · Good Electronics · IndustriALL · Sherpa</p>
    <p>매일 오전 8시 자동 수집 발송 · {datetime.now().year} 공급망 노동인권 모니터링</p>
  </div>

</div>
</body>
</html>"""


# ── 4. Gmail SMTP 발송 ─────────────────────────────────────────────────────────
def send_email(subject: str, html_body: str):
    for to in RECIPIENTS:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = to
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, to, msg.as_string())
        print(f"  발송 완료 → {to}")


# ── 메인 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    today = datetime.now().strftime("%Y년 %m월 %d일")
    print(f"=== 공급망 노동인권 뉴스레터 시작: {today} ===")

    print("\n[1] 뉴스 수집 중...")
    news_articles = collect_news()
    print(f"  → 최종 {len(news_articles)}건")

    print("\n[2] 단체 사이트 수집 중...")
    site_articles = collect_sites()
    print(f"  → 최종 {len(site_articles)}건")

    if not news_articles and not site_articles:
        print("수집된 콘텐츠 없음 → 발송 건너뜀")
        exit(0)

    html_body = build_html(news_articles, site_articles, today)
    subject   = f"[공급망 노동인권] {today} 뉴스 {len(news_articles)}건 + 단체 {len(site_articles)}건"

    print("\n[3] 이메일 발송 중...")
    send_email(subject, html_body)
    print("=== 완료 ===")
