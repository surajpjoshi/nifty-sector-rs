import os
import json
import time
import gzip
from datetime import date, timedelta

import pandas as pd
import requests


ACCESS_TOKEN = os.environ["UPSTOX_ANALYTICS_TOKEN"]

BASE_URL = "https://api.upstox.com/v3/historical-candle"

# Upstox official NSE BOD instrument file.
INSTRUMENT_MASTER_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
)

STOCK_FILE = "data/stocks.csv"
OUTPUT_JSON = "data/stock_rs.json"
OUTPUT_CSV = "data/stock_rs.csv"
MAPPING_CSV = "data/instrument_mapping.csv"

NIFTY_INSTRUMENT = "NSE_INDEX|Nifty 50"

REQUEST_TIMEOUT = 60
REQUEST_DELAY = 0.15


def get_headers():
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }


def download_instrument_master():
    print()
    print("Downloading Upstox instrument master...")

    response = requests.get(
        INSTRUMENT_MASTER_URL,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    print(
        "Instrument master downloaded:",
        len(response.content),
        "bytes",
    )

    try:
        raw = gzip.decompress(response.content)
    except OSError:
        raw = response.content

    instruments = json.loads(raw.decode("utf-8"))

    print(
        "Total instruments in master:",
        len(instruments),
    )

    return instruments


def build_nse_equity_mapping(instruments):
    mapping = {}

    for instrument in instruments:

        if instrument.get("segment") != "NSE_EQ":
            continue

        instrument_type = str(
            instrument.get("instrument_type", "")
        ).upper()

        if instrument_type not in ("EQ", "BE"):
            continue

        isin = str(
            instrument.get("isin", "")
        ).strip().upper()

        if not isin:
            continue

        instrument_key = str(
            instrument.get("instrument_key", "")
        ).strip()

        if not instrument_key:
            continue

        trading_symbol = str(
            instrument.get("trading_symbol", "")
        ).strip()

        mapping[isin] = {
            "instrument_key": instrument_key,
            "trading_symbol": trading_symbol,
            "instrument_type": instrument_type,
            "name": instrument.get("name", ""),
        }

    print(
        "NSE equity ISIN mappings:",
        len(mapping),
    )

    return mapping


def get_daily_candles(
    instrument_key,
    from_date,
    to_date,
):
    encoded_key = instrument_key.replace(
        "|",
        "%7C",
    )

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
            f"Upstox API error "
            f"{response.status_code}: "
            f"{response.text}"
        )

    data = response.json()

    candles = data.get(
        "data",
        {},
    ).get(
        "candles",
        [],
    )

    if not candles:
        return pd.DataFrame(
            columns=[
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    rows = []

    for candle in candles:
        rows.append(
            {
                "date": pd.to_datetime(
                    candle[0]
                ).date(),

                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
            }
        )

    df = pd.DataFrame(rows)

    df = df.drop_duplicates(
        subset=["date"]
    )

    df = df.sort_values(
        "date"
    ).reset_index(
        drop=True
    )

    return df


def calculate_return(df, periods):

    if len(df) <= periods:
        return None

    latest_close = df.iloc[-1]["close"]

    previous_close = df.iloc[
        -1 - periods
    ]["close"]

    if previous_close == 0:
        return None

    return (
        (latest_close / previous_close)
        - 1
    ) * 100


def calculate_ytd(df):

    if df.empty:
        return None

    latest_date = df.iloc[-1]["date"]

    current_year = latest_date.year

    previous_year_data = df[
        df["date"].apply(
            lambda x:
            x.year < current_year
        )
    ]

    if previous_year_data.empty:
        return None

    previous_year_close = (
        previous_year_data.iloc[-1]["close"]
    )

    latest_close = df.iloc[-1]["close"]

    if previous_year_close == 0:
        return None

    return (
        (latest_close / previous_year_close)
        - 1
    ) * 100


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

    return round(
        float(value),
        6,
    )


def fetch_nifty_return(
    from_date,
    to_date,
):

    print()
    print("Fetching NIFTY 50...")

    nifty_df = get_daily_candles(
        NIFTY_INSTRUMENT,
        from_date,
        to_date,
    )

    print(
        "NIFTY candles:",
        len(nifty_df),
    )

    if nifty_df.empty:
        raise RuntimeError(
            "No NIFTY 50 data returned."
        )

    nifty_returns = calculate_returns(
        nifty_df
    )

    print(
        "NIFTY returns:",
        {
            key: clean_number(value)
            for key, value
            in nifty_returns.items()
        },
    )

    return nifty_returns


def load_stocks():

    df = pd.read_csv(
        STOCK_FILE,
        dtype=str,
    )

    required_columns = [
        "Sector",
        "Company Name",
        "Industry",
        "Symbol",
        "Series",
        "ISIN Code",
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


def create_unique_stock_list(stocks):

    unique = (
        stocks[
            [
                "Symbol",
                "ISIN Code",
            ]
        ]
        .drop_duplicates(
            subset=["ISIN Code"]
        )
    )

    unique = unique[
        unique["ISIN Code"].str.strip() != ""
    ]

    return unique


def save_mapping_report(
    stocks,
    instrument_mapping,
):

    rows = []

    unique_stocks = create_unique_stock_list(
        stocks
    )

    for _, row in unique_stocks.iterrows():

        isin = str(
            row["ISIN Code"]
        ).strip().upper()

        mapped = instrument_mapping.get(
            isin
        )

        rows.append(
            {
                "Symbol": row["Symbol"],
                "ISIN Code": isin,
                "Upstox Instrument Key": (
                    mapped["instrument_key"]
                    if mapped
                    else ""
                ),
                "Upstox Trading Symbol": (
                    mapped["trading_symbol"]
                    if mapped
                    else ""
                ),
                "Instrument Type": (
                    mapped["instrument_type"]
                    if mapped
                    else ""
                ),
                "Mapping Status": (
                    "FOUND"
                    if mapped
                    else "NOT_FOUND"
                ),
            }
        )

    pd.DataFrame(rows).to_csv(
        MAPPING_CSV,
        index=False,
    )

    print()
    print(
        "Saved:",
        MAPPING_CSV,
    )


def process_stock(
    row,
    from_date,
    to_date,
    nifty_returns,
    instrument_mapping,
):

    symbol = str(
        row["Symbol"]
    ).strip()

    isin = str(
        row["ISIN Code"]
    ).strip().upper()

    mapped = instrument_mapping.get(
        isin
    )

    if not mapped:

        print(
            f"  ERROR: No Upstox NSE instrument "
            f"mapping for {symbol} / {isin}"
        )

        return {
            "status": "MAPPING_NOT_FOUND",
            "symbol": symbol,
            "isin": isin,
        }

    instrument_key = mapped[
        "instrument_key"
    ]

    print(
        f"Fetching {symbol} "
        f"({instrument_key})..."
    )

    df = get_daily_candles(
        instrument_key,
        from_date,
        to_date,
    )

    if df.empty:

        print(
            f"  WARNING: No data for {symbol}"
        )

        return {
            "status": "NO_DATA",
            "symbol": symbol,
            "isin": isin,
        }

    returns = calculate_returns(df)

    stock_3m = returns.get("3m")

    nifty_3m = nifty_returns.get("3m")

    if (
        stock_3m is not None
        and nifty_3m is not None
    ):
        relative_strength = (
            stock_3m
            - nifty_3m
        )
    else:
        relative_strength = None

    result = {
        "Sector": row["Sector"],
        "Company Name": row["Company Name"],
        "Industry": row["Industry"],
        "Symbol": symbol,
        "Series": row["Series"],
        "ISIN Code": isin,
        "NSE Symbol": (
            row.get("NSE Symbol", "")
        ),

        "Daily": clean_number(
            returns.get("daily")
        ),

        "Weekly": clean_number(
            returns.get("weekly")
        ),

        "1M": clean_number(
            returns.get("1m")
        ),

        "3M": clean_number(
            returns.get("3m")
        ),

        "6M": clean_number(
            returns.get("6m")
        ),

        "YTD": clean_number(
            returns.get("ytd")
        ),

        "Nifty Index 3M % Change":
            clean_number(
                nifty_3m
            ),

        "Stock Relative Strength vs Nifty":
            clean_number(
                relative_strength
            ),

        "Upstox Instrument Key":
            instrument_key,

        "Status": "OK",
    }

    print(
        f"  3M={result['3M']}% | "
        f"Nifty 3M="
        f"{result['Nifty Index 3M % Change']}% | "
        f"RS 3M="
        f"{result['Stock Relative Strength vs Nifty']}%"
    )

    return result


def save_results(results):

    os.makedirs(
        "data",
        exist_ok=True,
    )

    df = pd.DataFrame(
        results
    )

    if (
        "Stock Relative Strength vs Nifty"
        in df.columns
    ):

        df = df.sort_values(
            by=(
                "Stock Relative Strength "
                "vs Nifty"
            ),
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
    print(
        "Saved:",
        OUTPUT_CSV,
    )

    print(
        "Saved:",
        OUTPUT_JSON,
    )


def main():

    print("=" * 70)
    print(
        "NIFTY SECTOR "
        "RELATIVE STRENGTH"
    )
    print("=" * 70)

    today = date.today()

    from_date = (
        today
        - timedelta(days=250)
    )

    from_date_str = (
        from_date.isoformat()
    )

    to_date_str = (
        today.isoformat()
    )

    print(
        "Date range:"
    )

    print(
        "From:",
        from_date_str,
    )

    print(
        "To  :",
        to_date_str,
    )

    stocks = load_stocks()

    print(
        "Master rows:",
        len(stocks),
    )

    unique_stocks = (
        create_unique_stock_list(
            stocks
        )
    )

    print(
        "Unique ISINs:",
        len(unique_stocks),
    )

    instruments = (
        download_instrument_master()
    )

    instrument_mapping = (
        build_nse_equity_mapping(
            instruments
        )
    )

    save_mapping_report(
        stocks,
        instrument_mapping,
    )

    nifty_returns = (
        fetch_nifty_return(
            from_date_str,
            to_date_str,
        )
    )

    results_by_isin = {}

    errors = []

    total_unique = len(
        unique_stocks
    )

    for index, (_, stock) in enumerate(
        unique_stocks.iterrows(),
        start=1,
    ):

        symbol = str(
            stock["Symbol"]
        ).strip()

        isin = str(
            stock["ISIN Code"]
        ).strip().upper()

        print()
        print(
            f"[{index}/{total_unique}]"
        )

        try:

            result = process_stock(
                {
                    "Sector": "",
                    "Company Name": "",
                    "Industry": "",
                    "Symbol": symbol,
                    "Series": "",
                    "ISIN Code": isin,
                    "NSE Symbol": "",
                },
                from_date_str,
                to_date_str,
                nifty_returns,
                instrument_mapping,
            )

            if result.get(
                "Status"
            ) == "OK":

                results_by_isin[
                    isin
                ] = result

            else:

                errors.append(
                    {
                        "Symbol": symbol,
                        "ISIN": isin,
                        "Error": result.get(
                            "status"
                        ),
                    }
                )

        except Exception as error:

            print(
                f"  ERROR: {error}"
            )

            errors.append(
                {
                    "Symbol": symbol,
                    "ISIN": isin,
                    "Error": str(error),
                }
            )

        time.sleep(
            REQUEST_DELAY
        )

    final_results = []

    for _, row in stocks.iterrows():

        isin = str(
            row["ISIN Code"]
        ).strip().upper()

        base = {
            "Sector": row["Sector"],
            "Company Name":
                row["Company Name"],
            "Industry": row["Industry"],
            "Symbol": row["Symbol"],
            "Series": row["Series"],
            "ISIN Code": isin,
            "NSE Symbol":
                row.get(
                    "NSE Symbol",
                    "",
                ),
        }

        stock_result = (
            results_by_isin.get(
                isin
            )
        )

        if stock_result:

            result = {
                **base,
                "Daily":
                    stock_result.get(
                        "Daily"
                    ),
                "Weekly":
                    stock_result.get(
                        "Weekly"
                    ),
                "1M":
                    stock_result.get(
                        "1M"
                    ),
                "3M":
                    stock_result.get(
                        "3M"
                    ),
                "6M":
                    stock_result.get(
                        "6M"
                    ),
                "YTD":
                    stock_result.get(
                        "YTD"
                    ),
                "Nifty Index 3M % Change":
                    stock_result.get(
                        "Nifty Index 3M % Change"
                    ),
                "Stock Relative Strength vs Nifty":
                    stock_result.get(
                        "Stock Relative Strength vs Nifty"
                    ),
                "Upstox Instrument Key":
                    stock_result.get(
                        "Upstox Instrument Key"
                    ),
                "Status": "OK",
            }

        else:

            error_info = next(
                (
                    item
                    for item in errors
                    if item["ISIN"]
                    == isin
                ),
                None,
            )

            result = {
                **base,
                "Daily": None,
                "Weekly": None,
                "1M": None,
                "3M": None,
                "6M": None,
                "YTD": None,
                "Nifty Index 3M % Change":
                    clean_number(
                        nifty_returns.get(
                            "3m"
                        )
                    ),
                "Stock Relative Strength vs Nifty":
                    None,
                "Upstox Instrument Key":
                    "",
                "Status":
                    (
                        error_info["Error"]
                        if error_info
                        else "ERROR"
                    ),
            }

        final_results.append(
            result
        )

    save_results(
        final_results
    )

    successful = sum(
        1
        for item
        in final_results
        if item.get(
            "Status"
        ) == "OK"
    )

    failed = (
        len(final_results)
        - successful
    )

    print()
    print("=" * 70)
    print("COMPLETED")
    print("=" * 70)
    print(
        "Master rows     :",
        len(stocks),
    )
    print(
        "Unique ISINs    :",
        len(unique_stocks),
    )
    print(
        "Successful      :",
        successful,
    )
    print(
        "Errors          :",
        failed,
    )
    print("=" * 70)


if __name__ == "__main__":
    main()