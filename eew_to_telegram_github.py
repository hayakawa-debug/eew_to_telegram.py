import os
import json
import html
import requests
import xml.etree.ElementTree as ET
import subprocess

# --- 設定 ---
# 監視対象フィードを複数に
FEED_URLS = [
    "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml",  # 全般
    "https://www.data.jma.go.jp/developer/xml/data/VXSE51.xml", # EEW 予報・警報
    "https://www.data.jma.go.jp/developer/xml/data/VXSE52.xml", # EEW 地震動予報
]
def fetch_feed_entries():
    entries = []
    for url in FEED_URLS:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for e in root.findall(".//{*}entry"):
            title = (e.findtext("{*}title") or "").strip()
            id_ = (e.findtext("{*}id") or "").strip()
            link_el = e.find("{*}link")
            href = link_el.get("href") if link_el is not None else None
            entries.append({"title": title, "id": id_, "href": href})
    return entries
EEW_KEYWORDS = ("緊急地震速報",)  # タイトルに含まれる文字列で簡易判定
STATE_FILE = "./seen_ids.json"

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# --- 既読管理 ---
def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)
    # GitHub に push
    subprocess.run(["git", "config", "user.name", "github-actions"])
    subprocess.run(["git", "config", "user.email", "actions@github.com"])
    subprocess.run(["git", "add", STATE_FILE])
    subprocess.run(["git", "commit", "-m", "update seen_ids"], check=False)
    subprocess.run(["git", "push"], check=False)

# --- Telegram 送信 ---
def send_telegram(text):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(TG_API, json=payload, timeout=10)
    r.raise_for_status()

# --- Atom フィード取得 ---
def fetch_feed_entries():
    r = requests.get(FEED_URL, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    entries = []
    for e in root.findall(".//{*}entry"):
        title = (e.findtext("{*}title") or "").strip()
        id_ = (e.findtext("{*}id") or "").strip()
        link_el = e.find("{*}link")
        href = link_el.get("href") if link_el is not None else None
        entries.append({"title": title, "id": id_, "href": href})
    return entries

# --- XML 本文要約 ---
def fetch_and_summarize_xml(xml_url):
    r = requests.get(xml_url, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    title = root.findtext(".//{*}Title") or ""
    report_time = root.findtext(".//{*}ReportDateTime") or ""
    headline = root.findtext(".//{*}Headline//{*}Text") or ""

    lines = []
    if title:       lines.append(f"<b>{html.escape(title)}</b>")
    if report_time: lines.append(f"・発表: {html.escape(report_time)}")
    if headline:    lines.append("\n" + html.escape(headline))
    if not lines:
        lines = [f"<b>緊急地震速報</b>", xml_url]
    return "\n".join(lines)

def is_eew(title: str) -> bool:
    return any(k in title for k in EEW_KEYWORDS)

def main():
    seen = load_seen()
    entries = fetch_feed_entries()

    for en in entries:
        print("Feed entry:", en["title"])  # ログ出力で確認
        if not en["href"] or not en["id"]:
            continue
        if en["id"] in seen:
            continue
        if not is_eew(en["title"]):
            continue

        summary = fetch_and_summarize_xml(en["href"])
        send_telegram(summary)
        seen.add(en["id"])

    save_seen(seen)

if __name__ == "__main__":
    main()
send_telegram("GitHub Actions EEW Bot: テスト送信 OK")
