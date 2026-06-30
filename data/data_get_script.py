import csv
import io
import re
import time
import datetime as dt

import requests

START_DATE = dt.date(2025, 8, 1)
END_DATE   = dt.date(2025, 8, 15)


#   "kansho" … 気象官署
#   "all"    … 官署＋アメダス(全地点)。
#   "amedas" … アメダスのみ
STATION_MODE = "kansho"

#   201=気温, 101=降水量, 605=相対湿度, 610=全天日射量, 401=日照時間,
#   607=雲量, 301=風向・風速, 604=蒸気圧, 612=露点温度
ELEMENT_CODES = ["201", "101", "605", "610", "401", "607", "301", "604", "612"]

# 集計粒度: 9=時別値(1時間ごと)
AGGRG_PERIOD = 9

REQUEST_INTERVAL = 1.2

ROOT = "https://www.data.jma.go.jp/risk/obsdl/"
INDEX_URL   = ROOT + "index.php"
STATION_URL = ROOT + "top/station"
TABLE_URL   = ROOT + "show/table"
UA = "Mozilla/5.0 (study project; weather heatstroke analysis)"


NAME2KEY = {
    "気温": "temp",
    "降水量": "precip",
    "相対湿度": "humidity",
    "日射量": "solar",
    "日照時間": "sunshine",
    "雲量": "cloud",
    "風速": "wind_speed",  
    "蒸気圧": "vapor_pressure",
    "露点温度": "dew_point",
}

VALUE_KEYS = [
    "temp", "precip", "humidity", "solar", "sunshine",
    "cloud", "wind_dir", "wind_speed", "vapor_pressure", "dew_point",
]

STR_KEYS = {"wind_dir", "cloud"}

AUX_LABELS = {"品質情報", "均質番号", "現象なし情報", "信頼性ランク", "備考"}

DATE_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}")


def open_session():
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": INDEX_URL})
    sess.get(INDEX_URL, timeout=30).raise_for_status()
    return sess

def post(sess, url, data, timeout=60):
    resp = sess.post(url, data=data, timeout=timeout)
    resp.raise_for_status()
    return resp.content

ST_BLOCK_RE = re.compile(
    r'<div[^>]*class="station([^"]*)"[^>]*title="(.*?)"[^>]*>(.*?)</div>', re.S
)


def _dms(deg, minute):
    return round(int(deg) + float(minute) / 60.0, 4)


def fetch_station_master(sess):
    pref_html = post(sess, STATION_URL, {"pd": "00"}).decode("utf-8", "replace")
    prids = sorted(set(re.findall(r'name="prid"\s+value="(\d+)"', pref_html)), key=int)

    seen = {}
    for prid in prids:
        html = post(sess, STATION_URL, {"pd": prid}).decode("utf-8", "replace")
        for m in ST_BLOCK_RE.finditer(html):
            cls, title, inner = m.group(1), m.group(2), m.group(3)
            sid_m = re.search(r'name="stid"\s+value="([^"]+)"', inner)
            if not sid_m:
                continue
            sid = sid_m.group(1)
            if sid in seen:
                continue
            if "owata" in cls:
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
    stations.sort(key=lambda s: s["station_id"])
    return stations

def fetch_station_csv(sess, station_id):
    elem = "[" + ",".join(f'["{c}",""]' for c in ELEMENT_CODES) + "]"
    s, e = START_DATE, END_DATE
    payload = {
        "stationNumList": f'["{station_id}"]',
        "aggrgPeriod": AGGRG_PERIOD,
        "elementNumList": elem,
        "interAnnualType": 1,
        "ymdList": f'["{s.year}","{e.year}","{s.month}","{e.month}","{s.day}","{e.day}"]',
        "optionNumList": "[]",
        "downloadFlag": "true",
        "rmkFlag": 0,
        "disconnectFlag": 0,
        "youbiFlag": 0,
        "fukenFlag": 0,
        "kijiFlag": 0,
        "csvFlag": 1,
        "jikantaiFlag": 0,
        "jikantaiList": "[1,24]",
        "ymdLiteral": 1,
    }
    raw = post(sess, TABLE_URL, payload)
    return raw.decode("shift_jis", errors="replace")


def parse_csv(text):
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

    colmap = {}
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

def main():
    sess = open_session()
    stations = fetch_station_master(sess)

    obs_rows = []
    for idx, st in enumerate(stations, 1):
        sid, name = st["station_id"], st["name"]
        try:
            text = fetch_station_csv(sess, sid)
            parsed = parse_csv(text)
            for rec in parsed:
                row = {"datetime": rec["datetime"], "station_id": sid, "name": name}
                for k in VALUE_KEYS:
                    row[k] = rec.get(k)
                obs_rows.append(row)
        except Exception as ex:
            print(f"  [error] {name}({sid}): {ex}")
        time.sleep(REQUEST_INTERVAL)

    
    obs_cols = ["datetime", "station_id", "name"] + VALUE_KEYS
    obs_rows.sort(key=lambda r: (r["datetime"], r["station_id"]))
    with open("./observations.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=obs_cols)
        w.writeheader()
        w.writerows(obs_rows)

    st_cols = ["station_id", "name", "lat", "lon", "elev", "prid", "kansoku", "type"]
    with open("./stations.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=st_cols)
        w.writeheader()
        w.writerows(stations)


if __name__ == "__main__":
    main()
