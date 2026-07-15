import csv
import io
import os
import re
import time
import datetime as dt
from pathlib import Path

import requests
import urllib3

# verify=False 時の警告を抑制(TLS傍受環境のため無検証で運用)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

START_DATE = dt.date(2015, 1, 1)
END_DATE   = dt.date(2026, 12, 31)
DATA_DIR = Path(__file__).resolve().parent
OBSERVATIONS_PATH = DATA_DIR / "observations.csv"
STATIONS_PATH = DATA_DIR / "stations.csv"
PARTS_DIR = DATA_DIR / ".download_parts_v1" / "kansho"


#   "kansho" … 気象官署
#   "all"    … 官署＋アメダス(全地点)。
#   "amedas" … アメダスのみ
STATION_MODE = "kansho"

#   201=気温, 101=降水量, 605=相対湿度, 610=全天日射量, 401=日照時間,
#   607=雲量, 301=風向・風速, 604=蒸気圧, 612=露点温度
ELEMENT_CODES = ["201", "101", "605", "610", "401", "607", "301", "604", "612"]

# 気象庁の過去データDL(obsdl)では 1=日別値, 9=時別値。
# 10分値はこのエンドポイントの aggrgPeriod=1 では取れない。
AGGRG_PERIOD = 9

REQUEST_INTERVAL = 1.2

# obsdlは1リクエストあたりのダウンロード量に上限があり、超えると200 OKで
# 「やり直してください」というエラーページが返る(要素9個/地点だと約200日が上限)。
# 上限より十分小さい180日単位に分割してリクエストする。
CHUNK_DAYS = 180

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

OBS_COLS = ["datetime", "station_id", "name"] + VALUE_KEYS
ST_COLS = ["station_id", "name", "lat", "lon", "elev", "prid", "kansoku", "type"]

STR_KEYS = {"wind_dir", "cloud"}

AUX_LABELS = {"品質情報", "均質番号", "現象なし情報", "信頼性ランク", "備考"}

DATE_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}")


def open_session():
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Referer": INDEX_URL})
    # 社内プロキシのTLS傍受で証明書検証が失敗するため無検証にする
    sess.verify = False
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

def date_chunks(start, end, days=CHUNK_DAYS):
    s = start
    while s <= end:
        e = min(s + dt.timedelta(days=days - 1), end)
        yield s, e
        s = e + dt.timedelta(days=1)


def year_chunks(start, end):
    for year in range(start.year, end.year + 1):
        cs = max(start, dt.date(year, 1, 1))
        ce = min(end, dt.date(year, 12, 31))
        yield year, cs, ce


def latest_complete_year_end(end, today=None):
    """進行中の年を完了済みとして固定しないよう、前年末までに制限する。"""
    current = today or dt.date.today()
    return min(end, dt.date(current.year - 1, 12, 31))


def annual_part_path(parts_dir, station_id, start, end, element_codes):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", station_id):
        raise ValueError(f"不正な station_id: {station_id!r}")
    if start.year != end.year or start > end:
        raise ValueError(f"年パーツの期間が不正です: {start}～{end}")
    code_token = "-".join(element_codes) or "none"
    return Path(parts_dir) / (
        f"{station_id}-{start:%Y%m%d}-{end:%Y%m%d}-{code_token}.csv"
    )


def write_csv_atomic(path, fieldnames, rows):
    """CSVを同一ディレクトリの一時ファイルへ書き、完成後だけ公開する。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    row_count = 0
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
                row_count += 1
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return row_count


def merge_csv_parts(part_paths, output_path, fieldnames):
    """完成済みパーツをストリーミング統合し、既存出力を原子的に置換する。"""
    output_path = Path(output_path)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    row_count = 0
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=fieldnames)
            writer.writeheader()
            for part_path in part_paths:
                with open(part_path, encoding="utf-8-sig", newline="") as src:
                    reader = csv.DictReader(src)
                    if reader.fieldnames != list(fieldnames):
                        raise ValueError(f"列が一致しない年パーツです: {part_path}")
                    for row in reader:
                        writer.writerow(row)
                        row_count += 1
            dst.flush()
            os.fsync(dst.fileno())
        if row_count == 0:
            raise RuntimeError(f"観測データが0件のため {output_path.name} を上書きしません")
        os.replace(tmp, output_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return row_count


def fetch_station_csv(sess, station_id, start=None, end=None, element_codes=None):
    codes = element_codes if element_codes is not None else ELEMENT_CODES
    elem = "[" + ",".join(f'["{c}",""]' for c in codes) + "]"
    s = start if start is not None else START_DATE
    e = end if end is not None else END_DATE
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
        if any(row and row[0].strip() == "年月日" for row in rows):
            raise ValueError(
                "時別値ではなく日別値CSVです。obsdl の aggrgPeriod=1 は10分値ではなく日別値です。"
            )
        preview = " ".join(text[:200].split())
        raise ValueError(f"時別値CSVのヘッダーがありません。応答先頭: {preview!r}")

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


def validate_parsed_rows(rows, start, end):
    """応答行が要求期間内で、同一時刻を重複していないことを確認する。

    気象庁の時別値は1時~24時形式で、末日24時分は翌日00:00:00として返る
    (例: end=12/31 の最終行は 翌年1/1 00:00:00)。次チャンクは1:00開始なので
    重複にはならない。この1行だけは期間外として許容する。
    """
    seen = set()
    boundary_next_day = end + dt.timedelta(days=1)
    for row in rows:
        try:
            timestamp = dt.datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, TypeError, ValueError) as ex:
            raise ValueError(f"不正な日時を含む観測行です: {row!r}") from ex
        day = timestamp.date()
        is_boundary = day == boundary_next_day and timestamp.time() == dt.time(0, 0)
        if not is_boundary and (day < start or day > end):
            raise ValueError(f"要求期間外の観測行です: {row['datetime']} ({start}～{end})")
        if row["datetime"] in seen:
            raise ValueError(f"同一地点・期間内で日時が重複しています: {row['datetime']}")
        seen.add(row["datetime"])


def observation_rows(station, parsed):
    sid, name = station["station_id"], station["name"]
    rows = []
    for rec in parsed:
        row = {"datetime": rec["datetime"], "station_id": sid, "name": name}
        for key in VALUE_KEYS:
            row[key] = rec.get(key)
        rows.append(row)
    return rows

def main():
    sess = open_session()
    stations = fetch_station_master(sess)
    download_end = latest_complete_year_end(END_DATE)
    if download_end < START_DATE:
        raise RuntimeError("完了済みの年が取得期間に含まれていません")
    if download_end < END_DATE:
        print(f"進行中の年は未完了扱いのため、取得終了日を {download_end} に制限します")

    periods = list(year_chunks(START_DATE, download_end))
    expected_parts = []
    errors = []
    completed = 0
    skipped = 0

    for st in stations:
        sid, name = st["station_id"], st["name"]
        for year, year_start, year_end in periods:
            part_path = annual_part_path(
                PARTS_DIR, sid, year_start, year_end, ELEMENT_CODES
            )
            expected_parts.append(part_path)
            if part_path.exists():
                skipped += 1
                continue

            try:
                year_rows = []
                for chunk_start, chunk_end in date_chunks(year_start, year_end):
                    try:
                        text = fetch_station_csv(sess, sid, chunk_start, chunk_end)
                        parsed = parse_csv(text)
                        validate_parsed_rows(parsed, chunk_start, chunk_end)
                        year_rows.extend(observation_rows(st, parsed))
                    finally:
                        time.sleep(REQUEST_INTERVAL)
                write_csv_atomic(part_path, OBS_COLS, year_rows)
                completed += 1
            except Exception as ex:
                errors.append((sid, year, str(ex)))
                print(f"  [error] {name}({sid}) {year}: {ex}")

    missing = [path for path in expected_parts if not path.exists()]
    if errors or missing:
        raise RuntimeError(
            f"未完了の地点×年が {len(missing)} 件あります。"
            "完成済み年は保存済みなので、同じコマンドで再開できます"
        )

    row_count = merge_csv_parts(expected_parts, OBSERVATIONS_PATH, OBS_COLS)
    write_csv_atomic(STATIONS_PATH, ST_COLS, stations)
    print(
        f"完了: {len(stations)} 地点、{len(periods)} 年、{row_count} 行 "
        f"(新規 {completed} 年パーツ / 再利用 {skipped} 年パーツ)"
    )


if __name__ == "__main__":
    main()
