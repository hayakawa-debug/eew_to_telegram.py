# eew_to_telegram.py
import os
import time
import json
import html
import requests
import xml.etree.ElementTree as ET

# ==== 設定 ====
FEED_URL = "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml"  # 地震火山（高頻度）
EEW_KEYWORDS = ("緊急地震速報（予報", "緊急地震速報（警報", "緊急地震速報（地震動予報")
POLL_INTERVAL_SEC = 10  # ポーリング間隔（短くしすぎない）
STATE_FILE = "./seen_ids.json"  # 既読IDの保存先

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# ==== 既読管理 ====
def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)

# ==== Telegram 送信 ====
def send_telegram(text):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",  # 太字など軽い整形用
        "disable_web_page_preview": True,
    }
    r = requests.post(TG_API, json=payload, timeout=10)
    r.raise_for_status()

# ==== Atom フィード取得＆解析（標準ライブラリで） ====
def fetch_feed_entries():
    r = requests.get(FEED_URL, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    # Atom 名前空間を意識せずに { * } で拾う
    entries = []
    for e in root.findall(".//{*}entry"):
        title = (e.findtext("{*}title") or "").strip()
        id_ = (e.findtext("{*}id") or "").strip()
        updated = (e.findtext("{*}updated") or "").strip()
        link_el = e.find("{*}link")
        href = link_el.get("href") if link_el is not None else None
        entries.append({"title": title, "id": id_, "updated": updated, "href": href})
    return entries

# ==== EEW 本文XMLから要点抽出 ====
def fetch_and_summarize_xml(xml_url):
    r = requests.get(xml_url, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    # Head 要素（タイトル・発表時刻・見出し）
    title = root.findtext(".//{*}Title") or ""
    report_time = root.findtext(".//{*}ReportDateTime") or ""
    headline = root.findtext(".//{*}Headline//{*}Text") or ""

    # あると嬉しい追加情報（あるものだけ）
    serial = root.findtext(".//{*}Serial") or ""           # 第x報 等
    info_type = root.findtext(".//{*}InfoType") or ""      # 発表/訂正/取消
    target_time = root.findtext(".//{*}TargetDateTime") or ""  # 基点時刻

    # 震源・規模（EEWでは入らない場合もある）
    hypocenter = root.findtext(".//{*}Hypocenter//{*}Name") or ""
    magnitude = root.findtext(".//{*}Magnitude") or ""
    maxint = root.findtext(".//{*}Intensity//{*}MaxInt") or ""

    # 簡易整形（存在する項目だけ並べる）
    lines = []
    if title:        lines.append(f"<b>{html.escape(title)}</b>")
    if serial:       lines.append(f"・報号: {html.escape(serial)}")
    if info_type:    lines.append(f"・種別: {html.escape(info_type)}")
    if report_time:  lines.append(f"・発表: {html.escape(report_time)}")
    if target_time:  lines.append(f"・基点: {html.escape(target_time)}")
    if hypocenter:   lines.append(f"・震源: {html.escape(hypocenter)}")
    if magnitude:    lines.append(f"・M: {html.escape(magnitude)}")
    if maxint:       lines.append(f"・最大震度: {html.escape(maxint)}")
    if headline:     lines.append("\n" + html.escape(headline))

    if not lines:
        # 最低限URLだけでも
        lines = [f"<b>緊急地震速報</b>", f"{html.escape(xml_url)}"]

    return "\n".join(lines)

def is_eew(title: str) -> bool:
    return any(k in title for k in EEW_KEYWORDS)

def main():
    seen = load_seen()

    while True:
        try:
            entries = fetch_feed_entries()
            # 新しいものから処理したいときは updated で降順にする等も可
            for en in entries:
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
        except Exception as e:
            # 落ちないように軽くログ
            print("Error:", e)
        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()
