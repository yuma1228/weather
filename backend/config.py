from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RUNTIME_DATA_DIR = DATA_DIR / "runtime"

# --- 仮想時計(server.py) --------------------------------------------------
STEP_INTERVAL_SEC = 1
LOOP = True
START_INDEX = 800

# --- データファイル(server.py) --------------------------------------------
STATIONS_GLOB = str(DATA_DIR / "stations*.csv")
OBSERVATIONS_GLOB = str(RUNTIME_DATA_DIR / "observations*.csv")
# 観測CSVは官署+アメダスで計10年超・数GBあり全件をメモリに載せるとOOMするため、
# 実行用CSVの最新日時から遡ってこの日数分だけメモリへ読み込む。
LOAD_RECENT_DAYS = 30

# --- サーバ(生データ配信 server.py) ---------------------------------------
SERVER_HOST = "localhost"
SERVER_PORT = 8000

# --- 処理系(WBGT加工 + SSE client.py) -------------------------------------
CLIENT_HOST = "localhost"
CLIENT_PORT = 8001
POLL_INTERVAL_SEC =   0.5 # client が server を見に行く間隔
STREAM_CHECK_SEC =  0.5# SSE が新フレームを確認してフロントへ push する間隔

HISTORY_MAX = 24 # client が保持する時刻数(=平均を出せる最大時間)

SOURCE = f"http://{SERVER_HOST}:{SERVER_PORT}"
