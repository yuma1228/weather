"""アメダスの降水量・気温・風(要素101/201/301)を取得する。

官署データ(data_get_script.py が作る observations.csv)とは別ファイルに出力する。
server.py は data/observations*.csv / data/stations*.csv をまとめて読むので、
このファイルを置くだけで雨ページの地点が一気に増え、観測がある地点は
気温・風向・風速も使える。

  出力: observations_amedas.csv , stations_amedas.csv
  実行: (backend/data の中で)
      py fetch_amedas_rain.py         # 全アメダス
      py fetch_amedas_rain.py 5       # 先頭5地点だけ(疎通確認用)

アメダスは湿度・日射を持たないため WBGT は出せない。
熱中症ページ側では WBGT の出る地点だけ表示する(server/client は変更不要)。
"""

import csv
import os
import sys
import time

import data_get_script as obs  # セッション/地点マスタ/CSV取得/パースを再利用

# アメダスを対象にする。取得項目は地点ごとの観測有無で出し分ける。
obs.STATION_MODE = "amedas"

# kansoku は先頭から 降水/気温/風 の有無を表す。
AMEDAS_ELEMENTS = [
    (0, "101"),  # 降水量
    (1, "201"),  # 気温
    (2, "301"),  # 風向・風速
]

# observations.csv と同じ列にそろえる(観測がない項目は空欄)
OBS_COLS = [
    "datetime", "station_id", "name", "temp", "precip", "humidity", "solar",
    "sunshine", "cloud", "wind_dir", "wind_speed", "vapor_pressure", "dew_point",
]
ST_COLS = ["station_id", "name", "lat", "lon", "elev", "prid", "kansoku", "type"]


def element_codes(st: dict) -> list[str]:
    kansoku = st.get("kansoku") or ""
    return [
        code
        for pos, code in AMEDAS_ELEMENTS
        if len(kansoku) > pos and kansoku[pos] == "1"
    ]


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    observations_path = obs.DATA_DIR / "observations_amedas.csv"
    stations_path = obs.DATA_DIR / "stations_amedas.csv"
    observations_tmp = obs.DATA_DIR / "observations_amedas.csv.tmp"
    stations_tmp = obs.DATA_DIR / "stations_amedas.csv.tmp"

    sess = obs.open_session()
    stations = obs.fetch_station_master(sess)
    # 雨ページの密度を上げる用途なので、降水観測のある地点を対象にする。
    stations = [s for s in stations if "101" in element_codes(s)]
    if limit:
        stations = stations[:limit]
    print(f"対象アメダス: {len(stations)} 地点")

    # 観測CSVは1地点ずつ追記+flush(途中で落ちても部分保存が残る)
    done = []
    row_count = 0
    with open(observations_tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OBS_COLS)
        w.writeheader()
        for i, st in enumerate(stations, 1):
            sid, name = st["station_id"], st["name"]
            try:
                text = obs.fetch_station_csv(sess, sid, element_codes(st))
                parsed = obs.parse_csv(text)
                for rec in parsed:
                    row = {c: "" for c in OBS_COLS}
                    row["datetime"] = rec["datetime"]
                    row["station_id"] = sid
                    row["name"] = name
                    for key in ("temp", "precip", "wind_dir", "wind_speed"):
                        row[key] = rec.get(key)
                    w.writerow(row)
                    row_count += 1
                f.flush()
                done.append(st)
            except Exception as ex:
                print(f"  [error] {name}({sid}): {ex}")
            if i % 50 == 0:
                print(f"  {i}/{len(stations)} ...")
            time.sleep(obs.REQUEST_INTERVAL)

    if row_count == 0:
        observations_tmp.unlink(missing_ok=True)
        raise RuntimeError("アメダス観測データが0件のため observations_amedas.csv を上書きしません")

    with open(stations_tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ST_COLS)
        w.writeheader()
        w.writerows(done)

    os.replace(observations_tmp, observations_path)
    os.replace(stations_tmp, stations_path)

    print(f"完了: {len(done)} 地点を取得")


if __name__ == "__main__":
    main()
