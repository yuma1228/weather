import numpy as np
import pandas as pd

from neighbors import compute_neighbors

VARS = ["temp", "precip", "wind_speed"]
HISTORY = 24            # 直近24時間
HORIZONS = [1, 6, 12, 24]
RAIN_THRESH = 0.1
# 日付ベース固定分割（デフォルト: train 2015-2024 / test 2025、2026端数は除外）
TRAIN_END = "2024-12-31 23:00:00"
TEST_START = "2025-01-01 00:00:00"
TEST_END = "2025-12-31 23:00:00"


def _load_pivots(obs_csv, nrows=None):
    df = pd.read_csv(
        obs_csv,
        encoding="utf-8-sig",  # ヘッダBOM対策（先頭列が ﻿datetime になるのを防ぐ）
        usecols=["datetime", "station_id"] + VARS,
        dtype={"station_id": "string", **{v: "float32" for v in VARS}},
        parse_dates=["datetime"],
        nrows=nrows,
    )
    pivots = {v: df.pivot(index="datetime", columns="station_id", values=v) for v in VARS}
    cols = pivots["temp"].columns
    full_idx = pd.date_range(pivots["temp"].index.min(), pivots["temp"].index.max(), freq="h")
    return {v: pivots[v].reindex(index=full_idx, columns=cols) for v in VARS}, full_idx, cols


def _valid_positions(pivots):
    tp, pp = pivots["temp"], pivots["precip"]
    valid = tp.notna() & pp.notna()  # 基準時刻（persistence と neighbor@t を成立させるため base も要求）
    for h in HORIZONS:
        valid &= tp.shift(-h).notna() & pp.shift(-h).notna()
    r, c = np.where(valid.to_numpy())
    return r.astype(np.int64), c.astype(np.int64)


def _feature_names(k):
    names = [f"{v}_lag{lag}" for v in VARS for lag in range(HISTORY)]
    names += ["lat", "lon", "elev", "month", "hour"]
    names += [f"nb{j + 1}_{v}" for j in range(k) for v in VARS]
    return names


def _materialize(pivots, full_idx, cols, r, c, stations_csv, neighbors, k):
    arrs = {v: pivots[v].to_numpy(np.float32) for v in VARS}
    n = len(r)
    names = _feature_names(k)
    X = np.full((n, len(names)), np.nan, np.float32)

    col = 0
    for v in VARS:
        a = arrs[v]
        for lag in range(HISTORY):
            src = r - lag
            ok = src >= 0
            X[ok, col] = a[src[ok], c[ok]]
            col += 1

    smeta = pd.read_csv(stations_csv, encoding="utf-8-sig").set_index("station_id")
    for name in ["lat", "lon", "elev"]:
        vals = smeta[name].reindex(cols).to_numpy(np.float32)
        X[:, col] = vals[c]
        col += 1

    times = full_idx[r]
    X[:, col] = times.month.to_numpy(np.float32); col += 1
    X[:, col] = times.hour.to_numpy(np.float32); col += 1

    col_of = {sid: i for i, sid in enumerate(cols)}
    nb_cols = np.full((len(cols), k), -1, np.int64)
    for i, sid in enumerate(cols):
        for j, nb_sid in enumerate(neighbors.get(sid, [])[:k]):
            nb_cols[i, j] = col_of.get(nb_sid, -1)  # pivotに無い地点(nrows制限時等)は -1 -> NaN
    sample_nb = nb_cols[c]  # (n, k)
    for j in range(k):
        nj = sample_nb[:, j]
        ok = nj >= 0
        for v in VARS:
            X[ok, col] = arrs[v][r[ok], nj[ok]]
            col += 1
    assert col == len(names)

    TV, PV = arrs["temp"], arrs["precip"]
    y_temp = {h: TV[r + h, c] for h in HORIZONS}
    y_precip = {h: (PV[r + h, c] >= RAIN_THRESH).astype(np.int8) for h in HORIZONS}
    base_temp = TV[r, c]                              # persistence: t+k気温 = t気温
    base_rain = (PV[r, c] >= RAIN_THRESH).astype(np.float32)  # persistence: t+k降水確率 = t降水状態
    return {"X": X, "y_temp": y_temp, "y_precip": y_precip,
            "base_temp": base_temp, "base_rain": base_rain}


def build_dataset(obs_csv, stations_csv, n_train=5_000_000, n_test=1_000_000,
                  k=5, seed=0, nrows=None,
                  train_end=TRAIN_END, test_start=TEST_START, test_end=TEST_END):
    rng = np.random.default_rng(seed)
    pivots, full_idx, cols = _load_pivots(obs_csv, nrows=nrows)
    neighbors = compute_neighbors(stations_csv, k=k)

    r, c = _valid_positions(pivots)
    ts = full_idx[r]  # 各サンプルの基準時刻
    train_mask = ts <= pd.Timestamp(train_end)
    test_mask = (ts >= pd.Timestamp(test_start)) & (ts <= pd.Timestamp(test_end))

    def _sample(mask, n):
        idx = np.where(mask)[0]
        if len(idx) > n:
            idx = rng.choice(idx, size=n, replace=False)
        return _materialize(pivots, full_idx, cols, r[idx], c[idx], stations_csv, neighbors, k)

    train = _sample(train_mask, n_train)
    test = _sample(test_mask, n_test)
    cat_features = [_feature_names(k).index(x) for x in ("month", "hour")]
    return {"train": train, "test": test,
            "feature_names": _feature_names(k), "cat_features": cat_features}


if __name__ == "__main__":
    import os
    here = os.path.dirname(__file__)
    # 先頭30万行は 2015年（CSVは年ソート）。自己チェックはその中を月で分けて高速に回す。
    data = build_dataset(
        os.path.join(here, "..", "data", "observations_amedas.csv"),
        os.path.join(here, "..", "data", "stations_amedas.csv"),
        n_train=20_000, n_test=5_000, nrows=300_000,
        train_end="2015-09-30 23:00:00", test_start="2015-10-01 00:00:00",
        test_end="2015-12-31 23:00:00",
    )
    tr = data["train"]
    print("features:", len(data["feature_names"]), "train X:", tr["X"].shape, "test X:", data["test"]["X"].shape)
    assert tr["X"].shape[1] == len(data["feature_names"])
    assert np.isfinite(tr["y_temp"][24]).all() and set(np.unique(tr["y_precip"][24])) <= {0, 1}
    assert not np.isnan(tr["base_temp"]).any(), "base温度は非NaN（有効条件で保証）"
    print("OK")
