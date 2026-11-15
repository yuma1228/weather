from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from inference import (
    DT_FMT,
    EXPECTED_FEATURES,
    HISTORY_HOURS,
    NEIGHBOR_COUNT,
    VARS,
    ForecastService,
)

# 学習時の並び。inference.py から import してはいけない。
# import すると VARS を入れ替えたときに期待値も一緒に動き、テストが永久に通ってしまう。
# dataset.py の VARS / HISTORY / NEIGHBOR_COUNT と同じ値をここに固定値で持つ。
TRAIN_VARS = ("temp", "precip", "wind_speed")
TRAIN_HISTORY = 24
TRAIN_NEIGHBORS = 5
TRAIN_FEATURES = len(TRAIN_VARS) * TRAIN_HISTORY + 5 + TRAIN_NEIGHBORS * len(TRAIN_VARS)

HERE = Path(__file__).resolve().parent
STATIONS_CSV = HERE.parent / "data" / "stations_amedas.csv"
MODELS_DIR = HERE / "models"

BASED_AT = "2026-10-04 17:00:00"  # month=10 / hour=17 が静的列に出る
TARGET = "a0002"  # 沓形
TARGET_LAT, TARGET_LON, TARGET_ELEV = 45.1783, 141.1383, 14.0

# 緯度経度から決まる値。学習側の compute_neighbors と全地点で一致することを確認して固定した。
EXPECTED_NEIGHBORS = ("a1512", "a1546", "a1054", "a1203", "a1528")

# 観測値に埋め込む目印。float32 で誤差なく表せる整数にする。
MARK = {"temp": 1000, "precip": 2000, "wind_speed": 3000}
NEIGHBOR_MARK = 10000
MISSING_LAG = 7  # この lag だけ欠測にして NaN のまま渡ることを確認する

# 最新観測(station dict)側に置く罠。lag0 をここから取る実装になったら落ちる。
STATION_TRAP = -999.0

STATIC_COL = len(TRAIN_VARS) * TRAIN_HISTORY  # 72: lat / lon / elev / month / hour
NEIGHBOR_COL = STATIC_COL + 5  # 77: nb1_temp 以降

_cache: dict = {}


def _observation_at(based_at):
    """本物の観測の代わりに、来るべき列が分かる値を返す。"""

    def getter(timestamp, station_id):
        if station_id == TARGET:
            lag = round(
                (based_at - datetime.strptime(timestamp, DT_FMT)).total_seconds() / 3600
            )
            if lag == MISSING_LAG:
                return None  # 欠測。NaN のまま渡るべき
            return {v: float(MARK[v] + lag) for v in TRAIN_VARS}

        # 近傍は基準時刻のみ聞かれる。未知の地点なら近傍が変わったということなので落とす。
        j = EXPECTED_NEIGHBORS.index(station_id) + 1
        return {
            v: float(NEIGHBOR_MARK + 100 * j + i + 1)
            for i, v in enumerate(TRAIN_VARS)
        }

    return getter


def _build():
    if not _cache:
        svc = ForecastService(STATIONS_CSV, MODELS_DIR)
        svc._ensure_loaded()
        based_at = datetime.strptime(BASED_AT, DT_FMT)
        station = {
            "lat": TARGET_LAT,
            "lon": TARGET_LON,
            "elev": TARGET_ELEV,
            # _features はこの2つを欠測ガードにしか使わない。実値は観測履歴側から取る。
            "temp": STATION_TRAP,
            "precip": STATION_TRAP,
        }
        features = svc._features(TARGET, based_at, station, _observation_at(based_at))
        _cache["svc"], _cache["x"] = svc, features[0]
    return _cache["svc"], _cache["x"]


def test_constants_match_training():
    """推論側の定数が学習時と一致していること。

    変数の並び順はここでしか検出できない。列の位置テストは期待値を同じ定数から
    組むため、定数ごと入れ替わると一緒に動いてすり抜ける。
    """
    assert VARS == TRAIN_VARS, f"変数の並びが学習時と違う: {VARS}"
    assert HISTORY_HOURS == TRAIN_HISTORY, HISTORY_HOURS
    assert NEIGHBOR_COUNT == TRAIN_NEIGHBORS, NEIGHBOR_COUNT
    assert EXPECTED_FEATURES == TRAIN_FEATURES == 92, EXPECTED_FEATURES


def test_layout():
    """列数が 3変数×24時間 + 静的5 + 近傍5×3 = 92 であること。"""
    _, x = _build()
    assert x.shape == (TRAIN_FEATURES,), x.shape


def test_history_columns():
    """時系列は 変数ごとに lag0..23 がまとまって並ぶ(temp → precip → wind_speed)。"""
    _, x = _build()
    for vi, var in enumerate(TRAIN_VARS):
        for lag in range(TRAIN_HISTORY):
            col = vi * TRAIN_HISTORY + lag
            if lag == MISSING_LAG:
                assert np.isnan(x[col]), f"欠測が NaN でない: {var} lag{lag} col{col}={x[col]}"
            else:
                assert x[col] == MARK[var] + lag, f"{var} lag{lag} col{col}={x[col]}"


def test_static_columns():
    """静的列は lat / lon / elev / month / hour の順。"""
    _, x = _build()
    assert abs(x[STATIC_COL + 0] - TARGET_LAT) < 1e-3, x[STATIC_COL + 0]
    assert abs(x[STATIC_COL + 1] - TARGET_LON) < 1e-3, x[STATIC_COL + 1]
    assert abs(x[STATIC_COL + 2] - TARGET_ELEV) < 1e-3, x[STATIC_COL + 2]
    assert x[STATIC_COL + 3] == 10, x[STATIC_COL + 3]  # month
    assert x[STATIC_COL + 4] == 17, x[STATIC_COL + 4]  # hour


def test_neighbor_columns():
    """近傍は「近い順 j の外側ループ × 変数の内側ループ」で並ぶ。"""
    _, x = _build()
    for j in range(TRAIN_NEIGHBORS):
        for vi, var in enumerate(TRAIN_VARS):
            col = NEIGHBOR_COL + j * len(TRAIN_VARS) + vi
            expected = NEIGHBOR_MARK + 100 * (j + 1) + vi + 1
            assert x[col] == expected, f"nb{j + 1}_{var} col{col}={x[col]} != {expected}"


def test_lag0_comes_from_history_not_latest():
    """lag0 は観測履歴から取る。最新観測(station dict)から取ってはいけない。

    学習時の lag0 は基準時刻の毎時観測。全地点一括化で最新値から取る実装にすると
    全地点の予測が静かにずれるため、ここで設計を固定する。
    """
    _, x = _build()
    for var in ("temp", "precip"):
        col = TRAIN_VARS.index(var) * TRAIN_HISTORY
        assert x[col] == MARK[var], f"{var} lag0 col{col}={x[col]}"
        assert x[col] != STATION_TRAP, f"{var} lag0 が最新観測側から取られている"


def test_neighbors_unchanged():
    """近傍の選び方と順序は実地理なので変わってはいけない。"""
    assert len(EXPECTED_NEIGHBORS) == TRAIN_NEIGHBORS
    svc, _ = _build()
    assert svc._nearest_station_ids(TARGET, TARGET_LAT, TARGET_LON) == EXPECTED_NEIGHBORS


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all green")
