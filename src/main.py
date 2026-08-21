import os
import requests
from datetime import date, timedelta

ACCESS_TOKEN = os.environ["UPSTOX_ACCESS_TOKEN"]
INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"
BASE_URL = "https://api.upstox.com/v3/historical-candle"


def get_daily_data(instrument_key, from_date, to_date):
    encoded_key = instrument_key.replace("|", "%7C")
    url = (
        f"{BASE_URL}/{encoded_key}/days/1/"
        f"{to_date}/{from_date}"
    )

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }

    response = requests.get(url, headers=headers, timeout=30)

    print("HTTP Status:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        response.raise_for_status()

    return response.json()


def main():
    today = date.today()
    from_date = today - timedelta(days=400)

    print("Fetching NIFTY 50 data...")
    print("From:", from_date)
    print("To:", today)

    data = get_daily_data(
        INSTRUMENT_KEY,
        from_date.isoformat(),
        today.isoformat(),
    )

    candles = data["data"]["candles"]

    print()
    print("Total candles:", len(candles))
    print()

    for candle in candles[-5:]:
        print(candle)


if __name__ == "__main__":
    main()
