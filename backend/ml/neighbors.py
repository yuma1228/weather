import numpy as np
import pandas as pd


def compute_neighbors(stations_csv, k=5):
    df = pd.read_csv(stations_csv, encoding="utf-8-sig")
    ids = df["station_id"].to_numpy()
    lat = np.radians(df["lat"].to_numpy(float))
    lon = np.radians(df["lon"].to_numpy(float))

    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlon / 2) ** 2
    d = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    np.fill_diagonal(d, np.inf)

    nn = np.argsort(d, axis=1)[:, :k]
    return {ids[i]: [ids[j] for j in nn[i]] for i in range(len(ids))}


if __name__ == "__main__":
    import os
    here = os.path.dirname(__file__)
    tbl = compute_neighbors(os.path.join(here, "..", "data", "stations_amedas.csv"), k=5)
    sid = next(iter(tbl))
    print(f"{len(tbl)} 地点。例: {sid} -> {tbl[sid]}")
    assert all(len(v) == 5 for v in tbl.values()), "K=5 の近傍が全地点で揃うこと"
    assert all(sid not in v for sid, v in tbl.items()), "自分自身は近傍に入らないこと"
    print("OK")
