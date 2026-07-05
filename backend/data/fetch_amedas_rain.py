"""アメダスの降水量(要素101)を取得して雨ページのデータ密度を上げる。

官署データ(data_get_script.py が作る observations.csv)とは別ファイルに出力する。
server.py は data/observations*.csv / data/stations*.csv をまとめて読むので、
このファイルを置くだけで雨ページの地点が一気に増える。

  出力: observations_amedas.csv , stations_amedas.csv
  実行: (backend/data の中で)
      py fetch_amedas_rain.py         # 全アメダス
      py fetch_amedas_rain.py 5       # 先頭5地点だけ(疎通確認用)

アメダスは湿度・日射を持たないため WBGT は出せない。よって降水量のみ取得し、
熱中症ページ側では WBGT の出る地点だけ表示する(server/client は変更不要)。
"""

import csv
import sys
import time

import data_get_script as obs  # セッション/地点マスタ/CSV取得/パースを再利用

# 降水量のみ取得する設定に上書き
obs.STATION_MODE = "amedas"
obs.ELEMENT_CODES = ["101"]  # 101 = 降水量

# observations.csv と同じ列にそろえる(降水以外は空欄)
OBS_COLS = [
    "datetime", "station_id", "name", "temp", "precip", "humidity", "solar",
    "sunshine", "cloud", "wind_dir", "wind_speed", "vapor_pressure", "dew_point",
]
ST_COLS = ["station_id", "name", "lat", "lon", "elev", "prid", "kansoku", "type"]


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    sess = obs.open_session()
    stations = obs.fetch_station_master(sess)
    # 降水観測のある地点のみ(kansoku 6桁の先頭=降水の有無)
    stations = [s for s in stations if (s.get("kansoku") or "")[:1] == "1"]
    if limit:
        stations = stations[:limit]
    print(f"対象アメダス: {len(stations)} 地点")

    # 観測CSVは1地点ずつ追記+flush(途中で落ちても部分保存が残る)
    done = []
    with open("./observations_amedas.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OBS_COLS)
        w.writeheader()
        for i, st in enumerate(stations, 1):
            sid, name = st["station_id"], st["name"]
            try:
                text = obs.fetch_station_csv(sess, sid)
                parsed = obs.parse_csv(text)
                for rec in parsed:
                    row = {c: "" for c in OBS_COLS}
                    row["datetime"] = rec["datetime"]
                    row["station_id"] = sid
                    row["name"] = name
                    row["precip"] = rec.get("precip")
                    w.writerow(row)
                f.flush()
                done.append(st)
            except Exception as ex:
                print(f"  [error] {name}({sid}): {ex}")
            if i % 50 == 0:
                print(f"  {i}/{len(stations)} ...")
            time.sleep(obs.REQUEST_INTERVAL)

    with open("./stations_amedas.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ST_COLS)
        w.writeheader()
        w.writerows(done)

    print(f"完了: {len(done)} 地点を取得")


if __name__ == "__main__":
    main()
