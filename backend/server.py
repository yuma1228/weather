import csv
import glob
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config


NUMERIC_FIELDS = {
    "temp", "precip", "humidity", "solar", "sunshine",
    "wind_speed", "vapor_pressure", "dew_point",
}
STATION_NUMERIC = {"lat", "lon", "elev"}



class WeatherData:
    def __init__(self):
        self.station_by_id = {}
        self.obs_by_time = {}
        self.times = []
        self._load()

    @staticmethod
    def _num(v: str | None) -> float | None:
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

        self.times = sorted(self.obs_by_time.keys())

    def station_meta(self, sid: str) -> dict:
        s = self.station_by_id.get(sid)
        if not s:
            return {}
        return {"lat": s.get("lat"), "lon": s.get("lon"),
                "elev": s.get("elev"), "type": s.get("type")}

    def snapshot(self, t: str, station_id: str | None = None) -> list[dict]:
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

    def index(self) -> int:
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
        return {
            "datetime": self.times[i] if self.times else None,
            "index": i,
        }


app = FastAPI(title="Weather CSV API", description="気象観測CSVの配信API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

data = WeatherData()
clock = VirtualClock(
    data.times, config.STEP_INTERVAL_SEC, config.LOOP, config.START_INDEX,
)

@app.get("/clock")
def get_clock():
    return clock.state()


@app.get("/now")
def get_now(station_id: str | None = None):
    st = clock.state()
    t = st["datetime"]
    snap = data.snapshot(t, station_id) if t else []
    return {"datetime": t, "observations": snap}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT)
