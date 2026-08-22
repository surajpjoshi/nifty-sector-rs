import os
import json
import time
import gzip
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests


ACCESS_TOKEN = os.environ["UPSTOX_ANALYTICS_TOKEN"]

BASE_URL = "https://api.upstox.com/v3/historical-candle"
LTP_URL = "https://api.upstox.com/v3/market-quote/ltp"
IST = ZoneInfo("Asia/Kolkata")

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


def fetch_ltp_quotes(instrument_mapping):
    """
    Fetch live LTP / previous close for mapped NSE equity instruments.

    Important:
    The response can contain more quote objects than our requested
    equity universe. We therefore only accept quotes whose instrument
    key was explicitly requested and keep exactly one quote per ISIN.
    """
    quotes = {}

    instrument_items = []

    for isin, mapped in instrument_mapping.items():
        instrument_key = str(
            mapped.get("instrument_key", "")
        ).strip()

        if instrument_key:
            instrument_items.append(
                (
                    str(isin).strip().upper(),
                    instrument_key,
                )
            )

    # Keep one requested instrument per ISIN.
    unique_items = {}
    for isin, instrument_key in instrument_items:
        unique_items[isin] = instrument_key

    instrument_items = list(
        unique_items.items()
    )

    # Upstox supports up to 500 instruments per request.
    batch_size = 500

    print()
    print("=" * 70)
    print("FETCHING LIVE LTP")
    print("=" * 70)
    print(
        "Requested instruments:",
        len(instrument_items),
    )

    fetched_at = datetime.now(
        IST
    ).isoformat(
        timespec="seconds"
    )

    for start in range(
        0,
        len(instrument_items),
        batch_size,
    ):

        batch = instrument_items[
            start:start + batch_size
        ]

        requested_keys = {
            instrument_key
            for _, instrument_key in batch
        }

        print(
            f"LTP batch "
            f"{start + 1}-"
            f"{start + len(batch)}"
        )

        try:

            response = requests.get(
                LTP_URL,
                headers=get_headers(),
                params={
                    "instrument_key": ",".join(
                        requested_keys
                    )
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:

                print(
                    "  LTP API error:",
                    response.status_code,
                    response.text[:500],
                )

                continue

            data = response.json().get(
                "data",
                {}
            )

            # Build an exact normalized instrument-key lookup.
            requested_lookup = {}

            for isin, instrument_key in batch:

                normalized_key = (
                    instrument_key
                    .strip()
                    .replace(":", "|")
                )

                requested_lookup[
                    normalized_key
                ] = isin

            batch_quotes = 0

            for response_key, quote in data.items():

                response_key = str(
                    response_key
                ).strip()

                instrument_token = str(
                    quote.get(
                        "instrument_token",
                        response_key,
                    )
                ).strip()

                # Prefer the actual instrument_token returned
                # by Upstox, then fall back to the response key.
                candidates = [
                    instrument_token,
                    response_key,
                    instrument_token.replace(
                        ":",
                        "|",
                    ),
                    response_key.replace(
                        ":",
                        "|",
                    ),
                ]

                isin = None

                for candidate in candidates:

                    normalized = candidate.replace(
                        ":",
                        "|",
                    )

                    if normalized in requested_lookup:

                        isin = requested_lookup[
                            normalized
                        ]

                        break

                # CRITICAL:
                # Ignore any quote not belonging to the requested
                # 500-instrument batch.
                if not isin:
                    continue

                # Never allow duplicate quote records for an ISIN.
                if isin in quotes:
                    continue

                last_price = quote.get(
                    "last_price"
                )

                previous_close = quote.get(
                    "cp"
                )

                change_pct = None

                if (
                    last_price is not None
                    and previous_close is not None
                ):

                    try:

                        previous_close_float = float(
                            previous_close
                        )

                        if (
                            previous_close_float
                            != 0
                        ):

                            change_pct = (
                                (
                                    float(
                                        last_price
                                    )
                                    /
                                    previous_close_float
                                ) - 1
                            ) * 100

                    except (
                        TypeError,
                        ValueError,
                    ):
                        change_pct = None

                quotes[isin] = {

                    "LTP":
                        clean_number(
                            last_price
                        ),

                    "Previous Close":
                        clean_number(
                            previous_close
                        ),

                    "LTP Change %":
                        clean_number(
                            change_pct
                        ),

                    "LTP Volume":
                        quote.get(
                            "volume"
                        ),

                    "LTP Last Traded Qty":
                        quote.get(
                            "ltq"
                        ),

                    "LTP Fetch Time":
                        fetched_at,
                }

                batch_quotes += 1

            print(
                "  Quotes matched:",
                batch_quotes,
            )

        except Exception as error:

            print(
                "  LTP batch ERROR:",
                error,
            )

        time.sleep(
            REQUEST_DELAY
        )

    print()
    print(
        "LTP quotes received:",
        len(quotes),
    )

    print(
        "LTP instruments missing:",
        max(
            0,
            len(instrument_items)
            - len(quotes),
        ),
    )

    print("=" * 70)

    return quotes, fetched_at


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


def calculate_rs_history(
    stock_df,
    nifty_df,
    days=10,
):
    """
    Calculate daily 3M Relative Strength for the
    last `days` actual market trading sessions.

    RS = Stock 3M return - Nifty 3M return

    Only actual dates returned by the NSE/Upstox daily
    candle data are used. Weekends and market holidays
    therefore never appear in the history.
    """

    if stock_df.empty or nifty_df.empty:
        return []

    stock = stock_df.copy()
    nifty = nifty_df.copy()

    stock["date"] = pd.to_datetime(stock["date"])
    nifty["date"] = pd.to_datetime(nifty["date"])

    stock = (
        stock
        .sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    nifty = (
        nifty
        .sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # Align stock and NIFTY on actual common trading sessions.
    # ---------------------------------------------------------

    merged = pd.merge(
        stock[
            [
                "date",
                "close",
                "volume",
            ]
        ],
        nifty[
            [
                "date",
                "close",
            ]
        ],
        on="date",
        how="inner",
        suffixes=(
            "_stock",
            "_nifty",
        ),
    )

    if merged.empty:
        return []

    merged = (
        merged
        .sort_values("date")
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # 3 MONTH = approximately 63 trading sessions.
    #
    # We need the historical candle before the 3M window
    # in order to calculate the return for EACH date.
    # ---------------------------------------------------------

    LOOKBACK_SESSIONS = 63

    if len(merged) <= LOOKBACK_SESSIONS:
        return []

    merged["stock_base"] = (
        merged["close_stock"]
        .shift(LOOKBACK_SESSIONS)
    )

    merged["nifty_base"] = (
        merged["close_nifty"]
        .shift(LOOKBACK_SESSIONS)
    )

    # Stock 3M return
    merged["stock_3m_return"] = (
        (
            merged["close_stock"]
            / merged["stock_base"]
        ) - 1
    ) * 100

    # NIFTY 3M return
    merged["nifty_3m_return"] = (
        (
            merged["close_nifty"]
            / merged["nifty_base"]
        ) - 1
    ) * 100

    # Relative Strength
    merged["rs"] = (
        merged["stock_3m_return"]
        - merged["nifty_3m_return"]
    )

    # ---------------------------------------------------------
    # Keep only rows where the complete 3M calculation exists.
    # ---------------------------------------------------------

    valid = merged[
        merged["stock_base"].notna()
        & merged["nifty_base"].notna()
        & merged["rs"].notna()
    ].copy()

    if valid.empty:
        return []

    # ---------------------------------------------------------
    # IMPORTANT:
    #
    # tail(days) means LAST ACTUAL TRADING SESSIONS.
    #
    # No calendar-day calculation is used here.
    # ---------------------------------------------------------

    recent = valid.tail(days).copy()

    history = []

    for _, item in recent.iterrows():

        volume = item["volume"]

        history.append(
            {
                "date": item["date"].strftime(
                    "%Y-%m-%d"
                ),

                "rs": clean_number(
                    item["rs"]
                ),

                "volume": (
                    int(volume)
                    if (
                        pd.notna(volume)
                        and float(volume) >= 0
                    )
                    else None
                ),
            }
        )

    return history

def calculate_rs_momentum_metrics(
    rs_history,
):
    """
    Calculate RS momentum statistics from the
    last 10 available RS observations.
    """

    valid = [
        item
        for item in rs_history
        if item.get("rs") is not None
    ]

    if not valid:
        return {
            "10D RS Change": None,
            "Highest RS": None,
            "Lowest RS": None,
            "Average RS": None,
            "RS Momentum Score": None,
            "Consistency": None,
            "RS Data Days": 0,
        }

    rs_values = [
        float(item["rs"])
        for item in valid
    ]

    current_rs = rs_values[-1]

    if len(rs_values) >= 2:

        first_rs = rs_values[0]

        rs_change = (
            current_rs - first_rs
        )

        previous_values = rs_values[:-1]

        previous_average = (
            sum(previous_values)
            / len(previous_values)
        )

        momentum_score = (
            current_rs
            - previous_average
        )

    else:

        rs_change = None
        momentum_score = None

    # Count sessions where RS increased
    positive_days = 0

    for i in range(1, len(rs_values)):

        if rs_values[i] > rs_values[i - 1]:
            positive_days += 1

    consistency = (
        positive_days
        if len(rs_values) <= 1
        else positive_days
    )

    return {
        "10D RS Change": clean_number(
            rs_change
        ),

        "Highest RS": clean_number(
            max(rs_values)
        ),

        "Lowest RS": clean_number(
            min(rs_values)
        ),

        "Average RS": clean_number(
            sum(rs_values)
            / len(rs_values)
        ),

        "RS Momentum Score": clean_number(
            momentum_score
        ),

        "Consistency": consistency,

        "RS Data Days": len(rs_values),
    }


def calculate_volume_metrics(
    rs_history,
):
    """
    Calculate volume statistics using the last 10
    available trading sessions.

    Volume Ratio compares the latest session against
    the average of the preceding sessions.
    """

    valid = [
        item
        for item in rs_history
        if item.get("volume") is not None
    ]

    if not valid:
        return {
            "Today Volume": None,
            "10D Average Volume": None,
            "Volume Ratio": None,
            "Volume Change %": None,
        }

    volumes = [
        float(item["volume"])
        for item in valid
    ]

    today_volume = volumes[-1]

    previous_volumes = volumes[:-1]

    if previous_volumes:

        average_volume = (
            sum(previous_volumes)
            / len(previous_volumes)
        )

    else:

        average_volume = None

    if (
        average_volume is not None
        and average_volume > 0
    ):

        volume_ratio = (
            today_volume
            / average_volume
        )

        volume_change = (
            volume_ratio - 1
        ) * 100

    else:

        volume_ratio = None
        volume_change = None

    return {
        "Today Volume": int(
            today_volume
        ),

        "10D Average Volume": (
            clean_number(
                average_volume
            )
            if average_volume is not None
            else None
        ),

        "Volume Ratio": clean_number(
            volume_ratio
        ),

        "Volume Change %": clean_number(
            volume_change
        ),
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

    return nifty_returns, nifty_df


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
    nifty_df,
    instrument_mapping,
    ltp_quotes,
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

    # ---------------------------------------------------------
    # 10-DAY RS HISTORY + VOLUME HISTORY
    # ---------------------------------------------------------

    rs_history = calculate_rs_history(
        df,
        nifty_df,
        days=10,
    )

    rs_metrics = calculate_rs_momentum_metrics(
        rs_history
    )

    volume_metrics = calculate_volume_metrics(
        rs_history
    )

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

        "RS History":
            rs_history,

        "10D RS Change":
            rs_metrics[
                "10D RS Change"
            ],

        "Highest RS":
            rs_metrics[
                "Highest RS"
            ],

        "Lowest RS":
            rs_metrics[
                "Lowest RS"
            ],

        "Average RS":
            rs_metrics[
                "Average RS"
            ],

        "RS Momentum Score":
            rs_metrics[
                "RS Momentum Score"
            ],

        "Consistency":
            rs_metrics[
                "Consistency"
            ],

        "RS Data Days":
            rs_metrics[
                "RS Data Days"
            ],

        "Volume History":
            rs_history,

        "Today Volume":
            volume_metrics[
                "Today Volume"
            ],

        "10D Average Volume":
            volume_metrics[
                "10D Average Volume"
            ],

        "Volume Ratio":
            volume_metrics[
                "Volume Ratio"
            ],

        "Volume Change %":
            volume_metrics[
                "Volume Change %"
            ],

        "Upstox Instrument Key":
            instrument_key,

        "Data Date": (
            str(df.iloc[-1]["date"])
            if not df.empty
            else ""
        ),

        "LTP": (
            ltp_quotes.get(isin, {}).get("LTP")
        ),

        "Previous Close": (
            ltp_quotes.get(isin, {}).get(
                "Previous Close"
            )
        ),

        "LTP Change %": (
            ltp_quotes.get(isin, {}).get(
                "LTP Change %"
            )
        ),

        "LTP Volume": (
            ltp_quotes.get(isin, {}).get(
                "LTP Volume"
            )
        ),

        "LTP Last Traded Qty": (
            ltp_quotes.get(isin, {}).get(
                "LTP Last Traded Qty"
            )
        ),

        "LTP Fetch Time": (
            ltp_quotes.get(isin, {}).get(
                "LTP Fetch Time"
            )
        ),

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

    now_ist = datetime.now(IST)
    today = now_ist.date()

    print(
        "Workflow fetch time (IST):",
        now_ist.isoformat(timespec="seconds"),
    )

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

    # Only fetch LTP for instruments that actually exist
    # in our master stock list.
    # Restrict live LTP requests to the 536 ISINs in our stock master.
    # instrument_mapping contains the full NSE universe (~2872 instruments).
    master_isins = set(
        unique_stocks["ISIN Code"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    ltp_instrument_mapping = {
        isin: instrument_mapping[isin]
        for isin in master_isins
        if isin in instrument_mapping
    }

    print(
        "LTP instrument universe:",
        len(ltp_instrument_mapping)
    )

    ltp_quotes, ltp_fetch_time = fetch_ltp_quotes(
        ltp_instrument_mapping
    )

    # Safety check: LTP data must never exceed the unique
    # instrument universe we requested.
    if len(ltp_quotes) > len(ltp_instrument_mapping):
        raise RuntimeError(
            "LTP mapping error: received more unique "
            "quotes than unique ISINs. "
            f"ISINs={len(ltp_instrument_mapping)}, "
            f"LTP quotes={len(ltp_quotes)}"
        )

    nifty_returns, nifty_df = (
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
                nifty_df,
                instrument_mapping,
                ltp_quotes,
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

    # Common dashboard metadata. LTP fetch time is the exact time the
    # live quote request completed in India Standard Time.
    dashboard_metadata = {
        "Last Fetch": ltp_fetch_time,
    }

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

            "Last Fetch":
                dashboard_metadata["Last Fetch"],
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
                "RS History":
                    stock_result.get(
                        "RS History"
                    ),
                "10D RS Change":
                    stock_result.get(
                        "10D RS Change"
                    ),
                "Highest RS":
                    stock_result.get(
                        "Highest RS"
                    ),
                "Lowest RS":
                    stock_result.get(
                        "Lowest RS"
                    ),
                "Average RS":
                    stock_result.get(
                        "Average RS"
                    ),
                "RS Momentum Score":
                    stock_result.get(
                        "RS Momentum Score"
                    ),
                "Consistency":
                    stock_result.get(
                        "Consistency"
                    ),
                "RS Data Days":
                    stock_result.get(
                        "RS Data Days"
                    ),
                "Volume History":
                    stock_result.get(
                        "Volume History"
                    ),
                "Today Volume":
                    stock_result.get(
                        "Today Volume"
                    ),
                "10D Average Volume":
                    stock_result.get(
                        "10D Average Volume"
                    ),
                "Volume Ratio":
                    stock_result.get(
                        "Volume Ratio"
                    ),
                "Volume Change %":
                    stock_result.get(
                        "Volume Change %"
                    ),
                "Upstox Instrument Key":
                    stock_result.get(
                        "Upstox Instrument Key"
                    ),

                "Data Date":
                    stock_result.get(
                        "Data Date"
                    ),

                "LTP":
                    stock_result.get(
                        "LTP"
                    ),

                "Previous Close":
                    stock_result.get(
                        "Previous Close"
                    ),

                "LTP Change %":
                    stock_result.get(
                        "LTP Change %"
                    ),

                "LTP Volume":
                    stock_result.get(
                        "LTP Volume"
                    ),

                "LTP Last Traded Qty":
                    stock_result.get(
                        "LTP Last Traded Qty"
                    ),

                "LTP Fetch Time":
                    stock_result.get(
                        "LTP Fetch Time"
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
                "RS History": None,
                "10D RS Change": None,
                "Highest RS": None,
                "Lowest RS": None,
                "Average RS": None,
                "RS Momentum Score": None,
                "Consistency": None,
                "RS Data Days": None,
                "Volume History": None,
                "Today Volume": None,
                "10D Average Volume": None,
                "Volume Ratio": None,
                "Volume Change %": None,
                "Upstox Instrument Key":
                    "",

                "Data Date":
                    "",

                "LTP":
                    None,

                "Previous Close":
                    None,

                "LTP Change %":
                    None,

                "LTP Volume":
                    None,

                "LTP Last Traded Qty":
                    None,

                "LTP Fetch Time":
                    ltp_fetch_time,

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
    print(
        "LTP Quotes      :",
        len(ltp_quotes),
    )
    print(
        "Last Fetch (IST):",
        ltp_fetch_time,
    )
    print("=" * 70)


if __name__ == "__main__":
    main()