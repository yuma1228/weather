import json
import os

import lightgbm as lgb
import numpy as np

import baseline
from dataset import HORIZONS, build_dataset

HERE = os.path.dirname(__file__)
MODELS_DIR = os.path.join(HERE, "models")


def _train_one(objective, X, y, cat_features, num_boost_round):
    ds = lgb.Dataset(X, label=y, categorical_feature=cat_features, free_raw_data=False)
    params = {"objective": objective, "verbosity": -1, "num_threads": 0}
    return lgb.train(params, ds, num_boost_round=num_boost_round)


def run(obs_csv, stations_csv, n_train=5_000_000, n_test=1_000_000,
        k=5, num_boost_round=300, seed=0, save=True, **ds_kwargs):
    data = build_dataset(obs_csv, stations_csv, n_train=n_train, n_test=n_test,
                         k=k, seed=seed, **ds_kwargs)
    tr, te = data["train"], data["test"]
    cat = data["cat_features"]
    metrics = {"precip": {}, "temp": {}}
    if save:
        os.makedirs(MODELS_DIR, exist_ok=True)

    for h in HORIZONS:
        tag = f"{h}h"

        # 降水: 二値分類（logloss）。persistence = t の降水状態(0/1)を確率とみなす。
        m = _train_one("binary", tr["X"], tr["y_precip"][h], cat, num_boost_round)
        prob = m.predict(te["X"])
        metrics["precip"][tag] = {
            "lgb": baseline.precip_metrics(prob, te["y_precip"][h]),
            "persistence": baseline.precip_metrics(te["base_rain"], te["y_precip"][h]),
        }
        _mark(metrics["precip"][tag], "Brier", lower_better=True)
        if save:
            m.save_model(os.path.join(MODELS_DIR, f"lgb_precip_{tag}.txt"))

        # 気温: 回帰（L2）。persistence = t の気温。
        m = _train_one("regression", tr["X"], tr["y_temp"][h], cat, num_boost_round)
        pred = m.predict(te["X"])
        metrics["temp"][tag] = {
            "lgb": baseline.temp_metrics(pred, te["y_temp"][h]),
            "persistence": baseline.temp_metrics(te["base_temp"], te["y_temp"][h]),
        }
        _mark(metrics["temp"][tag], "MAE", lower_better=True)
        if save:
            m.save_model(os.path.join(MODELS_DIR, f"lgb_temp_{tag}.txt"))

    if save:
        with open(os.path.join(MODELS_DIR, "..", "metrics.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
    return metrics


def _mark(entry, key, lower_better):
    """lgb が persistence を上回ったか（下回ったら警告フラグ）を記録。"""
    a, b = entry["lgb"][key], entry["persistence"][key]
    entry["beats_baseline"] = bool(a < b) if lower_better else bool(a > b)


def _print(metrics):
    for target in ("precip", "temp"):
        print(f"\n=== {target} ===")
        for tag, e in metrics[target].items():
            flag = "" if e["beats_baseline"] else "  <-- WARN: persistence未達"
            print(f"  {tag:>3}  lgb={e['lgb']}  persistence={e['persistence']}{flag}")


if __name__ == "__main__":
    # 自己チェック: 先頭30万行(=2015)を月で分けて小規模にパイプライン全体を回す。
    obs = os.path.join(HERE, "..", "data", "observations_amedas.csv")
    st = os.path.join(HERE, "..", "data", "stations_amedas.csv")
    metrics = run(obs, st, n_train=20_000, n_test=5_000, num_boost_round=60, save=False,
                  nrows=300_000, train_end="2015-09-30 23:00:00",
                  test_start="2015-10-01 00:00:00", test_end="2015-12-31 23:00:00")
    _print(metrics)

    def finite(d):
        return all(np.isfinite(v) for v in d.values())

    for target in ("precip", "temp"):
        for tag, e in metrics[target].items():
            assert finite(e["lgb"]) and finite(e["persistence"]), f"{target} {tag} 指標が非有限"
    # 12h気温は persistence が最も弱く（日周期で正午↔深夜が逆相）、学習が機能していれば必ず上回る。
    # 1h/24hは persistence が強い（1h=ほぼ不変、24h=同時刻で日周期一致）ため assert には使わない。
    assert metrics["temp"]["12h"]["lgb"]["MAE"] <= metrics["temp"]["12h"]["persistence"]["MAE"], \
        "12h気温MAEが persistence を超えられない -> 学習パイプラインが機能していない疑い"
    print("\nOK")
