# 降水確率・気温予測NN 学習パイプライン Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 直近24時間の観測データから1/6/12/24時間後の降水確率と気温を予測するPyTorch MLPの学習パイプライン（データ読み込み〜学習〜モデル保存）を作る。

**Architecture:** `backend/ml/dataset.py`でCSV観測データを地点×基準時刻ごとの学習サンプル（24時間分の時系列特徴量＋地点の緯度経度標高＋月/時刻の周期エンコーディング）に変換し、`backend/ml/model.py`の共通MLPを`backend/ml/train.py`で学習してモデルファイルに保存する。地点ごとに個別モデルは作らず、単一の共通モデルに地点・季節情報を入力として与える。

**Tech Stack:** Python 3.14 / PyTorch / pandas / numpy / pytest

## Global Constraints

- 学習に使う時系列特徴量は `temp, precip, humidity, solar, sunshine, wind_speed, vapor_pressure, dew_point` の8種（`wind_dir`, `cloud`はv1で除外）
- 入力窓は直近24時間、予測ホライズンは `[1, 6, 12, 24]` 時間後
- 降水確率の正解ラベルは `precip >= 0.1` を1/0（既存フロントの`isRaining`と同じ閾値）
- 欠測している入力特徴量は学習データの列平均で補完する（欠測フラグ列は追加しない）
- 正解ラベル（予測対象時刻の`precip`/`temp`）が欠測しているサンプルは学習データから除外する
- train/valの分割は日付ベース（ランダムシャッフルしない）
- 今回のスコープは学習パイプラインのみ。`server.py`/`client.py`への推論組み込みは行わない

---

## File Structure

- `backend/requirements.txt` — `torch`, `pandas`, `numpy`, `pytest`を追加
- `backend/ml/__init__.py` — 新規、空ファイル（パッケージ化のため）
- `backend/ml/dataset.py` — 新規。CSV読み込み・サンプル抽出・分割・欠測補完
- `backend/ml/model.py` — 新規。MLPモデル定義
- `backend/ml/train.py` — 新規。学習ループ・モデル保存
- `backend/ml/tests/__init__.py` — 新規、空ファイル
- `backend/ml/tests/test_dataset.py` — 新規
- `backend/ml/tests/test_model.py` — 新規
- `backend/ml/tests/test_train.py` — 新規

---

### Task 1: 依存関係のセットアップとパッケージ化

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/ml/__init__.py`
- Create: `backend/ml/tests/__init__.py`

**Interfaces:**
- Produces: `backend/ml/`が`ml`パッケージとしてimport可能になる。以降のタスクは`ml.dataset`, `ml.model`のように参照する

- [ ] **Step 1: requirements.txtに依存を追加**

`backend/requirements.txt`を以下に置き換える:

```
fastapi
uvicorn
requests
torch
pandas
numpy
pytest
```

- [ ] **Step 2: インストール**

Run: `cd backend && py -m pip install -r requirements.txt`
Expected: エラーなく完了する（`torch`, `pandas`, `numpy`, `pytest`のインストールログが出る）

- [ ] **Step 3: パッケージ用の空ファイルを作成**

`backend/ml/__init__.py`（空ファイル）を作成する。

`backend/ml/tests/__init__.py`（空ファイル）を作成する。

- [ ] **Step 4: importが通ることを確認**

Run: `cd backend && py -c "import torch, pandas, numpy; print(torch.__version__, pandas.__version__, numpy.__version__)"`
Expected: 3つのバージョン文字列が1行で出力される（エラーなし）

- [ ] **Step 5: コミット**

```bash
git add backend/requirements.txt backend/ml/__init__.py backend/ml/tests/__init__.py
git commit -m "chore: add ML dependencies and ml package skeleton"
```

---

### Task 2: `load_observations` — CSV読み込み

**Files:**
- Create: `backend/ml/dataset.py`
- Test: `backend/ml/tests/test_dataset.py`

**Interfaces:**
- Produces:
  - `ml.dataset.FEATURE_COLUMNS: list[str]` = `["temp", "precip", "humidity", "solar", "sunshine", "wind_speed", "vapor_pressure", "dew_point"]`
  - `ml.dataset.WINDOW_HOURS: int` = `24`
  - `ml.dataset.HORIZONS: list[int]` = `[1, 6, 12, 24]`
  - `ml.dataset.RAIN_THRESHOLD: float` = `0.1`
  - `ml.dataset.load_observations(csv_paths: list[str]) -> pandas.DataFrame` — 列: `datetime(datetime64), station_id, name, temp, precip, humidity, solar, sunshine, cloud, wind_dir, wind_speed, vapor_pressure, dew_point`。`station_id, datetime`昇順にソート済み

- [ ] **Step 1: 失敗するテストを書く**

`backend/ml/tests/test_dataset.py`を作成:

```python
import pandas as pd

from ml.dataset import load_observations, FEATURE_COLUMNS, WINDOW_HOURS, HORIZONS, RAIN_THRESHOLD


def _write_csv(path, rows):
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return str(path)


def test_load_observations_sorts_and_concatenates(tmp_path):
    csv_a = _write_csv(tmp_path / "a.csv", [
        {"datetime": "2025-09-01 02:00:00", "station_id": "s2", "name": "B",
         "temp": 20.0, "precip": 0.0, "humidity": 80.0, "solar": 0.0, "sunshine": 0.0,
         "cloud": "", "wind_dir": "北", "wind_speed": 1.0, "vapor_pressure": 15.0, "dew_point": 10.0},
        {"datetime": "2025-09-01 01:00:00", "station_id": "s1", "name": "A",
         "temp": 22.0, "precip": 0.1, "humidity": 85.0, "solar": 0.0, "sunshine": 0.0,
         "cloud": "", "wind_dir": "南", "wind_speed": 2.0, "vapor_pressure": 16.0, "dew_point": 11.0},
    ])
    csv_b = _write_csv(tmp_path / "b.csv", [
        {"datetime": "2025-09-01 01:00:00", "station_id": "s2", "name": "B",
         "temp": 19.0, "precip": 0.0, "humidity": 78.0, "solar": 0.0, "sunshine": 0.0,
         "cloud": "", "wind_dir": "北", "wind_speed": 1.5, "vapor_pressure": 14.0, "dew_point": 9.0},
    ])

    df = load_observations([csv_a, csv_b])

    assert list(df.columns) >= FEATURE_COLUMNS if False else set(FEATURE_COLUMNS) <= set(df.columns)
    assert len(df) == 3
    assert pd.api.types.is_datetime64_any_dtype(df["datetime"])
    # station_id, datetime の昇順になっている
    pairs = list(zip(df["station_id"], df["datetime"]))
    assert pairs == sorted(pairs)


def test_constants():
    assert WINDOW_HOURS == 24
    assert HORIZONS == [1, 6, 12, 24]
    assert RAIN_THRESHOLD == 0.1
    assert FEATURE_COLUMNS == [
        "temp", "precip", "humidity", "solar", "sunshine",
        "wind_speed", "vapor_pressure", "dew_point",
    ]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd backend && py -m pytest ml/tests/test_dataset.py -v`
Expected: `ModuleNotFoundError: No module named 'ml.dataset'` でFAIL

- [ ] **Step 3: 最小実装を書く**

`backend/ml/dataset.py`を作成:

```python
import pandas as pd

FEATURE_COLUMNS = [
    "temp", "precip", "humidity", "solar", "sunshine",
    "wind_speed", "vapor_pressure", "dew_point",
]
WINDOW_HOURS = 24
HORIZONS = [1, 6, 12, 24]
RAIN_THRESHOLD = 0.1


def load_observations(csv_paths):
    frames = [pd.read_csv(p, encoding="utf-8-sig") for p in csv_paths]
    df = pd.concat(frames, ignore_index=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values(["station_id", "datetime"]).reset_index(drop=True)
    return df
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd backend && py -m pytest ml/tests/test_dataset.py -v`
Expected: 2件ともPASS

- [ ] **Step 5: コミット**

```bash
git add backend/ml/dataset.py backend/ml/tests/test_dataset.py
git commit -m "feat: add load_observations for ML dataset pipeline"
```

---

### Task 3: `build_samples` — サンプル抽出・特徴量ベクトル化

**Files:**
- Modify: `backend/ml/dataset.py`
- Test: `backend/ml/tests/test_dataset.py`

**Interfaces:**
- Consumes: `load_observations`が返す`DataFrame`、`stations`は列`station_id, lat, lon, elev`を持つ`DataFrame`（`FEATURE_COLUMNS`, `WINDOW_HOURS`, `HORIZONS`, `RAIN_THRESHOLD`はTask 2で定義済み）
- Produces:
  - `ml.dataset.build_samples(df: pandas.DataFrame, stations: pandas.DataFrame) -> dict` — キー:
    - `"X"`: `numpy.ndarray`, shape `(N, WINDOW_HOURS*len(FEATURE_COLUMNS)+7)` = `(N, 199)`, dtype float。列順序は「時刻 t-23h→t の各時刻ごとにFEATURE_COLUMNS8個を並べたもの(192次元)」→「lat, lon, elev(3次元)」→「month_sin, month_cos, hour_sin, hour_cos(4次元)」
    - `"y_rain"`: `numpy.ndarray`, shape `(N, 4)`, 0.0/1.0（`HORIZONS`の順）
    - `"y_temp"`: `numpy.ndarray`, shape `(N, 4)`, float（`HORIZONS`の順）
    - `"station_id"`: `numpy.ndarray`, shape `(N,)`, str
    - `"datetime"`: `numpy.ndarray`, shape `(N,)`, dtype `datetime64[ns]`（基準時刻t）
  - 基準時刻tのサンプルが採用されるのは「t-23h〜tの24時刻すべてが存在」かつ「t+1h, t+6h, t+12h, t+24hの`precip`と`temp`が両方とも非欠測で存在」する場合のみ

- [ ] **Step 1: 失敗するテストを書く**

`backend/ml/tests/test_dataset.py`に追記:

```python
import numpy as np

from ml.dataset import build_samples


def _hourly_rows(station_id, name, lat_seed, start, n_hours):
    rows = []
    base = pd.Timestamp(start)
    for i in range(n_hours):
        t = base + pd.Timedelta(hours=i)
        rows.append({
            "datetime": t.strftime("%Y-%m-%d %H:%M:%S"),
            "station_id": station_id,
            "name": name,
            "temp": 15.0 + i * 0.1,
            "precip": 1.0 if i % 10 == 0 else 0.0,
            "humidity": 70.0,
            "solar": 0.0,
            "sunshine": 0.0,
            "cloud": "",
            "wind_dir": "南",
            "wind_speed": 2.0,
            "vapor_pressure": 15.0,
            "dew_point": 10.0,
        })
    return rows


def test_build_samples_shapes_and_count():
    # 24(窓) + 24(最大ホライズン) = 48時間ぴったり -> 基準時刻は1個だけ採用される
    # (49時間分用意すると i=23,24 の2個が条件を満たしてしまうので48時間ちょうどにする)
    df = pd.DataFrame(_hourly_rows("s1", "A", 0, "2025-09-01 00:00:00", 48))
    df["datetime"] = pd.to_datetime(df["datetime"])
    stations = pd.DataFrame([{"station_id": "s1", "lat": 35.0, "lon": 139.0, "elev": 10.0}])

    samples = build_samples(df, stations)

    assert samples["X"].shape == (1, 24 * 8 + 7)
    assert samples["y_rain"].shape == (1, 4)
    assert samples["y_temp"].shape == (1, 4)
    assert samples["station_id"].shape == (1,)
    assert samples["datetime"].shape == (1,)

    # 基準時刻は先頭から24時間後 (index 23) = 2025-09-01 23:00:00
    assert pd.Timestamp(samples["datetime"][0]) == pd.Timestamp("2025-09-01 23:00:00")

    # precip は i%10==0 のとき1.0。ホライズン [1,6,12,24] 先の index は 24,29,35,47
    # それぞれ i%10: 24%10=4(->0.0,雨じゃない), 29%10=9(->0.0), 35%10=5(->0.0), 47%10=7(->0.0)
    assert list(samples["y_rain"][0]) == [0.0, 0.0, 0.0, 0.0]

    # temp = 15.0 + i*0.1 なので、horizon先の temp が正解値と一致する
    expected_temp = [15.0 + i * 0.1 for i in (24, 29, 35, 47)]
    assert np.allclose(samples["y_temp"][0], expected_temp)


def test_build_samples_skips_when_label_missing():
    rows = _hourly_rows("s1", "A", 0, "2025-09-01 00:00:00", 48)
    rows[24]["precip"] = None  # t+1h の正解が欠測 -> 基準時刻 index23 のサンプルは除外される
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    stations = pd.DataFrame([{"station_id": "s1", "lat": 35.0, "lon": 139.0, "elev": 10.0}])

    samples = build_samples(df, stations)

    assert samples["X"].shape[0] == 0


def test_build_samples_keeps_missing_input_feature():
    rows = _hourly_rows("s1", "A", 0, "2025-09-01 00:00:00", 48)
    rows[0]["humidity"] = None  # 窓の中の入力特徴量が欠測 -> サンプル自体は残る(NaNのまま)
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    stations = pd.DataFrame([{"station_id": "s1", "lat": 35.0, "lon": 139.0, "elev": 10.0}])

    samples = build_samples(df, stations)

    assert samples["X"].shape[0] == 1
    assert np.isnan(samples["X"]).any()


def test_build_samples_skips_station_without_metadata():
    df = pd.DataFrame(_hourly_rows("s_unknown", "A", 0, "2025-09-01 00:00:00", 48))
    df["datetime"] = pd.to_datetime(df["datetime"])
    stations = pd.DataFrame([{"station_id": "s1", "lat": 35.0, "lon": 139.0, "elev": 10.0}])

    samples = build_samples(df, stations)

    assert samples["X"].shape[0] == 0
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd backend && py -m pytest ml/tests/test_dataset.py -v -k build_samples`
Expected: `ImportError: cannot import name 'build_samples'` でFAIL

- [ ] **Step 3: 実装を書く**

`backend/ml/dataset.py`に追記:

```python
import numpy as np


def build_samples(df, stations):
    station_meta = stations.set_index("station_id")[["lat", "lon", "elev"]]
    offsets = list(range(-(WINDOW_HOURS - 1), 1))  # -23..0

    X_list, rain_list, temp_list, sid_list, dt_list = [], [], [], [], []

    for station_id, g in df.groupby("station_id"):
        if station_id not in station_meta.index:
            continue
        lat, lon, elev = station_meta.loc[station_id, ["lat", "lon", "elev"]]

        g = g.set_index("datetime").sort_index()
        time_set = set(g.index)

        for t in g.index:
            window_times = [t + pd.Timedelta(hours=h) for h in offsets]
            if not all(wt in time_set for wt in window_times):
                continue

            horizon_times = [t + pd.Timedelta(hours=h) for h in HORIZONS]
            if not all(ht in time_set for ht in horizon_times):
                continue

            rain_labels = []
            temp_labels = []
            skip = False
            for ht in horizon_times:
                row = g.loc[ht]
                if pd.isna(row["precip"]) or pd.isna(row["temp"]):
                    skip = True
                    break
                rain_labels.append(1.0 if row["precip"] >= RAIN_THRESHOLD else 0.0)
                temp_labels.append(float(row["temp"]))
            if skip:
                continue

            window_feats = g.loc[window_times, FEATURE_COLUMNS].to_numpy(dtype=float).flatten()
            month, hour = t.month, t.hour
            time_enc = np.array([
                np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12),
                np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24),
            ])
            static_feats = np.array([lat, lon, elev], dtype=float)
            x = np.concatenate([window_feats, static_feats, time_enc])

            X_list.append(x)
            rain_list.append(rain_labels)
            temp_list.append(temp_labels)
            sid_list.append(station_id)
            dt_list.append(t)

    n_features = WINDOW_HOURS * len(FEATURE_COLUMNS) + 7
    return {
        "X": np.array(X_list, dtype=float).reshape(-1, n_features) if X_list else np.empty((0, n_features)),
        "y_rain": np.array(rain_list, dtype=float).reshape(-1, len(HORIZONS)) if rain_list else np.empty((0, len(HORIZONS))),
        "y_temp": np.array(temp_list, dtype=float).reshape(-1, len(HORIZONS)) if temp_list else np.empty((0, len(HORIZONS))),
        "station_id": np.array(sid_list, dtype=object),
        "datetime": np.array(dt_list, dtype="datetime64[ns]"),
    }
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd backend && py -m pytest ml/tests/test_dataset.py -v`
Expected: 全件PASS

- [ ] **Step 5: コミット**

```bash
git add backend/ml/dataset.py backend/ml/tests/test_dataset.py
git commit -m "feat: add build_samples for feature/label extraction"
```

---

### Task 4: `split_by_date` / `impute_missing`

**Files:**
- Modify: `backend/ml/dataset.py`
- Test: `backend/ml/tests/test_dataset.py`

**Interfaces:**
- Consumes: `build_samples`が返す`dict`（キー`"X", "y_rain", "y_temp", "station_id", "datetime"`）
- Produces:
  - `ml.dataset.split_by_date(samples: dict, val_days: int = 3) -> tuple[dict, dict]` — `(train_samples, val_samples)`。`datetime`の最大値から`val_days`日以内を`val`、それより前を`train`とする。どちらも入力と同じキー構造の`dict`
  - `ml.dataset.impute_missing(X_train: numpy.ndarray, X_val: numpy.ndarray) -> tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray]` — `(X_train_filled, X_val_filled, col_means)`。`col_means`は`X_train`の列平均（全欠測列は0）で、`X_train`/`X_val`のNaNをこの平均で埋める

- [ ] **Step 1: 失敗するテストを書く**

`backend/ml/tests/test_dataset.py`に追記:

```python
from ml.dataset import split_by_date, impute_missing


def test_split_by_date_uses_last_val_days():
    dates = np.array([
        "2025-09-01", "2025-09-02", "2025-09-03", "2025-09-04", "2025-09-05",
    ], dtype="datetime64[ns]")
    samples = {
        "X": np.arange(5).reshape(5, 1).astype(float),
        "y_rain": np.zeros((5, 4)),
        "y_temp": np.zeros((5, 4)),
        "station_id": np.array(["s1"] * 5, dtype=object),
        "datetime": dates,
    }

    train, val = split_by_date(samples, val_days=2)

    # cutoff = 2025-09-05 - 2days = 2025-09-03。 <=cutoff が train, >cutoff が val
    assert list(train["X"].flatten()) == [0.0, 1.0, 2.0]
    assert list(val["X"].flatten()) == [3.0, 4.0]
    assert train["datetime"].shape[0] == 3
    assert val["datetime"].shape[0] == 2


def test_impute_missing_fills_with_train_mean():
    X_train = np.array([
        [1.0, np.nan],
        [3.0, 2.0],
    ])
    X_val = np.array([
        [np.nan, np.nan],
    ])

    X_train_filled, X_val_filled, col_means = impute_missing(X_train, X_val)

    assert not np.isnan(X_train_filled).any()
    assert not np.isnan(X_val_filled).any()
    assert col_means[0] == 2.0  # (1.0+3.0)/2
    assert col_means[1] == 2.0  # nanmean は 2.0 のみ
    assert X_train_filled[0, 1] == 2.0  # train内のNaNも列平均で埋まる
    assert X_val_filled[0, 0] == 2.0
    assert X_val_filled[0, 1] == 2.0


def test_impute_missing_all_nan_column_becomes_zero():
    X_train = np.array([[np.nan], [np.nan]])
    X_val = np.array([[np.nan]])

    X_train_filled, X_val_filled, col_means = impute_missing(X_train, X_val)

    assert col_means[0] == 0.0
    assert X_train_filled[0, 0] == 0.0
    assert X_val_filled[0, 0] == 0.0
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd backend && py -m pytest ml/tests/test_dataset.py -v -k "split_by_date or impute_missing"`
Expected: `ImportError` でFAIL

- [ ] **Step 3: 実装を書く**

`backend/ml/dataset.py`に追記:

```python
def split_by_date(samples, val_days=3):
    dates = samples["datetime"]
    cutoff = dates.max() - np.timedelta64(val_days, "D")
    train_idx = dates <= cutoff
    val_idx = ~train_idx
    train = {k: v[train_idx] for k, v in samples.items()}
    val = {k: v[val_idx] for k, v in samples.items()}
    return train, val


def impute_missing(X_train, X_val):
    col_means = np.nanmean(X_train, axis=0)
    col_means = np.nan_to_num(col_means, nan=0.0)

    def fill(X):
        X = X.copy()
        idx = np.where(np.isnan(X))
        X[idx] = np.take(col_means, idx[1])
        return X

    return fill(X_train), fill(X_val), col_means
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd backend && py -m pytest ml/tests/test_dataset.py -v`
Expected: 全件PASS

- [ ] **Step 5: コミット**

```bash
git add backend/ml/dataset.py backend/ml/tests/test_dataset.py
git commit -m "feat: add split_by_date and impute_missing"
```

---

### Task 5: `ForecastNet` モデル定義

**Files:**
- Create: `backend/ml/model.py`
- Test: `backend/ml/tests/test_model.py`

**Interfaces:**
- Consumes: `ml.dataset.WINDOW_HOURS`, `ml.dataset.FEATURE_COLUMNS`, `ml.dataset.HORIZONS`（次元計算に使用）
- Produces:
  - `ml.model.INPUT_DIM: int` = `199`
  - `ml.model.N_HORIZONS: int` = `4`
  - `ml.model.ForecastNet(torch.nn.Module)` — `__init__(self, input_dim: int = INPUT_DIM, hidden1: int = 128, hidden2: int = 64)`。`forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]`で`(rain_logits, temp_pred)`を返す。それぞれshape`(batch, N_HORIZONS)`。`rain_logits`はsigmoid適用前のロジット（損失側で`BCEWithLogitsLoss`を使う前提）

- [ ] **Step 1: 失敗するテストを書く**

`backend/ml/tests/test_model.py`を作成:

```python
import torch

from ml.model import ForecastNet, INPUT_DIM, N_HORIZONS


def test_forward_output_shapes():
    model = ForecastNet()
    x = torch.randn(5, INPUT_DIM)

    rain_logits, temp_pred = model(x)

    assert rain_logits.shape == (5, N_HORIZONS)
    assert temp_pred.shape == (5, N_HORIZONS)


def test_forward_is_differentiable():
    model = ForecastNet()
    x = torch.randn(3, INPUT_DIM, requires_grad=True)

    rain_logits, temp_pred = model(x)
    loss = rain_logits.sum() + temp_pred.sum()
    loss.backward()

    assert x.grad is not None
    assert x.grad.shape == x.shape
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd backend && py -m pytest ml/tests/test_model.py -v`
Expected: `ModuleNotFoundError: No module named 'ml.model'` でFAIL

- [ ] **Step 3: 実装を書く**

`backend/ml/model.py`を作成:

```python
import torch
import torch.nn as nn

INPUT_DIM = 199
N_HORIZONS = 4


class ForecastNet(nn.Module):
    def __init__(self, input_dim: int = INPUT_DIM, hidden1: int = 128, hidden2: int = 64):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, hidden1),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden1, hidden2),
            nn.ReLU(),
        )
        self.rain_head = nn.Linear(hidden2, N_HORIZONS)
        self.temp_head = nn.Linear(hidden2, N_HORIZONS)

    def forward(self, x):
        h = self.backbone(x)
        rain_logits = self.rain_head(h)
        temp_pred = self.temp_head(h)
        return rain_logits, temp_pred
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd backend && py -m pytest ml/tests/test_model.py -v`
Expected: 2件ともPASS

- [ ] **Step 5: コミット**

```bash
git add backend/ml/model.py backend/ml/tests/test_model.py
git commit -m "feat: add ForecastNet MLP model"
```

---

### Task 6: `train.py` — 学習ループとスモークテスト

**Files:**
- Create: `backend/ml/train.py`
- Test: `backend/ml/tests/test_train.py`

**Interfaces:**
- Consumes: `ml.dataset.load_observations`, `ml.dataset.build_samples`, `ml.dataset.split_by_date`, `ml.dataset.impute_missing`（Task 2-4）、`ml.model.ForecastNet`（Task 5）
- Produces:
  - `ml.train.load_stations(path: str) -> pandas.DataFrame`
  - `ml.train.train(csv_paths: list[str], stations_path: str, epochs: int = 20, val_days: int = 3, lr: float = 1e-3, batch_size: int = 256, model_path: str | None = None) -> dict` — 戻り値は`{"train_loss": list[float], "val_loss": list[float]}`（各epochの値、長さ`epochs`）。`model_path`を指定した場合はそこに`torch.save(model.state_dict(), ...)`で保存する

- [ ] **Step 1: 失敗するテストを書く**

`backend/ml/tests/test_train.py`を作成:

```python
from pathlib import Path

import pandas as pd
import pytest

from ml.train import train

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OBSERVATIONS_CSV = DATA_DIR / "observations.csv"
STATIONS_CSV = DATA_DIR / "stations.csv"


@pytest.mark.skipif(
    not OBSERVATIONS_CSV.exists() or not STATIONS_CSV.exists(),
    reason="実データCSVが無い環境ではスキップ",
)
def test_train_smoke_on_real_kansho_data(tmp_path):
    model_path = tmp_path / "model.pt"

    history = train(
        csv_paths=[str(OBSERVATIONS_CSV)],
        stations_path=str(STATIONS_CSV),
        epochs=10,
        val_days=3,
        model_path=str(model_path),
    )

    assert len(history["train_loss"]) == 10
    assert len(history["val_loss"]) == 10
    assert all(v == v for v in history["train_loss"])  # NaNでない
    assert all(v == v for v in history["val_loss"])
    assert history["train_loss"][-1] < history["train_loss"][0]
    assert model_path.exists()
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd backend && py -m pytest ml/tests/test_train.py -v`
Expected: `ModuleNotFoundError: No module named 'ml.train'` でFAIL

- [ ] **Step 3: 実装を書く**

`backend/ml/train.py`を作成:

```python
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, TensorDataset

from ml.dataset import build_samples, impute_missing, load_observations, split_by_date
from ml.model import ForecastNet

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "model.pt"


def load_stations(path):
    return pd.read_csv(path, encoding="utf-8-sig")


def train(csv_paths, stations_path, epochs=20, val_days=3, lr=1e-3, batch_size=256, model_path=None):
    df = load_observations(csv_paths)
    stations = load_stations(stations_path)
    samples = build_samples(df, stations)
    train_s, val_s = split_by_date(samples, val_days=val_days)

    X_train, X_val, _ = impute_missing(train_s["X"], val_s["X"])

    model = ForecastNet()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    bce = torch.nn.BCEWithLogitsLoss()
    mse = torch.nn.MSELoss()

    X_train_t = torch.tensor(X_train, dtype=torch.float32)
    y_rain_t = torch.tensor(train_s["y_rain"], dtype=torch.float32)
    y_temp_t = torch.tensor(train_s["y_temp"], dtype=torch.float32)
    loader = DataLoader(
        TensorDataset(X_train_t, y_rain_t, y_temp_t),
        batch_size=batch_size,
        shuffle=True,
    )

    X_val_t = torch.tensor(X_val, dtype=torch.float32)
    y_rain_val_t = torch.tensor(val_s["y_rain"], dtype=torch.float32)
    y_temp_val_t = torch.tensor(val_s["y_temp"], dtype=torch.float32)

    history = {"train_loss": [], "val_loss": []}

    for epoch in range(epochs):
        model.train()
        batch_losses = []
        for xb, yr, yt in loader:
            optimizer.zero_grad()
            rain_logits, temp_pred = model(xb)
            loss = bce(rain_logits, yr) + mse(temp_pred, yt)
            loss.backward()
            optimizer.step()
            batch_losses.append(loss.item())
        train_loss = float(np.mean(batch_losses))

        model.eval()
        with torch.no_grad():
            rain_logits, temp_pred = model(X_val_t)
            val_loss = float((bce(rain_logits, y_rain_val_t) + mse(temp_pred, y_temp_val_t)).item())

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        print(f"epoch {epoch + 1}/{epochs} train_loss={train_loss:.4f} val_loss={val_loss:.4f}")

    save_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
    torch.save(model.state_dict(), save_path)

    return history


if __name__ == "__main__":
    train(
        csv_paths=[str(DATA_DIR / "observations.csv")],
        stations_path=str(DATA_DIR / "stations.csv"),
    )
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd backend && py -m pytest ml/tests/test_train.py -v`
Expected: PASS（実データCSVが無い場合はSKIP）。実行時間は数十秒程度かかる場合がある

- [ ] **Step 5: 全テストスイートを通しで実行**

Run: `cd backend && py -m pytest ml -v`
Expected: 全件PASS（またはSKIP）、FAILなし

- [ ] **Step 6: コミット**

```bash
git add backend/ml/train.py backend/ml/tests/test_train.py
git commit -m "feat: add training loop with real-data smoke test"
```

---

## Self-Review Notes

- スペック各項目とタスクの対応: モデル構成(共通MLP/入力/出力/損失) → Task 5,6。データパイプライン(サンプル抽出条件/train-val分割) → Task 2-4。ファイル構成 → 全タスクでカバー。自己チェック(実データでのスモークテスト) → Task 6。スコープ外項目(推論エンドポイント等)は本計画に含めていない
- プレースホルダー・未定義参照なし。各タスクのコードは全て具体的な実装
- 型・シグネクチャの一貫性: `build_samples`の戻り値キー(`X, y_rain, y_temp, station_id, datetime`)をTask 4, 6で同じ名前で参照。`INPUT_DIM=199`は`WINDOW_HOURS(24)*len(FEATURE_COLUMNS)(8)+3(静的)+4(時刻)=199`とTask 3のサンプル次元計算に一致させている
