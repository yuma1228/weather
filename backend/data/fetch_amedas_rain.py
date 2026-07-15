"""アメダスの降水量・気温・風(要素101/201/301)を取得する。

官署データ(data_get_script.py が作る observations.csv)とは別ファイルに出力する。
server.py は data/observations*.csv / data/stations*.csv をまとめて読むので、
このファイルを置くだけで雨ページの地点が一気に増え、観測がある地点は
気温・風向・風速も使える。

  出力: observations_amedas.csv , stations_amedas.csv
  実行: (backend/data の中で)
      py fetch_amedas_rain.py         # 全アメダス
      py fetch_amedas_rain.py 5       # 先頭5地点だけ(疎通確認用、最終CSVは置換しない)

  地点×年ごとに取得し、完成した年を .download_parts_v1/amedas に原子的に保存する。
  同じコマンドを再実行すると完成済みの地点×年をスキップして続きから取れる。
  全パーツが揃ったときだけ observations_amedas.csv を原子的に置き換えるため、
  PCクラッシュや一部取得失敗で既存の完成データを壊さない。
  やり直したい場合は .download_parts_v1/amedas を削除してから実行する。

アメダスは湿度・日射を持たないため WBGT は出せない。
熱中症ページ側では WBGT の出る地点だけ表示する(server/client は変更不要)。
"""

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import data_get_script as obs  # セッション/地点マスタ/CSV取得/パースを再利用

# アメダスを対象にする。取得項目は地点ごとの観測有無で出し分ける。
obs.STATION_MODE = "amedas"

# 並列ワーカー数。上げるほど速いが気象庁サーバーへの同時アクセスが増える。
WORKERS = 4

_local = threading.local()


def _session():
    # スレッドごとに1つのセッションを使い回す(地点ごとに開き直さない)。
    if not hasattr(_local, "sess"):
        _local.sess = obs.open_session()
    return _local.sess


# kansoku は先頭から 降水/気温/風 の有無を表す。
AMEDAS_ELEMENTS = [
    (0, "101"),  # 降水量
    (1, "201"),  # 気温
    (2, "301"),  # 風向・風速
]

# observations.csv と同じ列にそろえる(観測がない項目は空欄)
OBS_COLS = obs.OBS_COLS
ST_COLS = obs.ST_COLS

OBSERVATIONS_PATH = obs.DATA_DIR / "observations_amedas.csv"
STATIONS_PATH = obs.DATA_DIR / "stations_amedas.csv"
PARTS_DIR = obs.DATA_DIR / ".download_parts_v1" / "amedas"


def element_codes(st: dict) -> list[str]:
    kansoku = st.get("kansoku") or ""
    return [
        code
        for pos, code in AMEDAS_ELEMENTS
        if len(kansoku) > pos and kansoku[pos] == "1"
    ]


def year_chunks(start, end):
    """要素3個までなら1年分でも気象庁側の取得上限に収まる(実測確認済み)。"""
    yield from obs.year_chunks(start, end)


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    stations = obs.fetch_station_master(_session())
    # 雨ページの密度を上げる用途なので、降水観測のある地点を対象にする。
    stations = [s for s in stations if "101" in element_codes(s)]
    if limit:
        stations = stations[:limit]

    download_end = obs.latest_complete_year_end(obs.END_DATE)
    if download_end < obs.START_DATE:
        raise RuntimeError("完了済みの年が取得期間に含まれていません")
    if download_end < obs.END_DATE:
        print(f"進行中の年は未完了扱いのため、取得終了日を {download_end} に制限します")
    periods = list(year_chunks(obs.START_DATE, download_end))

    print(f"対象アメダス: {len(stations)} 地点 ({WORKERS}並列)")

    expected_parts = [
        obs.annual_part_path(
            PARTS_DIR, st["station_id"], cs, ce, element_codes(st)
        )
        for _, cs, ce in periods
        for st in stations
    ]

    def process_station(st):
        sid, name = st["station_id"], st["name"]
        codes = element_codes(st)
        completed = 0
        skipped = 0
        errors = []
        try:
            sess = _session()
        except Exception as ex:
            return completed, skipped, [(sid, None, str(ex))]

        for year, cs, ce in periods:
            part_path = obs.annual_part_path(PARTS_DIR, sid, cs, ce, codes)
            if part_path.exists():
                skipped += 1
                continue
            try:
                try:
                    text = obs.fetch_station_csv(sess, sid, cs, ce, codes)
                    parsed = obs.parse_csv(text)
                    obs.validate_parsed_rows(parsed, cs, ce)
                finally:
                    time.sleep(obs.REQUEST_INTERVAL)
                rows = []
                for rec in parsed:
                    row = {c: "" for c in OBS_COLS}
                    row["datetime"] = rec["datetime"]
                    row["station_id"] = sid
                    row["name"] = name
                    for key in ("temp", "precip", "wind_dir", "wind_speed"):
                        row[key] = rec.get(key)
                    rows.append(row)
                obs.write_csv_atomic(part_path, OBS_COLS, rows)
                completed += 1
            except Exception as ex:
                errors.append((sid, year, str(ex)))
                print(f"  [error] {name}({sid}) {year}: {ex}")
        return completed, skipped, errors

    completed = 0
    skipped = 0
    errors = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(process_station, st) for st in stations]
        for i, fut in enumerate(as_completed(futures), 1):
            station_completed, station_skipped, station_errors = fut.result()
            completed += station_completed
            skipped += station_skipped
            errors.extend(station_errors)
            if i % 50 == 0:
                print(f"  {i}/{len(stations)} ...")

    missing = [path for path in expected_parts if not path.exists()]
    if errors or missing:
        raise RuntimeError(
            f"未完了の地点×年が {len(missing)} 件あります。"
            "完成済み年は保存済みなので、同じコマンドで再開できます"
        )

    if limit:
        print(
            f"疎通確認完了: {len(stations)} 地点、{len(periods)} 年 "
            f"(新規 {completed} 年パーツ / 再利用 {skipped} 年パーツ)。"
            "最終CSVは置き換えていません"
        )
        return

    row_count = obs.merge_csv_parts(expected_parts, OBSERVATIONS_PATH, OBS_COLS)
    obs.write_csv_atomic(STATIONS_PATH, ST_COLS, stations)
    print(
        f"完了: {len(stations)} 地点、{len(periods)} 年、{row_count} 行 "
        f"(新規 {completed} 年パーツ / 再利用 {skipped} 年パーツ)"
    )


if __name__ == "__main__":
    main()
