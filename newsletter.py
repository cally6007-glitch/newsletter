# -*- coding: utf-8 -*-
"""
공급망 노동인권 뉴스레터 v2
- 네이버 뉴스 API 다중 키워드 수집
- 중복 기사 빈도 높은 순 정렬
- 썸네일 + 대시보드
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
    "기업인권",
    "삼성 하청",
    "애플 하청",
    "강제노동 기업",
    "분쟁광물",
    "삼성 지속가능경영",
    "삼성 ESG",
    "탄소중립기본법",
    "탄소중립 기업",
    "공급망 실사",
    "아동 노동",
    "ILO",
    "forced labor",
    "위구르",
]
MAX_PER_KEYWORD = 5   # 키워드당 최대 수집
MAX_TOTAL       = 30  # 최종 노출 최대

NAVER_CLIENT_ID     = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
GMAIL_USER          = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD  = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENTS          = [r.strip() for r in os.environ["RECIPIENTS"].split(",") if r.strip()]

# 키워드 카테고리 색상
CATEGORY_COLOR = {
    "삼성전자 공급망": "#1428a0",
    "기업인권":        "#7c3aed",
    "삼성 하청":       "#1428a0",
    "애플 하청":       "#555555",
    "강제노동 기업":   "#dc2626",
    "분쟁광물":        "#b45309",
    "삼성 지속가능경영":"#1428a0",
    "삼성 ESG":        "#1428a0",
    "탄소중립기본법":  "#059669",
    "탄소중립 기업":   "#059669",
    "공급망 실사":     "#0891b2",
    "아동 노동":       "#dc2626",
    "ILO":             "#7c3aed",
    "forced labor":    "#dc2626",
    "위구르":          "#dc2626",
}


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def clean(text: str) -> str:
    text = html.unescape(text)
    return re.sub(r"<[^>]+>", "", text).strip()

def fmt_date(pub: str) -> str:
    try:
        return parsedate_to_datetime(pub).strftime("%Y.%m.%d %H:%M")
    except Exception:
        return pub

def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


# ── 1. 네이버 뉴스 수집 ────────────────────────────────────────────────────────
def fetch_news(keyword: str, display: int = 5):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id":     NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": display, "sort": "date"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as e:
        print(f"  오류 [{keyword}]: {e}")
        return []

def collect_all():
    # aid → {article, keywords:[], count}
    pool = {}
    for kw in KEYWORDS:
        items = fetch_news(kw, MAX_PER_KEYWORD)
        print(f"  [{kw}] {len(items)}건")
        for item in items:
            link = item.get("originallink") or item.get("link", "")
            aid  = article_id(link)
            if aid not in pool:
                pool[aid] = {"item": item, "keywords": [kw], "count": 1}
            else:
                pool[aid]["keywords"].append(kw)
                pool[aid]["count"] += 1

    # 중복 많은 순 → 날짜 최신 순 정렬
    sorted_articles = sorted(
        pool.values(),
        key=lambda x: (x["count"], x["item"].get("pubDate", "")),
        reverse=True
    )
    return sorted_articles[:MAX_TOTAL]


# ── 2. 썸네일 URL 추출 ────────────────────────────────────────────────────────
def get_thumbnail(url: str) -> str:
    """og:image 메타태그에서 썸네일 추출 (실패 시 기본 이미지)"""
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        match = re.search(r'og:image["\s]+content=["\']([^"\']+)["\']', r.text)
        if not match:
            match = re.search(r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', r.text)
        if match:
            img = match.group(1)
            if img.startswith("http"):
                return img
    except Exception:
        pass
    return ""


# ── 3. HTML 생성 ──────────────────────────────────────────────────────────────
def build_html(articles: list, date_str: str) -> str:

    # 대시보드 데이터
    total      = len(articles)
    duplicates = sum(1 for a in articles if a["count"] > 1)
    kw_counter = Counter()
    for a in articles:
        for kw in a["keywords"]:
            kw_counter[kw] += 1
    top_kw = kw_counter.most_common(3)

    # 키워드 바 차트 (상위 5개)
    top5 = kw_counter.most_common(5)
    max_cnt = top5[0][1] if top5 else 1
    kw_bars = ""
    for kw, cnt in top5:
        pct = int(cnt / max_cnt * 100)
        color = CATEGORY_COLOR.get(kw, "#6b7280")
        kw_bars += f"""
        <div style="margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;
                      font-size:12px;color:#374151;margin-bottom:3px;">
            <span>{kw}</span><span style="font-weight:700;">{cnt}건</span>
          </div>
          <div style="background:#e5e7eb;border-radius:4px;height:8px;">
            <div style="background:{color};width:{pct}%;height:8px;
                        border-radius:4px;"></div>
          </div>
        </div>"""

    # 오늘의 Top 키워드 태그
    top_kw_tags = "".join([
        f'<span style="background:{CATEGORY_COLOR.get(kw,"#6b7280")};color:#fff;'
        f'font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;'
        f'margin:3px 3px 3px 0;display:inline-block;">#{kw} {cnt}건</span>'
        for kw, cnt in top_kw
    ])

    # 기사 카드
    articles_html = ""
    for i, a in enumerate(articles, 1):
        item     = a["item"]
        title    = clean(item.get("title", ""))
        desc     = clean(item.get("description", ""))
        url      = item.get("originallink") or item.get("link", "#")
        pub      = fmt_date(item.get("pubDate", ""))
        keywords = a["keywords"]
        count    = a["count"]
        thumb    = get_thumbnail(url)

        # 키워드 태그들
        kw_tags = "".join([
            f'<span style="background:{CATEGORY_COLOR.get(kw,"#6b7280")}22;'
            f'color:{CATEGORY_COLOR.get(kw,"#6b7280")};font-size:10px;'
            f'font-weight:700;padding:2px 8px;border-radius:12px;margin-right:4px;">'
            f'{kw}</span>'
            for kw in keywords[:3]
        ])

        # 중복 배지
        dup_badge = ""
        if count > 1:
            dup_badge = f'<span style="background:#fef3c7;color:#d97706;font-size:10px;font-weight:700;padding:2px 8px;border-radius:12px;margin-left:6px;">🔥 {count}개 키워드</span>'

        # 썸네일 레이아웃
        if thumb:
            content_layout = f"""
            <div style="display:flex;gap:14px;align-items:flex-start;">
              <img src="{thumb}" alt="" width="100" height="70"
                   style="border-radius:8px;object-fit:cover;flex-shrink:0;
                          width:100px;height:70px;" onerror="this.style.display='none'">
              <div style="flex:1;min-width:0;">
                <a href="{url}" target="_blank"
                   style="font-size:14px;font-weight:700;color:#111827;
                          text-decoration:none;line-height:1.5;display:block;
                          margin-bottom:5px;">{title}</a>
                <p style="font-size:12px;color:#6b7280;line-height:1.6;margin:0;">
                  {desc[:120]}{"..." if len(desc)>120 else ""}
                </p>
              </div>
            </div>"""
        else:
            content_layout = f"""
            <a href="{url}" target="_blank"
               style="font-size:14px;font-weight:700;color:#111827;
                      text-decoration:none;line-height:1.5;display:block;
                      margin-bottom:5px;">{title}</a>
            <p style="font-size:12px;color:#6b7280;line-height:1.6;margin:0;">
              {desc[:180]}{"..." if len(desc)>180 else ""}
            </p>"""

        articles_html += f"""
        <div style="background:#fff;border-radius:12px;padding:16px 18px;
                    margin-bottom:10px;border:1px solid #e8ecf4;
                    box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <div style="display:flex;align-items:center;
                      margin-bottom:10px;flex-wrap:wrap;gap:4px;">
            <span style="background:#1428a0;color:#fff;font-size:10px;
                         font-weight:700;padding:2px 8px;border-radius:4px;">
              #{i}</span>
            {dup_badge}
            <span style="font-size:11px;color:#9ca3af;margin-left:auto;">{pub}</span>
          </div>
          {content_layout}
          <div style="margin-top:10px;">{kw_tags}</div>
        </div>"""

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
    <div style="color:#fff;font-size:22px;font-weight:800;line-height:1.3;
                margin-bottom:6px;">공급망 노동인권 뉴스레터</div>
    <div style="color:#a8c8ff;font-size:13px;">{date_str}</div>
  </div>

  <!-- 대시보드 -->
  <div style="background:#fff;border-radius:16px;padding:24px;
              margin-bottom:16px;border:1px solid #e8ecf4;
              box-shadow:0 2px 8px rgba(0,0,0,0.06);">
    <div style="font-size:13px;font-weight:700;color:#374151;
                margin-bottom:16px;">📊 오늘의 뉴스 대시보드</div>

    <!-- 숫자 요약 -->
    <div style="display:flex;gap:12px;margin-bottom:20px;">
      <div style="flex:1;background:#f0f4ff;border-radius:10px;padding:14px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#1428a0;">{total}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:2px;">수집 기사</div>
      </div>
      <div style="flex:1;background:#fef3c7;border-radius:10px;padding:14px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#d97706;">{duplicates}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:2px;">중복 언급</div>
      </div>
      <div style="flex:1;background:#f0fdf4;border-radius:10px;padding:14px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#059669;">{len(KEYWORDS)}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:2px;">모니터링 키워드</div>
      </div>
    </div>

    <!-- 키워드 바 차트 -->
    <div style="font-size:12px;font-weight:700;color:#6b7280;
                margin-bottom:10px;text-transform:uppercase;letter-spacing:1px;">
      키워드별 기사 수
    </div>
    {kw_bars}

    <!-- Top 키워드 -->
    <div style="margin-top:16px;">
      <div style="font-size:12px;font-weight:700;color:#6b7280;
                  margin-bottom:8px;">🔥 오늘의 핫 키워드</div>
      {top_kw_tags}
    </div>
  </div>

  <!-- 기사 목록 -->
  <div style="font-size:13px;font-weight:700;color:#374151;
              margin-bottom:12px;padding-left:4px;">
    📰 전체 기사 (중복 언급 많은 순)
  </div>
  {articles_html}

  <!-- 푸터 -->
  <div style="text-align:center;padding:20px;color:#9ca3af;font-size:11px;line-height:1.8;">
    <p>네이버 뉴스 API 자동 수집 · 매일 오전 8시 발송</p>
    <p>{datetime.now().year} 공급망 노동인권 모니터링</p>
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

    print("뉴스 수집 중...")
    articles = collect_all()
    print(f"최종 기사 수: {len(articles)}건")

    if not articles:
        print("수집된 기사 없음 → 발송 건너뜀")
        exit(0)

    html_body = build_html(articles, today)
    subject   = f"[공급망 노동인권] {today} 뉴스 {len(articles)}건"
    print("이메일 발송 중...")
    send_email(subject, html_body)
    print("=== 완료 ===")
