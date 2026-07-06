# --- 仮想時計(server.py) --------------------------------------------------
STEP_INTERVAL_SEC = 0.5
LOOP = True
START_INDEX = 800

# --- データファイル(server.py) --------------------------------------------
STATIONS_GLOB = "data/stations*.csv"
OBSERVATIONS_GLOB = "data/observations*.csv"

# --- サーバ(生データ配信 server.py) ---------------------------------------
SERVER_HOST = "localhost"
SERVER_PORT = 8000

# --- 処理系(WBGT加工 + SSE client.py) -------------------------------------
CLIENT_HOST = "localhost"
CLIENT_PORT = 8001
POLL_INTERVAL_SEC = 0.5   # client が server を見に行く間隔
STREAM_CHECK_SEC = 0.5    # SSE が新フレームを確認してフロントへ push する間隔

SOURCE = f"http://{SERVER_HOST}:{SERVER_PORT}"
