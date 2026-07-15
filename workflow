# -*- coding: utf-8 -*-
"""
삼성전자 공급망 노동인권 뉴스레터
- 네이버 뉴스 API로 기사 수집 (최대 20개)
- Gmail SMTP로 이메일 발송
- GitHub Actions로 매일 오전 8시 KST 자동 실행
"""

import os
import smtplib
import requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 설정 ──────────────────────────────────────────────────────────────────────
KEYWORD = "삼성전자 공급망"
MAX_ARTICLES = 20

NAVER_CLIENT_ID     = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
GMAIL_USER          = os.environ["GMAIL_USER"]      # 발송 Gmail 주소
GMAIL_APP_PASSWORD  = os.environ["GMAIL_APP_PASSWORD"]  # Gmail 앱 비밀번호
RECIPIENTS          = [r.strip() for r in os.environ["RECIPIENTS"].split(",") if r.strip()]


# ── 1. 네이버 뉴스 수집 ────────────────────────────────────────────────────────
def fetch_news(keyword: str, display: int = 20):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": display, "sort": "date"}
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    print(f"수집된 기사: {len(items)}건")
    return items


def clean(text: str) -> str:
    import html, re
    text = html.unescape(text)
    return re.sub(r"<[^>]+>", "", text).strip()


# ── 2. HTML 뉴스레터 생성 ──────────────────────────────────────────────────────
def build_html(items: list, date_str: str) -> str:
    articles_html = ""
    for i, item in enumerate(items, 1):
        title = clean(item.get("title", ""))
        desc  = clean(item.get("description", ""))
        url   = item.get("originallink") or item.get("link", "#")
        pub   = item.get("pubDate", "")
        # 날짜 포맷 정리
        try:
            from email.utils import parsedate_to_datetime
            pub = parsedate_to_datetime(pub).strftime("%Y.%m.%d %H:%M")
        except Exception:
            pass

        articles_html += f"""
        <div style="background:#fff;border-radius:12px;padding:18px 20px;
                    margin-bottom:12px;border:1px solid #e8ecf4;
                    box-shadow:0 1px 3px rgba(0,0,0,0.06);">
          <div style="font-size:11px;color:#9ca3af;margin-bottom:8px;">
            <span style="background:#1428a0;color:#fff;font-size:10px;
                         font-weight:700;padding:2px 8px;border-radius:4px;
                         margin-right:8px;">#{i}</span>
            {pub}
          </div>
          <a href="{url}" target="_blank"
             style="font-size:15px;font-weight:700;color:#1428a0;
                    text-decoration:none;line-height:1.5;display:block;
                    margin-bottom:7px;">{title}</a>
          <p style="font-size:13px;color:#6b7280;line-height:1.7;margin:0;">
            {desc[:180]}{"..." if len(desc) > 180 else ""}
          </p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>삼성전자 공급망 노동인권 뉴스레터</title>
</head>
<body style="margin:0;padding:0;background:#f0f4ff;
             font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;">
<div style="max-width:660px;margin:0 auto;padding:24px 16px;">

  <!-- 헤더 -->
  <div style="background:linear-gradient(135deg,#1428a0 0%,#0a1172 100%);
              border-radius:16px;padding:36px 32px;margin-bottom:20px;
              text-align:center;">
    <div style="display:inline-block;background:rgba(255,255,255,0.15);
                color:#a8c8ff;font-size:11px;font-weight:700;
                letter-spacing:2px;padding:5px 14px;border-radius:20px;
                margin-bottom:14px;">LABOR RIGHTS · SUPPLY CHAIN</div>
    <div style="color:#fff;font-size:24px;font-weight:800;
                line-height:1.3;margin-bottom:8px;">
      삼성전자 공급망 노동인권<br>뉴스레터
    </div>
    <div style="color:#a8c8ff;font-size:14px;">{date_str}</div>
    <div style="margin-top:18px;display:inline-block;
                background:rgba(255,255,255,0.12);border-radius:10px;
                padding:10px 24px;color:#fff;font-size:13px;">
      오늘의 기사
      <span style="font-size:22px;font-weight:800;display:block;
                   color:#7ec8e3;">{len(items)}건</span>
    </div>
  </div>

  <!-- 검색어 태그 -->
  <div style="background:#fff;border-radius:12px;padding:14px 18px;
              margin-bottom:20px;border:1px solid #e8ecf4;">
    <span style="font-size:11px;color:#9ca3af;font-weight:600;
                 text-transform:uppercase;letter-spacing:1px;">
      📌 검색 키워드 &nbsp;
    </span>
    <span style="background:#e8f0fe;color:#1428a0;font-size:12px;
                 font-weight:700;padding:3px 12px;border-radius:20px;">
      삼성전자 공급망
    </span>
  </div>

  <!-- 기사 목록 -->
  {articles_html}

  <!-- 푸터 -->
  <div style="text-align:center;padding:20px;color:#9ca3af;font-size:12px;
              line-height:1.8;">
    <p>본 뉴스레터는 네이버 뉴스 API를 통해 자동 수집됩니다.</p>
    <p>매일 오전 8시 발송 · {datetime.now().year} 삼성전자 공급망 노동인권 모니터링</p>
  </div>

</div>
</body>
</html>"""


# ── 3. Gmail SMTP 발송 ─────────────────────────────────────────────────────────
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
        print(f"발송 완료 → {to}")


# ── 메인 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    today = datetime.now().strftime("%Y년 %m월 %d일")
    print(f"=== 뉴스레터 시작: {today} ===")

    items = fetch_news(KEYWORD, MAX_ARTICLES)
    if not items:
        print("수집된 기사 없음 → 발송 건너뜀")
        exit(0)

    html  = build_html(items, today)
    subject = f"[삼성전자 공급망] {today} 노동인권 뉴스 {len(items)}건"
    send_email(subject, html)
    print("=== 완료 ===")
