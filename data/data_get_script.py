# -*- coding: utf-8 -*-
"""
気象庁「過去の気象データ・ダウンロード」(obsdl) から
熱中症リスク(WBGT)・降雨分析に使うための時別値をまとめて取得するスクリプト。

取得要素(時別値):
    気温 / 相対湿度 / 全天日射量 / 日照時間 / 雲量 /
    風向 / 風速 / 蒸気圧 / 露点温度 / 降水量

取得地点:
    県庁所在地だけでなく、これらの要素を観測している「気象官署」全地点を
    obsdl の地点一覧から自動取得する(STATION_MODE で切替可)。
    ※ 日射量・雲量・蒸気圧・露点温度などのフルセットを観測するのは
      基本的に気象官署(stid が "s" で始まる)だけ。アメダス(stid が "a")は
      気温・降水量・風・日照などの一部のみで、それ以外の列は空欄になる。

依存: 標準ライブラリのみ(requests / pandas 不要)。`python data_get_script.py` で実行。
出力: data/observations.csv(観測値・ロング形式) と data/stations.csv(地点マスタ)
"""

import csv
import io
import re
import ssl
import time
import http.cookiejar
import urllib.request
import urllib.parse
import urllib.error
import datetime as dt
from pathlib import Path


# ====================== 設定(ここだけ変えればOK) ======================

# 取得期間(両端を含む)。2025年8月前半=8/1〜8/15。
START_DATE = dt.date(2025, 8, 1)
END_DATE   = dt.date(2025, 8, 15)

# 取得する地点の種類:
#   "kansho" … 気象官署(stid="s..")。日射・雲量・蒸気圧・露点まで含むフルセット【既定】
#   "all"    … 官署＋アメダス(全地点)。アメダスは未観測要素が空欄になる
#   "amedas" … アメダスのみ
STATION_MODE = "kansho"

# 取得要素(時別値の要素番号)。風向・風速(301)は1要素で両方返る。
#   201=気温, 101=降水量, 605=相対湿度, 610=全天日射量, 401=日照時間,
#   607=雲量, 301=風向・風速, 604=蒸気圧, 612=露点温度
ELEMENT_CODES = ["201", "101", "605", "610", "401", "607", "301", "604", "612"]

# 集計粒度: 9=時別値(1時間ごと)
AGGRG_PERIOD = 9

# サーバー負荷配慮のリクエスト間隔(秒)。気象庁は過度な自動アクセスを禁止しているため必須。
REQUEST_INTERVAL = 1.2

# SSL証明書を検証するか。社内プロキシ等で検証に失敗する場合は自動で無検証へ切替える。
VERIFY_SSL = True

OUT_DIR = Path(__file__).resolve().parent

ROOT = "https://www.data.jma.go.jp/risk/obsdl/"
INDEX_URL   = ROOT + "index.php"
STATION_URL = ROOT + "top/station"
TABLE_URL   = ROOT + "show/table"
UA = "Mozilla/5.0 (study project; weather heatstroke analysis)"

# =====================================================================


# obsdl CSV ヘッダの要素名 → 出力カラム名
NAME2KEY = {
    "気温": "temp",
    "降水量": "precip",
    "相対湿度": "humidity",
    "日射量": "solar",        # 全天日射量(610)はヘッダ上 "日射量(MJ/m2)"
    "日照時間": "sunshine",
    "雲量": "cloud",
    "風速": "wind_speed",     # 風向は別カラム(下のサブ見出しで判定)
    "蒸気圧": "vapor_pressure",
    "露点温度": "dew_point",
}
# 出力カラムの並び(風向は wind_dir として別途追加)
VALUE_KEYS = [
    "temp", "precip", "humidity", "solar", "sunshine",
    "cloud", "wind_dir", "wind_speed", "vapor_pressure", "dew_point",
]
# 文字列のまま保持する要素(数値化しない)
STR_KEYS = {"wind_dir", "cloud"}
# ヘッダのサブ行に現れる「値ではない」補助列のラベル
AUX_LABELS = {"品質情報", "均質番号", "現象なし情報", "信頼性ランク", "備考"}

DATE_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}")


# --------------------------- セッション ---------------------------

def make_opener(verify: bool):
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(cj),
    )
    opener.addheaders = [("User-Agent", UA)]
    return opener


def open_session():
    """index.php を開いてセッションクッキー(ci_session)を確立。
    証明書検証に失敗したら無検証で再試行する。"""
    global VERIFY_SSL
    for verify in ([True, False] if VERIFY_SSL else [False]):
        opener = make_opener(verify)
        try:
            opener.open(INDEX_URL, timeout=30)
            if not verify:
                print("[warn] SSL証明書の検証に失敗したため無検証で接続します。")
            return opener
        except urllib.error.URLError as e:
            if "CERTIFICATE" in str(e.reason).upper() or isinstance(e.reason, ssl.SSLError):
                continue
            raise
    raise RuntimeError("obsdl に接続できませんでした。")


def post(opener, url, data, timeout=60):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body)
    req.add_header("Referer", INDEX_URL)
    return opener.open(req, timeout=timeout).read()


# --------------------------- 地点一覧の取得 ---------------------------

# class="station ..." の地点ブロック(緯度経度・標高は title 属性内)
ST_BLOCK_RE = re.compile(
    r'<div[^>]*class="station([^"]*)"[^>]*title="(.*?)"[^>]*>(.*?)</div>', re.S
)


def _dms(deg, minute):
    return round(int(deg) + float(minute) / 60.0, 4)


def fetch_station_master(opener):
    """obsdl から全地点を取得し、STATION_MODE でフィルタした地点リストを返す。
    各要素: dict(station_id, name, lat, lon, elev, prid, kansoku, type)"""
    pref_html = post(opener, STATION_URL, {"pd": "00"}).decode("utf-8", "replace")
    prids = sorted(set(re.findall(r'name="prid"\s+value="(\d+)"', pref_html)), key=int)

    seen = {}
    for prid in prids:
        html = post(opener, STATION_URL, {"pd": prid}).decode("utf-8", "replace")
        for m in ST_BLOCK_RE.finditer(html):
            cls, title, inner = m.group(1), m.group(2), m.group(3)
            sid_m = re.search(r'name="stid"\s+value="([^"]+)"', inner)
            if not sid_m:
                continue
            sid = sid_m.group(1)
            if sid in seen:
                continue
            if "owata" in cls:          # 観測終了地点は除外
                continue
            name_m = re.search(r'name="stname"\s+value="([^"]*)"', inner)
            kan_m  = re.search(r'name="kansoku"\s+value="([^"]*)"', inner)
            la = re.search(r"北緯[：:]\s*([\d.]+)度([\d.]+)分", title)
            lo = re.search(r"東経[：:]\s*([\d.]+)度([\d.]+)分", title)
            el = re.search(r"標高[：:]\s*(-?[\d.]+)\s*m", title)
            seen[sid] = {
                "station_id": sid,
                "name": name_m.group(1) if name_m else "",
                "lat": _dms(*la.groups()) if la else None,
                "lon": _dms(*lo.groups()) if lo else None,
                "elev": float(el.group(1)) if el else None,
                "prid": prid,
                "kansoku": kan_m.group(1) if kan_m else "",
                "type": "官署" if sid.startswith("s") else "アメダス",
            }
        time.sleep(0.3)

    stations = list(seen.values())
    if STATION_MODE == "kansho":
        stations = [s for s in stations if s["station_id"].startswith("s")]
    elif STATION_MODE == "amedas":
        stations = [s for s in stations if s["station_id"].startswith("a")]
    # "all" はそのまま
    stations.sort(key=lambda s: s["station_id"])
    return stations


# --------------------------- 観測値の取得 ---------------------------

def fetch_station_csv(opener, station_id):
    """1地点ぶん(期間=START_DATE〜END_DATE)のCSVテキストを返す。"""
    elem = "[" + ",".join(f'["{c}",""]' for c in ELEMENT_CODES) + "]"
    s, e = START_DATE, END_DATE
    payload = {
        "stationNumList": f'["{station_id}"]',
        "aggrgPeriod": AGGRG_PERIOD,
        "elementNumList": elem,
        "interAnnualType": 1,                       # 1=連続した期間
        # [開始年, 終了年, 開始月, 終了月, 開始日, 終了日]
        "ymdList": f'["{s.year}","{e.year}","{s.month}","{e.month}","{s.day}","{e.day}"]',
        "optionNumList": "[]",
        "downloadFlag": "true",
        "rmkFlag": 0,            # 品質情報・均質番号の列を付けない(パース簡略化)
        "disconnectFlag": 0,
        "youbiFlag": 0,
        "fukenFlag": 0,
        "kijiFlag": 0,
        "csvFlag": 1,            # すべて数値で格納
        "jikantaiFlag": 0,
        "jikantaiList": "[1,24]",
        "ymdLiteral": 1,
    }
    raw = post(opener, TABLE_URL, payload)
    return raw.decode("shift_jis", errors="replace")


def parse_csv(text):
    """obsdl の時別値CSVをパースして [{datetime, temp, precip, ...}, ...] を返す。

    ヘッダは複層(要素名 / サブ見出し / 補助列ラベル)。
    - "年月日時" で始まる行を要素名行(H1)とする
    - 続く日付以外の行をサブ見出しとして各列の役割を判定
      ・サブに "風向" → wind_dir 列
      ・サブに 補助ラベル(品質情報/均質番号/現象なし情報) → 値ではないので無視
      ・それ以外 → 要素名(単位除去)を NAME2KEY で出力カラムへ対応付け
    """
    rows = list(csv.reader(io.StringIO(text)))

    hidx = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == "年月日時":
            hidx = i
            break
    if hidx is None:
        return []

    h1 = rows[hidx]
    subrows = []
    j = hidx + 1
    while j < len(rows) and not (rows[j] and DATE_RE.match(rows[j][0])):
        subrows.append(rows[j])
        j += 1
    data_start = j

    colmap = {}  # 列index -> 出力キー
    for c in range(1, len(h1)):
        subs = [sr[c].strip() for sr in subrows if c < len(sr)]
        if "風向" in subs:
            colmap[c] = "wind_dir"
            continue
        if any(s in AUX_LABELS for s in subs):
            continue
        base = re.split(r"[(（]", h1[c].strip())[0].strip()
        key = NAME2KEY.get(base)
        if key:
            colmap[c] = key

    out = []
    for row in rows[data_start:]:
        if not row or not DATE_RE.match(row[0]):
            continue
        try:
            ts = dt.datetime.strptime(row[0].strip(), "%Y/%m/%d %H:%M:%S")
        except ValueError:
            try:
                ts = dt.datetime.strptime(row[0].strip(), "%Y/%m/%d %H:%M")
            except ValueError:
                continue
        rec = {"datetime": ts.strftime("%Y-%m-%d %H:%M:%S")}
        for c, key in colmap.items():
            val = row[c].strip() if c < len(row) else ""
            if key in STR_KEYS:
                rec[key] = val
            else:
                try:
                    rec[key] = float(val)
                except ValueError:
                    rec[key] = None
        out.append(rec)
    return out


# --------------------------- メイン ---------------------------

def main():
    OUT_DIR.mkdir(exist_ok=True)
    opener = open_session()

    print(f"[1/3] 地点一覧を取得中(mode={STATION_MODE}) ...")
    stations = fetch_station_master(opener)
    print(f"      対象 {len(stations)} 地点")

    print(f"[2/3] 観測値を取得中({START_DATE}〜{END_DATE}, 時別) ...")
    obs_rows = []
    for idx, st in enumerate(stations, 1):
        sid, name = st["station_id"], st["name"]
        try:
            text = fetch_station_csv(opener, sid)
            parsed = parse_csv(text)
            if not parsed:
                print(f"  [warn] {name}({sid}): データなし")
            for rec in parsed:
                row = {"datetime": rec["datetime"], "station_id": sid, "name": name}
                for k in VALUE_KEYS:
                    row[k] = rec.get(k)
                obs_rows.append(row)
            print(f"  [{idx}/{len(stations)}] {name}({sid}): {len(parsed)} 行")
        except Exception as ex:
            print(f"  [error] {name}({sid}): {ex}")
        time.sleep(REQUEST_INTERVAL)

    print("[3/3] CSV 出力中 ...")
    obs_path = OUT_DIR / "observations.csv"
    obs_cols = ["datetime", "station_id", "name"] + VALUE_KEYS
    obs_rows.sort(key=lambda r: (r["datetime"], r["station_id"]))
    with open(obs_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=obs_cols)
        w.writeheader()
        w.writerows(obs_rows)

    st_path = OUT_DIR / "stations.csv"
    st_cols = ["station_id", "name", "lat", "lon", "elev", "prid", "kansoku", "type"]
    with open(st_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=st_cols)
        w.writeheader()
        w.writerows(stations)

    print(f"\n完了: {len(obs_rows)} 行を {obs_path} に出力")
    print(f"      {len(stations)} 地点を {st_path} に出力")


if __name__ == "__main__":
    main()
