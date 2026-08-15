#!/usr/bin/env python3
"""
主要11通貨の政策金利を BIS (Central bank policy rates, WS_CBPOL) から取得し
data/rates.json を生成する。

- 一次データ : BIS SDMX RESTful API (日次系列)
- 手動上書き : overrides.json （会合直後などBISの反映を待てないとき用）
- 依存関係なし（標準ライブラリのみ）。GitHub Actions で毎日実行する想定。
"""

import csv
import io
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "rates.json")
OVERRIDES = os.path.join(ROOT, "overrides.json")

JST = timezone(timedelta(hours=9))

# 通貨コード -> (BISの参照地域コード, 国名, 中銀/金利名, 公式ページ)
CURRENCIES = [
    ("USD", "US", "米国",             "FRB / FF金利誘導目標",
     "https://www.federalreserve.gov/monetarypolicy/openmarket.htm"),
    ("EUR", "XM", "ユーロ圏",         "ECB / 政策金利",
     "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html"),
    ("JPY", "JP", "日本",             "日銀 / 無担保コールO/N",
     "https://www.boj.or.jp/mopo/mpmdeci/index.htm"),
    ("GBP", "GB", "英国",             "BOE / バンクレート",
     "https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate"),
    ("AUD", "AU", "オーストラリア",   "RBA / キャッシュレート",
     "https://www.rba.gov.au/statistics/cash-rate/"),
    ("NZD", "NZ", "ニュージーランド", "RBNZ / OCR",
     "https://www.rbnz.govt.nz/monetary-policy"),
    ("CAD", "CA", "カナダ",           "BOC / 翌日物金利",
     "https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/"),
    ("CHF", "CH", "スイス",           "SNB / SNB政策金利",
     "https://www.snb.ch/en/"),
    ("ZAR", "ZA", "南アフリカ",       "SARB / レポレート",
     "https://www.resbank.co.za/en/home/what-we-do/monetary-policy"),
    ("TRY", "TR", "トルコ",           "CBRT / 1週間レポ金利",
     "https://www.tcmb.gov.tr/"),
    ("MXN", "MX", "メキシコ",         "Banxico / 翌日物金利目標",
     "https://www.banxico.org.mx/"),
]

AREAS = "+".join(a for _, a, *_ in CURRENCIES)
# 過去2年分あれば「前回変更日」を復元できる
START = (datetime.now(timezone.utc) - timedelta(days=760)).strftime("%Y-%m-%d")
BIS_URL = (
    "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/"
    f"D.{AREAS}?startPeriod={START}&format=csv"
)


def http_get(url, timeout=90):
    req = urllib.request.Request(url, headers={
        "User-Agent": "policy-rate-board/1.0 (personal dashboard)",
        "Accept": "text/csv, */*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def pick(header, *candidates):
    """CSVの列名ゆれを吸収する。"""
    low = {h.lower().strip(): h for h in header}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    for c in candidates:
        for k, v in low.items():
            if c.lower() in k:
                return v
    return None


def parse_bis(text):
    """{area: [(date, value), ...]} を日付昇順で返す。"""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("BIS応答にヘッダがありません")
    c_area = pick(reader.fieldnames, "REF_AREA", "ref_area")
    c_time = pick(reader.fieldnames, "TIME_PERIOD", "time_period")
    c_val = pick(reader.fieldnames, "OBS_VALUE", "obs_value")
    if not all([c_area, c_time, c_val]):
        raise ValueError(f"想定した列が見つかりません: {reader.fieldnames[:12]}")

    series = {}
    for row in reader:
        raw = (row.get(c_val) or "").strip()
        if raw in ("", "NaN", "NA"):
            continue
        try:
            v = float(raw)
        except ValueError:
            continue
        # "JP: Japan" のような表記も来るので先頭コードだけ取る
        area = (row.get(c_area) or "").split(":")[0].strip()
        t = (row.get(c_time) or "").strip()
        if not area or not t:
            continue
        series.setdefault(area, []).append((t, v))

    for a in series:
        series[a].sort(key=lambda x: x[0])
    return series


def last_change(points):
    """直近の値と、その値になった最初の日付（＝前回変更日）を返す。"""
    if not points:
        return None, None
    latest_date, latest_val = points[-1]
    changed_on = latest_date
    for d, v in reversed(points):
        if abs(v - latest_val) < 1e-9:
            changed_on = d
        else:
            break
    return latest_val, changed_on


def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[warn] {path} を読めません: {e}", file=sys.stderr)
        return {}


def main():
    overrides = load_json(OVERRIDES)
    previous = load_json(OUT)
    prev_rows = {r["code"]: r for r in previous.get("rows", [])}

    series, bis_ok, bis_error = {}, False, None
    try:
        series = parse_bis(http_get(BIS_URL))
        bis_ok = True
    except Exception as e:
        bis_error = f"{type(e).__name__}: {e}"
        print(f"[warn] BIS取得に失敗: {bis_error}", file=sys.stderr)

    rows, missing = [], []
    for code, area, country, cb, url in CURRENCIES:
        rate, changed = last_change(series.get(area, []))
        source = "BIS"

        if rate is None:                       # BIS未取得 → 前回値を維持
            prev = prev_rows.get(code)
            if prev:
                rate, changed, source = prev["rate"], prev.get("changed_on"), "前回値"
            missing.append(code)

        row = {
            "code": code, "country": country, "cb": cb, "url": url,
            "rate": rate, "label": None if rate is None else f"{rate:.2f}",
            "changed_on": changed, "source": source, "note": None,
        }

        ov = overrides.get(code)
        if isinstance(ov, dict):               # 手動上書きが最優先
            if "rate" in ov:
                row["rate"] = float(ov["rate"])
                row["label"] = ov.get("label") or f"{float(ov['rate']):.2f}"
            if ov.get("label"):
                row["label"] = ov["label"]
            if ov.get("changed_on"):
                row["changed_on"] = ov["changed_on"]
            row["note"] = ov.get("note")
            row["source"] = "手動"

        rows.append(row)

    rows = [r for r in rows if r["rate"] is not None]
    rows.sort(key=lambda r: -r["rate"])

    if not rows:
        # 1通貨も取れないときは既存ファイルを壊さずに失敗させる
        print("[error] 有効なデータが0件でした。data/rates.json は更新しません。",
              file=sys.stderr)
        return 1

    now = datetime.now(JST)
    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_at_display": now.strftime("%Y-%m-%d %H:%M JST"),
        "primary_source": "BIS Central bank policy rates (WS_CBPOL)",
        "primary_source_url": "https://www.bis.org/statistics/cbpol.htm",
        "bis_ok": bis_ok,
        "bis_error": bis_error,
        "missing": missing,
        "rows": rows,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"{len(rows)}通貨を書き出しました -> {OUT}")
    for r in rows:
        print(f"  {r['code']:>4} {r['rate']:>7.2f}%  {r['changed_on']}  ({r['source']})")
    if missing:
        print(f"[warn] BISから取得できなかった通貨: {', '.join(missing)}", file=sys.stderr)
    # BISが落ちていても前回値で site は成立するので、非ゼロ終了はしない
    return 0


if __name__ == "__main__":
    sys.exit(main())
