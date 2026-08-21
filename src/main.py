import os
import json
import time
from datetime import date, timedelta

import pandas as pd
import requests


ACCESS_TOKEN = os.environ["UPSTOX_ACCESS_TOKEN"]

BASE_URL = "https://api.upstox.com/v3/historical-candle"

STOCK_FILE = "data/stocks.csv"
OUTPUT_JSON = "data/stock_rs.json"
OUTPUT_CSV = "data/stock_rs.csv"

NIFTY_INSTRUMENT = "NSE_INDEX|Nifty 50"

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.15


def get_headers():
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }


def get_daily_candles(instrument_key, from_date, to_date):
    encoded_key = instrument_key.replace("|", "%7C")

    url = (
        f"{BASE_URL}/"
        f"{encoded_key}/"
        f"days/1/"
        f"{to_date}/"
        f"{from_date}"
    )

    response = requests.get(
        url,
        headers=get_headers(),
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Upstox API error {response.status_code} "
            f"for {instrument_key}: {response.text}"
        )

    data = response.json()

    candles = data.get("data", {}).get("candles", [])

    if not candles:
        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "volume"]
        )

    rows = []

    for candle in candles:
        rows.append(
            {
                "date": pd.to_datetime(candle[0]).date(),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
            }
        )

    df = pd.DataFrame(rows)

    df = df.drop_duplicates(subset=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    return df


def calculate_return(df, periods):
    if len(df) <= periods:
        return None

    latest_close = df.iloc[-1]["close"]
    previous_close = df.iloc[-1 - periods]["close"]

    if previous_close == 0:
        return None

    return ((latest_close / previous_close) - 1) * 100


def calculate_ytd(df):
    if df.empty:
        return None

    latest_date = df.iloc[-1]["date"]
    current_year = latest_date.year

    previous_year_data = df[df["date"].apply(lambda x: x.year < current_year)]

    if previous_year_data.empty:
        return None

    previous_year_close = previous_year_data.iloc[-1]["close"]
    latest_close = df.iloc[-1]["close"]

    if previous_year_close == 0:
        return None

    return ((latest_close / previous_year_close) - 1) * 100


def calculate_returns(df):
    return {
        "daily": calculate_return(df, 1),
        "weekly": calculate_return(df, 5),
        "1m": calculate_return(df, 21),
        "3m": calculate_return(df, 63),
        "6m": calculate_return(df, 126),
        "ytd": calculate_ytd(df),
    }


def clean_number(value):
    if value is None:
        return None

    return round(float(value), 6)


def fetch_nifty_return(from_date, to_date):
    print()
    print("Fetching NIFTY 50...")

    nifty_df = get_daily_candles(
        NIFTY_INSTRUMENT,
        from_date,
        to_date,
    )

    print("NIFTY candles:", len(nifty_df))

    if nifty_df.empty:
        raise RuntimeError("No NIFTY 50 data returned.")

    nifty_returns = calculate_returns(nifty_df)

    print(
        "NIFTY returns:",
        {
            key: clean_number(value)
            for key, value in nifty_returns.items()
        },
    )

    return nifty_returns


def load_stocks():
    df = pd.read_csv(STOCK_FILE)

    required_columns = [
        "Sector",
        "Company Name",
        "Industry",
        "Symbol",
        "Series",
        "ISIN Code",
        "NSE Symbol",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            "Missing columns in stocks.csv: "
            + ", ".join(missing)
        )

    df = df.fillna("")

    return df


def process_stock(row, from_date, to_date, nifty_returns):
    symbol = str(row["Symbol"]).strip()
    isin = str(row["ISIN Code"]).strip()

    instrument_key = f"NSE_EQ|{isin}"

    print(f"Fetching {symbol} ({instrument_key})...")

    df = get_daily_candles(
        instrument_key,
        from_date,
        to_date,
    )

    if df.empty:
        print(f"  WARNING: No data for {symbol}")
        return {
            "Sector": row["Sector"],
            "Company Name": row["Company Name"],
            "Industry": row["Industry"],
            "Symbol": symbol,
            "Series": row["Series"],
            "ISIN Code": isin,
            "NSE Symbol": row["NSE Symbol"],
            "Daily": None,
            "Weekly": None,
            "1M": None,
            "3M": None,
            "6M": None,
            "YTD": None,
            "Nifty Index 3M % Change": clean_number(
                nifty_returns.get("3m")
            ),
            "Stock Relative Strength vs Nifty": None,
            "Status": "NO_DATA",
        }

    returns = calculate_returns(df)

    stock_3m = returns.get("3m")
    nifty_3m = nifty_returns.get("3m")

    if stock_3m is not None and nifty_3m is not None:
        relative_strength = stock_3m - nifty_3m
    else:
        relative_strength = None

    result = {
        "Sector": row["Sector"],
        "Company Name": row["Company Name"],
        "Industry": row["Industry"],
        "Symbol": symbol,
        "Series": row["Series"],
        "ISIN Code": isin,
        "NSE Symbol": row["NSE Symbol"],
        "Daily": clean_number(returns.get("daily")),
        "Weekly": clean_number(returns.get("weekly")),
        "1M": clean_number(returns.get("1m")),
        "3M": clean_number(returns.get("3m")),
        "6M": clean_number(returns.get("6m")),
        "YTD": clean_number(returns.get("ytd")),
        "Nifty Index 3M % Change": clean_number(nifty_3m),
        "Stock Relative Strength vs Nifty": clean_number(
            relative_strength
        ),
        "Status": "OK",
    }

    print(
        f"  3M: {result['3M']}% | "
        f"Nifty: {result['Nifty Index 3M % Change']}% | "
        f"RS: {result['Stock Relative Strength vs Nifty']}%"
    )

    return result


def save_results(results):
    os.makedirs("data", exist_ok=True)

    df = pd.DataFrame(results)

    # Sort strongest stocks first by 3M relative strength
    if "Stock Relative Strength vs Nifty" in df.columns:
        df = df.sort_values(
            by="Stock Relative Strength vs Nifty",
            ascending=False,
            na_position="last",
        )

    df.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            results,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("Saved:")
    print(OUTPUT_CSV)
    print(OUTPUT_JSON)


def main():
    print("=" * 70)
    print("NIFTY SECTOR RELATIVE STRENGTH")
    print("=" * 70)

    today = date.today()

    # 200 calendar days gives enough trading sessions
    # for 6M calculations.
    from_date = today - timedelta(days=250)

    from_date_str = from_date.isoformat()
    to_date_str = today.isoformat()

    print()
    print("Date range:")
    print("From:", from_date_str)
    print("To  :", to_date_str)

    stocks = load_stocks()

    print()
    print("Stocks loaded:", len(stocks))

    nifty_returns = fetch_nifty_return(
        from_date_str,
        to_date_str,
    )

    results = []

    total = len(stocks)

    for index, (_, row) in enumerate(stocks.iterrows(), start=1):

        print()
        print(f"[{index}/{total}]")

        try:
            result = process_stock(
                row,
                from_date_str,
                to_date_str,
                nifty_returns,
            )

            results.append(result)

        except Exception as error:
            print(
                f"ERROR processing "
                f"{row['Symbol']}: {error}"
            )

            results.append(
                {
                    "Sector": row["Sector"],
                    "Company Name": row["Company Name"],
                    "Industry": row["Industry"],
                    "Symbol": row["Symbol"],
                    "Series": row["Series"],
                    "ISIN Code": row["ISIN Code"],
                    "NSE Symbol": row["NSE Symbol"],
                    "Daily": None,
                    "Weekly": None,
                    "1M": None,
                    "3M": None,
                    "6M": None,
                    "YTD": None,
                    "Nifty Index 3M % Change": clean_number(
                        nifty_returns.get("3m")
                    ),
                    "Stock Relative Strength vs Nifty": None,
                    "Status": "ERROR",
                    "Error": str(error),
                }
            )

        time.sleep(REQUEST_DELAY)

    save_results(results)

    successful = sum(
        1
        for item in results
        if item.get("Status") == "OK"
    )

    print()
    print("=" * 70)
    print("COMPLETED")
    print("=" * 70)
    print("Total stocks:", total)
    print("Successful  :", successful)
    print("Failed      :", total - successful)
    print("=" * 70)


if __name__ == "__main__":
    main()