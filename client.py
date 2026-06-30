import requests

API = "http://localhost:8000"


def main():
    res = requests.get(API + "/now", timeout=30)
    res.raise_for_status()
    data = res.json()

    t = data["datetime"]
    obs = data["observations"]

    hottest = None
    for o in obs:
        temp = o.get("temp")
        if temp is None:
            continue
        if hottest is None or temp > hottest["temp"]:
            hottest = o

    print(f"時刻: {t}")
    print(f"最高気温: {hottest['name']}({hottest['station_id']}) {hottest['temp']}℃")


if __name__ == "__main__":
    main()
