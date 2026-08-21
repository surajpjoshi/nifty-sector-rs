import os
import json
import time
from datetime import date, timedelta

import pandas as pd
import requests

# The GitHub secret can contain an Upstox Analytics Token.
# Analytics Tokens are read-only and suitable for historical-data pipelines.
TOKEN = os.environ["UPSTOX_ANALYTICS_TOKEN"]

BASE_URL = "https://api.upstox.com/v3/historical-candle"
STOCK_FILE = "data/stocks.csv"
OUTPUT_JSON = "data/stock_rs.json"
OUTPUT_CSV = "data/stock_rs.csv"

NIFTY_INSTRUMENT = "NSE_INDEX|Nifty 50"

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.20
MAX_RETRIES = 4

PERIODS = {
    "Daily": 1,
    "Weekly": 5,
    "1M": 21,
    "3M": 63,
    "6M": 126,
}


def get_headers():
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {TOKEN}",
    }


def get_daily_candles(instrument_key, from_date, to_date):
    encoded_key = instrument_key.replace("|", "%7C")
    url = (
        f"{BASE_URL}/{encoded_key}/days/1/"
        f"{to_date}/{from_date}"
    )

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                url,
                headers=get_headers(),
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                candles = response.json().get("data", {}).get("candles", [])
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

                if not rows:
                    return pd.DataFrame(
                        columns=["date", "open", "high", "low", "close", "volume"]
                    )

                result = pd.DataFrame(rows)
                result = result.drop_duplicates("date")
                return result.sort_values("date").reset_index(drop=True)

            # Retry rate-limit/server errors.
            if response.status_code in (429, 500, 502, 503, 504):
                wait = min(30, 2 ** attempt)
                print(
                    f"  API {response.status_code}; "
                    f"retry {attempt}/{MAX_RETRIES} in {wait}s"
                )
                time.sleep(wait)
                continue

            raise RuntimeError(
                f"Upstox API error {response.status_code}: "
                f"{response.text[:500]}"
            )

        except requests.RequestException as exc:
            last_error = exc
            wait = min(30, 2 ** attempt)
            print(
                f"  Network error; retry {attempt}/{MAX_RETRIES} "
                f"in {wait}s: {exc}"
            )
            time.sleep(wait)

    raise RuntimeError(f"Request failed after retries: {last_error}")


def period_return(df, periods):
    if len(df) <= periods:
        return None

    old_close = df.iloc[-1 - periods]["close"]
    new_close = df.iloc[-1]["close"]

    if old_close == 0:
        return None

    return ((new_close / old_close) - 1) * 100


def ytd_return(df):
    if df.empty:
        return None

    latest_date = df.iloc[-1]["date"]
    previous_year = latest_date.year - 1

    previous_year_rows = df[
        df["date"].apply(lambda d: d.year == previous_year)
    ]

    if previous_year_rows.empty:
        return None

    old_close = previous_year_rows.iloc[-1]["close"]
    new_close = df.iloc[-1]["close"]

    if old_close == 0:
        return None

    return ((new_close / old_close) - 1) * 100


def returns(df):
    result = {
        name: period_return(df, periods)
        for name, periods in PERIODS.items()
    }
    result["YTD"] = ytd_return(df)
    return result


def clean(value):
    return None if value is None else round(float(value), 6)


def load_master():
    df = pd.read_csv(STOCK_FILE, dtype=str).fillna("")

    required = [
        "Sector",
        "Company Name",
        "Industry",
        "Symbol",
        "Series",
        "ISIN Code",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(
            "Missing columns in stocks.csv: " + ", ".join(missing)
        )

    for column in required:
        df[column] = df[column].astype(str).str.strip()

    if (df["ISIN Code"] == "").any():
        raise RuntimeError("stocks.csv contains blank ISIN Code values.")

    return df


def align_to_nifty(stock_df, nifty_df):
    # Use only dates present in both series so stock-vs-Nifty comparisons
    # are made on the same market sessions.
    merged = stock_df[["date", "close"]].merge(
        nifty_df[["date", "close"]],
        on="date",
        how="inner",
        suffixes=("_stock", "_nifty"),
    )

    return merged.sort_values("date").reset_index(drop=True)


def calculate_aligned_returns(merged):
    if merged.empty:
        return {name: None for name in PERIODS} | {"YTD": None}

    result = {}

    for name, periods in PERIODS.items():
        if len(merged) <= periods:
            result[name] = None
            continue

        stock_old = merged.iloc[-1 - periods]["close_stock"]
        stock_new = merged.iloc[-1]["close_stock"]

        if stock_old == 0:
            result[name] = None
        else:
            result[name] = ((stock_new / stock_old) - 1) * 100

    latest_date = merged.iloc[-1]["date"]
    previous_year = latest_date.year - 1

    previous_year_rows = merged[
        merged["date"].apply(lambda d: d.year == previous_year)
    ]

    if previous_year_rows.empty:
        result["YTD"] = None
    else:
        old_close = previous_year_rows.iloc[-1]["close_stock"]
        new_close = merged.iloc[-1]["close_stock"]

        result["YTD"] = (
            None
            if old_close == 0
            else ((new_close / old_close) - 1) * 100
        )

    return result


def calculate_nifty_returns(nifty_df):
    result = {}

    for name, periods in PERIODS.items():
        result[name] = period_return(nifty_df, periods)

    result["YTD"] = ytd_return(nifty_df)

    return result


def process_unique_stock(isin, symbol, from_date, to_date, nifty_df, nifty_returns):
    instrument_key = f"NSE_EQ|{isin}"

    print(f"Fetching {symbol} ({instrument_key})...")

    stock_df = get_daily_candles(
        instrument_key,
        from_date,
        to_date,
    )

    if stock_df.empty:
        return {
            "status": "NO_DATA",
            "returns": {name: None for name in PERIODS} | {"YTD": None},
            "rs": {name: None for name in PERIODS} | {"YTD": None},
        }

    merged = align_to_nifty(stock_df, nifty_df)

    stock_returns = calculate_aligned_returns(merged)

    rs = {}
    for name in list(PERIODS.keys()) + ["YTD"]:
        stock_value = stock_returns.get(name)
        nifty_value = nifty_returns.get(name)

        if stock_value is None or nifty_value is None:
            rs[name] = None
        else:
            rs[name] = stock_value - nifty_value

    print(
        f"  3M={clean(stock_returns['3M'])}% | "
        f"Nifty 3M={clean(nifty_returns['3M'])}% | "
        f"RS 3M={clean(rs['3M'])}%"
    )

    return {
        "status": "OK",
        "returns": stock_returns,
        "rs": rs,
    }


def save_results(master, stock_results, nifty_returns):
    output = []

    for _, row in master.iterrows():
        isin = row["ISIN Code"]
        cached = stock_results.get(isin)

        if cached is None:
            cached = {
                "status": "ERROR",
                "returns": {name: None for name in PERIODS} | {"YTD": None},
                "rs": {name: None for name in PERIODS} | {"YTD": None},
            }

        stock_returns = cached["returns"]
        rs = cached["rs"]

        item = {
            "Sector": row["Sector"],
            "Company Name": row["Company Name"],
            "Industry": row["Industry"],
            "Symbol": row["Symbol"],
            "Series": row["Series"],
            "ISIN Code": isin,
            "Daily": clean(stock_returns.get("Daily")),
            "Weekly": clean(stock_returns.get("Weekly")),
            "1M": clean(stock_returns.get("1M")),
            "3M": clean(stock_returns.get("3M")),
            "6M": clean(stock_returns.get("6M")),
            "YTD": clean(stock_returns.get("YTD")),

            "Nifty Index Daily % Change": clean(nifty_returns.get("Daily")),
            "Nifty Index Weekly % Change": clean(nifty_returns.get("Weekly")),
            "Nifty Index 1M % Change": clean(nifty_returns.get("1M")),
            "Nifty Index 3M % Change": clean(nifty_returns.get("3M")),
            "Nifty Index 6M % Change": clean(nifty_returns.get("6M")),
            "Nifty Index YTD % Change": clean(nifty_returns.get("YTD")),

            "RS Daily": clean(rs.get("Daily")),
            "RS Weekly": clean(rs.get("Weekly")),
            "RS 1M": clean(rs.get("1M")),
            "RS 3M": clean(rs.get("3M")),
            "RS 6M": clean(rs.get("6M")),
            "RS YTD": clean(rs.get("YTD")),

            # Keep the original requested field name too.
            "Stock Relative Strength vs Nifty": clean(rs.get("3M")),
            "Status": cached["status"],
        }

        output.append(item)

    output_df = pd.DataFrame(output)

    # Strongest 3M RS first, while preserving every master row.
    output_df = output_df.sort_values(
        by="RS 3M",
        ascending=False,
        na_position="last",
    )

    output_df.to_csv(OUTPUT_CSV, index=False)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(
            output_df.to_dict(orient="records"),
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("Saved:", OUTPUT_CSV)
    print("Saved:", OUTPUT_JSON)


def main():
    print("=" * 70)
    print("NIFTY MASTER STOCK RELATIVE STRENGTH")
    print("=" * 70)

    today = date.today()

    # Long enough for 6M and YTD, while staying comfortably inside
    # the V3 daily historical-data availability.
    from_date = today - timedelta(days=450)

    from_date_str = from_date.isoformat()
    to_date_str = today.isoformat()

    master = load_master()

    print(f"Master rows      : {len(master)}")
    print(f"Unique symbols   : {master['Symbol'].nunique()}")
    print(f"Unique ISINs     : {master['ISIN Code'].nunique()}")
    print(f"Date range       : {from_date_str} -> {to_date_str}")

    print()
    print("Fetching NIFTY 50...")
    nifty_df = get_daily_candles(
        NIFTY_INSTRUMENT,
        from_date_str,
        to_date_str,
    )

    if nifty_df.empty:
        raise RuntimeError("No NIFTY 50 data returned.")

    print("NIFTY candles:", len(nifty_df))

    nifty_returns = calculate_nifty_returns(nifty_df)

    print(
        "NIFTY returns:",
        {k: clean(v) for k, v in nifty_returns.items()},
    )

    # The uploaded master contains the same stock in multiple Nifty indices.
    # Fetch each ISIN only once, then reuse its result for every sector/index row.
    unique_stocks = (
        master[["ISIN Code", "Symbol"]]
        .drop_duplicates(subset=["ISIN Code"])
        .reset_index(drop=True)
    )

    stock_results = {}
    total = len(unique_stocks)

    for index, row in unique_stocks.iterrows():
        print(f"[{index + 1}/{total}]")

        isin = row["ISIN Code"]
        symbol = row["Symbol"]

        try:
            stock_results[isin] = process_unique_stock(
                isin,
                symbol,
                from_date_str,
                to_date_str,
                nifty_df,
                nifty_returns,
            )
        except Exception as error:
            print(f"  ERROR: {error}")
            stock_results[isin] = {
                "status": "ERROR",
                "returns": {name: None for name in PERIODS} | {"YTD": None},
                "rs": {name: None for name in PERIODS} | {"YTD": None},
            }

        time.sleep(REQUEST_DELAY)

    save_results(master, stock_results, nifty_returns)

    successful = sum(
        1 for value in stock_results.values()
        if value["status"] == "OK"
    )
    no_data = sum(
        1 for value in stock_results.values()
        if value["status"] == "NO_DATA"
    )
    errors = total - successful - no_data

    print()
    print("=" * 70)
    print("COMPLETED")
    print("=" * 70)
    print("Master rows     :", len(master))
    print("Unique ISINs     :", total)
    print("Successful      :", successful)
    print("No data         :", no_data)
    print("Errors           :", errors)
    print("=" * 70)


if __name__ == "__main__":
    main()
