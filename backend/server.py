import csv
import glob
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import config


NUMERIC_FIELDS = {
    "temp", "precip", "humidity", "solar", "sunshine",
    "wind_speed", "vapor_pressure", "dew_point",
}
STATION_NUMERIC = {"lat", "lon", "elev"}



class WeatherData:
    def __init__(self):
        self.stations = []
        self.station_by_id = {}
        self.obs_by_time = {}
        self.obs_by_station = {}
        self.times = []
        self._load()

    @staticmethod
    def _num(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except ValueError:
            return None

    def _load(self):
        # 官署+アメダスなど複数ファイルをまとめて読む
        for st_path in sorted(glob.glob(config.STATIONS_GLOB)):
            with open(st_path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    for k in STATION_NUMERIC:
                        if k in row:
                            row[k] = self._num(row[k])
                    self.stations.append(row)
                    self.station_by_id[row["station_id"]] = row

        for obs_path in sorted(glob.glob(config.OBSERVATIONS_GLOB)):
            with open(obs_path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    for k in NUMERIC_FIELDS:
                        if k in row:
                            row[k] = self._num(row[k])
                    for k in ("wind_dir", "cloud"):
                        if row.get(k) == "":
                            row[k] = None
                    t = row["datetime"]
                    self.obs_by_time.setdefault(t, []).append(row)
                    self.obs_by_station.setdefault(row["station_id"], []).append(row)

        self.times = sorted(self.obs_by_time.keys())
        for sid in self.obs_by_station:
            self.obs_by_station[sid].sort(key=lambda r: r["datetime"])

    def station_meta(self, sid):
        s = self.station_by_id.get(sid)
        if not s:
            return {}
        return {"lat": s.get("lat"), "lon": s.get("lon"),
                "elev": s.get("elev"), "type": s.get("type")}

    def snapshot(self, t, station_id=None):
        rows = self.obs_by_time.get(t, [])
        out = []
        for r in rows:
            if station_id and r["station_id"] != station_id:
                continue
            merged = dict(r)
            merged.update(self.station_meta(r["station_id"]))
            out.append(merged)
        return out


class VirtualClock:

    def __init__(self, times, step_interval_sec, loop, start_index):
        self.times = times
        self.step_interval_sec = step_interval_sec
        self.loop = loop
        self.start_index = max(0, min(start_index, len(times) - 1)) if times else 0
        self.t0 = time.monotonic()

    def index(self):
        elapsed = time.monotonic() - self.t0
        steps = int(elapsed // self.step_interval_sec)
        i = self.start_index + steps
        n = len(self.times)
        if n == 0:
            return 0
        if self.loop:
            return i % n
        return min(i, n - 1)

    def state(self):
        i = self.index()
        n = len(self.times)
        return {
            "datetime": self.times[i] if n else None,
            "index": i,
            "total": n,
            "looping": self.loop,
            "step_interval_sec": self.step_interval_sec,
            "elapsed_sec": round(time.monotonic() - self.t0, 1),
        }


app = FastAPI(title="Weather CSV API", description="気象観測CSVの配信API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

data = WeatherData()
clock = VirtualClock(
    data.times, config.STEP_INTERVAL_SEC, config.LOOP, config.START_INDEX,
)


@app.get("/")
def index():
    return {
        "endpoints": {
            "/now": "今の仮想時刻の全地点スナップショット",
            "/clock": "今の仮想時刻だけ",
            "/stations": "地点マスタ",
            "/times": "時刻一覧",
            "/at": "?t=時刻 で全地点スナップショット",
            "/observations": "?station_id= の時系列",
            "/latest": "各地点の最新値",
            "/docs": "Swagger UI",
        },
        "station_count": len(data.stations),
        "time_count": len(data.times),
        "time_range": [data.times[0], data.times[-1]] if data.times else [],
    }


@app.get("/clock")
def get_clock():
    return clock.state()


@app.get("/now")
def get_now(station_id: Optional[str] = Query(None)):
    st = clock.state()
    t = st["datetime"]
    snap = data.snapshot(t, station_id) if t else []
    return {**st, "count": len(snap), "observations": snap}


@app.get("/stations")
def get_stations(type: Optional[str] = Query(None, description="官署 / アメダス")):
    items = data.stations
    if type:
        items = [s for s in items if s.get("type") == type]
    return {"count": len(items), "stations": items}


@app.get("/times")
def get_times():
    return {"count": len(data.times), "times": data.times}


@app.get("/at")
def get_at(
    t: str = Query(..., description="時刻 YYYY-MM-DD HH:MM:SS"),
    station_id: Optional[str] = Query(None),
):
    t = t.replace("T", " ")
    snap = data.snapshot(t, station_id)
    return {"datetime": t, "count": len(snap), "observations": snap}


@app.get("/observations")
def get_observations(
    station_id: str = Query(..., description="地点ID 例 s47662"),
    start: Optional[str] = Query(None, description="開始時刻(含む)"),
    end: Optional[str] = Query(None, description="終了時刻(含む)"),
    limit: Optional[int] = Query(None, ge=1),
):
    rows = data.obs_by_station.get(station_id)
    if rows is None:
        raise HTTPException(status_code=404, detail=f"unknown station_id: {station_id}")
    if start:
        rows = [r for r in rows if r["datetime"] >= start]
    if end:
        rows = [r for r in rows if r["datetime"] <= end]
    if limit:
        rows = rows[:limit]
    return {"station_id": station_id, "count": len(rows), "observations": rows}


@app.get("/latest")
def get_latest(station_id: Optional[str] = Query(None)):
    if station_id:
        rows = data.obs_by_station.get(station_id)
        if rows is None:
            raise HTTPException(status_code=404, detail=f"unknown station_id: {station_id}")
        return {"observation": rows[-1] if rows else None}
    latest = []
    for sid, rows in data.obs_by_station.items():
        if rows:
            m = dict(rows[-1])
            m.update(data.station_meta(sid))
            latest.append(m)
    latest.sort(key=lambda r: r["station_id"])
    return {"count": len(latest), "observations": latest}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT)
