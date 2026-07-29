"""Runtime feature construction and LightGBM inference."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import lightgbm as lgb
import numpy as np
import pandas as pd


VARS = ("temp", "precip", "wind_speed")
HISTORY_HOURS = 24
HORIZONS = (1, 6, 12, 24)
NEIGHBOR_COUNT = 5
DT_FMT = "%Y-%m-%d %H:%M:%S"
EXPECTED_FEATURES = len(VARS) * HISTORY_HOURS + 5 + len(VARS) * NEIGHBOR_COUNT

ObservationGetter = Callable[[str, str], dict | None]


class ForecastUnavailable(RuntimeError):
    """The requested station/time cannot be forecast."""


class ForecastService:
    def __init__(self, stations_csv: Path, models_dir: Path) -> None:
        self.stations_csv = Path(stations_csv)
        self.models_dir = Path(models_dir)
        self._load_lock = threading.Lock()
        self._models: dict[tuple[str, int], lgb.Booster] | None = None
        self._station_meta: pd.DataFrame | None = None
        self._station_ids: np.ndarray | None = None
        self._station_lat_rad: np.ndarray | None = None
        self._station_lon_rad: np.ndarray | None = None
        self._neighbor_cache: dict[str, tuple[str, ...]] = {}

    def _ensure_loaded(self) -> None:
        if self._models is not None:
            return
        with self._load_lock:
            if self._models is not None:
                return
            if not self.stations_csv.is_file():
                raise ForecastUnavailable(
                    f"予測用地点マスターがありません: {self.stations_csv.name}"
                )

            meta = pd.read_csv(
                self.stations_csv,
                encoding="utf-8-sig",
                dtype={"station_id": "string"},
            ).set_index("station_id")
            required = {"lat", "lon", "elev"}
            missing = required.difference(meta.columns)
            if missing:
                raise ForecastUnavailable(
                    f"予測用地点マスターに必要な列がありません: {sorted(missing)}"
                )

            ids = meta.index.to_numpy(str)
            lat = np.radians(meta["lat"].to_numpy(float))
            lon = np.radians(meta["lon"].to_numpy(float))
            usable = np.isfinite(lat) & np.isfinite(lon)
            self._station_meta = meta
            self._station_ids = ids[usable]
            self._station_lat_rad = lat[usable]
            self._station_lon_rad = lon[usable]

            models: dict[tuple[str, int], lgb.Booster] = {}
            for target in ("precip", "temp"):
                for horizon in HORIZONS:
                    path = self.models_dir / f"lgb_{target}_{horizon}h.txt"
                    if not path.is_file():
                        raise ForecastUnavailable(f"予測モデルがありません: {path.name}")
                    model = lgb.Booster(model_file=str(path))
                    if model.num_feature() != EXPECTED_FEATURES:
                        raise ForecastUnavailable(
                            f"{path.name} の特徴量数が不正です: "
                            f"{model.num_feature()} (expected {EXPECTED_FEATURES})"
                        )
                    models[(target, horizon)] = model
            self._models = models

    @staticmethod
    def _number(value: object) -> float:
        if value is None or value == "":
            return np.nan
        try:
            result = float(value)
        except (TypeError, ValueError):
            return np.nan
        return result if np.isfinite(result) else np.nan

    def _nearest_station_ids(
        self, station_id: str, lat: float, lon: float
    ) -> tuple[str, ...]:
        cached = self._neighbor_cache.get(station_id)
        if cached is not None:
            return cached

        assert self._station_ids is not None
        assert self._station_lat_rad is not None
        assert self._station_lon_rad is not None
        lat_rad = np.radians(lat)
        lon_rad = np.radians(lon)
        dlat = self._station_lat_rad - lat_rad
        dlon = self._station_lon_rad - lon_rad
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(lat_rad)
            * np.cos(self._station_lat_rad)
            * np.sin(dlon / 2) ** 2
        )
        distance = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        distance[self._station_ids == station_id] = np.inf
        order = np.argsort(distance)[:NEIGHBOR_COUNT]
        neighbors = tuple(self._station_ids[order].tolist())
        if len(neighbors) != NEIGHBOR_COUNT:
            raise ForecastUnavailable("近隣地点が不足しているため予測できません")
        self._neighbor_cache[station_id] = neighbors
        return neighbors

    def _features(
        self,
        station_id: str,
        based_at: datetime,
        station: dict,
        observation_at: ObservationGetter,
    ) -> np.ndarray:
        lat = self._number(station.get("lat"))
        lon = self._number(station.get("lon"))
        if not np.isfinite(lat) or not np.isfinite(lon):
            raise ForecastUnavailable("緯度・経度がない地点は予測できません")
        if not np.isfinite(self._number(station.get("temp"))):
            raise ForecastUnavailable("現在気温が欠測しているため予測できません")
        if not np.isfinite(self._number(station.get("precip"))):
            raise ForecastUnavailable("現在降水量が欠測しているため予測できません")

        values: list[float] = []
        for variable in VARS:
            for lag in range(HISTORY_HOURS):
                at = (based_at - timedelta(hours=lag)).strftime(DT_FMT)
                row = observation_at(at, station_id)
                values.append(self._number(row.get(variable)) if row else np.nan)

        values.extend(
            [
                lat,
                lon,
                self._number(station.get("elev")),
                float(based_at.month),
                float(based_at.hour),
            ]
        )

        for neighbor_id in self._nearest_station_ids(station_id, lat, lon):
            row = observation_at(based_at.strftime(DT_FMT), neighbor_id)
            for variable in VARS:
                values.append(self._number(row.get(variable)) if row else np.nan)

        features = np.asarray(values, dtype=np.float32).reshape(1, -1)
        if features.shape[1] != EXPECTED_FEATURES:
            raise RuntimeError(
                f"runtime feature mismatch: {features.shape[1]} != {EXPECTED_FEATURES}"
            )
        return features

    def predict(
        self,
        station_id: str,
        based_at_text: str,
        station: dict,
        observation_at: ObservationGetter,
    ) -> dict:
        self._ensure_loaded()
        assert self._models is not None
        try:
            based_at = datetime.strptime(based_at_text, DT_FMT)
        except ValueError as ex:
            raise ForecastUnavailable("予測基準時刻の形式が不正です") from ex

        features = self._features(
            station_id=station_id,
            based_at=based_at,
            station=station,
            observation_at=observation_at,
        )
        forecasts = []
        for horizon in HORIZONS:
            rain_probability = float(
                self._models[("precip", horizon)].predict(features)[0]
            )
            temperature = float(self._models[("temp", horizon)].predict(features)[0])
            if not np.isfinite(rain_probability) or not np.isfinite(temperature):
                raise ForecastUnavailable("モデルが有効な予測値を返しませんでした")
            forecasts.append(
                {
                    "hours": horizon,
                    "datetime": (based_at + timedelta(hours=horizon)).strftime(DT_FMT),
                    "temperature": round(temperature, 1),
                    "rain_probability": round(
                        float(np.clip(rain_probability, 0.0, 1.0)), 4
                    ),
                }
            )

        return {
            "station_id": station_id,
            "based_at": based_at_text,
            "model": "LightGBM",
            "forecasts": forecasts,
        }
