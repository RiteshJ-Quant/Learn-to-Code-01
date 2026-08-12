import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import io
import zipfile
import importlib
from datetime import datetime, timedelta

# Page Configuration
st.set_page_config(
    page_title="Stock OHCL Data App",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .stProgress > div > div > div > div {
        background-color: #2563EB;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">📈 Stock OHLC Data </div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Fetch historical OHLC stock data individually or in batch from Yahoo Finance. Export results as single CSVs or zipped archives.</div>', unsafe_allow_html=True)

# Sidebar - Mode & Search Parameters
st.sidebar.header("⚙️ Data Fetching Mode")
app_mode = st.sidebar.radio(
    "Choose Mode",
    options=["Single Stock Mode", "Batch CSV Upload Mode", "Stock Screener Mode"],
    index=0
)


st.sidebar.markdown("---")
st.sidebar.header("📅 Date & Timeframe Settings")

# Timeframe Selection
timeframe_option = st.sidebar.selectbox(
    "Timeframe / Interval",
    options=["Daily", "Weekly", "Monthly"],
    index=0,
    help="Select data sampling frequency"
)

interval_mapping = {
    "Daily": "1d",
    "Weekly": "1wk",
    "Monthly": "1mo"
}
selected_interval = interval_mapping[timeframe_option]

# Date Range Selection
default_end = datetime.today()
default_start = default_end - timedelta(days=365)

col_date1, col_date2 = st.sidebar.columns(2)
with col_date1:
    start_date = st.date_input("Start Date", value=default_start)
with col_date2:
    end_date = st.date_input("End Date", value=default_end)

# Suffix Toggle
append_ns = st.sidebar.toggle(
    'Append ".NS" suffix to symbol names',
    value=True,
    help="Appends .NS to stock symbols for National Stock Exchange (NSE) India stocks (e.g. RELIANCE -> RELIANCE.NS)"
)

# Screener Settings in Sidebar (when Stock Screener Mode is active)
if app_mode == "Stock Screener Mode":
    st.sidebar.markdown("---")
    st.sidebar.header("🎯 Filter Combination Mode")
    filter_logic = st.sidebar.radio(
        "Combination Logic for Active Filters",
        options=["AND (Match ALL Active Filters)", "OR (Match ANY Active Filter)"],
        index=0,
        help="AND requires all enabled indicators to pass. OR requires at least one enabled indicator to pass."
    )

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ 1. Moving Average Filter")
    ma_condition = st.sidebar.selectbox(
        "MA Filter Condition",
        options=["Close > MA", "Close < MA", "Any / Ignore MA Filter"],
        index=0,
        help="Filter stocks based on Close price relative to Moving Average"
    )
    ma_type = st.sidebar.selectbox(
        "Moving Average Type",
        options=["SMA (Simple Moving Average)", "EMA (Exponential Moving Average)"],
        index=0,
        help="Select Simple or Exponential Moving Average"
    )
    ma_period = st.sidebar.number_input(
        "MA Period (Bars/Days)",
        min_value=2,
        max_value=500,
        value=50,
        step=1,
        help="Number of data points used to compute moving average (e.g., 20, 50, 200)"
    )

    st.sidebar.markdown("---")
    st.sidebar.header("📊 2. RSI Filter Settings")
    rsi_condition = st.sidebar.selectbox(
        "RSI Filter Condition",
        options=[
            "Overbought or Oversold (RSI >= High or RSI <= Low)",
            "Overbought Only (RSI >= High Threshold)",
            "Oversold Only (RSI <= Low Threshold)",
            "Normal Range Only (Low < RSI < High)",
            "Any / Ignore RSI Filter"
        ],
        index=0,
        help="Filter stocks by RSI overbought/oversold status"
    )
    rsi_period = st.sidebar.number_input(
        "RSI Period (Bars/Days)",
        min_value=2,
        max_value=100,
        value=14,
        step=1,
        help="Default standard RSI period is 14"
    )
    col_rsi1, col_rsi2 = st.sidebar.columns(2)
    with col_rsi1:
        rsi_overbought = st.number_input(
            "Overbought (≥)",
            min_value=50.0,
            max_value=100.0,
            value=70.0,
            step=1.0,
            help="Standard default overbought threshold is 70"
        )
    with col_rsi2:
        rsi_oversold = st.number_input(
            "Oversold (≤)",
            min_value=0.0,
            max_value=50.0,
            value=30.0,
            step=1.0,
            help="Standard default oversold threshold is 30"
        )

    st.sidebar.markdown("---")
    st.sidebar.header("📈 3. Supertrend Filter Settings")
    st_condition = st.sidebar.selectbox(
        "Supertrend Filter Condition",
        options=[
            "Bullish / Green (Close > Supertrend)",
            "Bearish / Red (Close < Supertrend)",
            "Any / Ignore Supertrend Filter"
        ],
        index=0,
        help="Filter stocks based on Supertrend trend signal"
    )
    st_period = st.sidebar.number_input(
        "Supertrend ATR Period",
        min_value=2,
        max_value=100,
        value=10,
        step=1,
        help="Default standard ATR period for Supertrend is 10"
    )
    st_multiplier = st.sidebar.number_input(
        "Supertrend Multiplier",
        min_value=0.5,
        max_value=10.0,
        value=3.0,
        step=0.5,
        help="Default standard multiplier for Supertrend is 3.0"
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("🧹 Clear Stock Data Cache", help="Clear cached stock price data to force re-downloading fresh data"):
        st.cache_data.clear()
        st.sidebar.success("Cache cleared!")


def format_symbol(sym: str, add_ns: bool) -> str:
    """Format symbol by trimming whitespaces and appending .NS if requested."""
    sym = str(sym).strip().upper()
    if add_ns and not sym.endswith(".NS"):
        sym = f"{sym}.NS"
    return sym

@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_stock_data(symbol: str, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
    """Fetch and cache stock OHLC history from Yahoo Finance."""
    ticker_obj = yf.Ticker(symbol)
    df = ticker_obj.history(
        start=start,
        end=end + timedelta(days=1),
        interval=interval,
        auto_adjust=False
    )
    if df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date']).dt.date
    elif 'Datetime' in df.columns:
        df['Date'] = pd.to_datetime(df['Datetime']).dt.date
        df.drop(columns=['Datetime'], inplace=True, errors='ignore')
    return df


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI) using Wilder's Smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where((avg_gain != 0) | (avg_loss != 0), 50.0)
    return rsi


def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Calculate Supertrend indicator and trend direction (1 = Bullish/Green, -1 = Bearish/Red)."""
    if len(df) < period:
        return pd.DataFrame({'Supertrend': [np.nan] * len(df), 'ST_Trend': [0] * len(df)}, index=df.index)

    high = df['High']
    low = df['Low']
    close = df['Close']

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Use min_periods=1 so ATR has no initial NaNs
    atr = tr.ewm(alpha=1/period, min_periods=1, adjust=False).mean()

    hl2 = (high + low) / 2.0
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()

    supertrend = np.zeros(len(df))
    trend = np.zeros(len(df), dtype=int)

    # Initialize first bar
    trend[0] = 1 if close.iloc[0] > final_upper.iloc[0] else -1
    supertrend[0] = final_lower.iloc[0] if trend[0] == 1 else final_upper.iloc[0]

    for i in range(1, len(df)):
        # Upper band
        if basic_upper.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i-1]

        # Lower band
        if basic_lower.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i-1]

        # Trend & Supertrend line
        if trend[i-1] == 1:
            if close.iloc[i] < final_lower.iloc[i]:
                trend[i] = -1
                supertrend[i] = final_upper.iloc[i]
            else:
                trend[i] = 1
                supertrend[i] = final_lower.iloc[i]
        else:
            if close.iloc[i] > final_upper.iloc[i]:
                trend[i] = 1
                supertrend[i] = final_lower.iloc[i]
            else:
                trend[i] = -1
                supertrend[i] = final_upper.iloc[i]

    return pd.DataFrame({'Supertrend': supertrend, 'ST_Trend': trend}, index=df.index)

# Validation helper for dates

if start_date >= end_date:
    st.error("Error: Start date must be earlier than End date.")
    st.stop()


# ==============================================================================
# MODE 1: SINGLE STOCK MODE
# ==============================================================================
if app_mode == "Single Stock Mode":
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Single Stock Input")
    
    ticker_input_raw = st.sidebar.text_input(
        "Stock Ticker Symbol",
        value="RELIANCE",
        help="Enter stock symbol e.g., RELIANCE, TCS, AAPL, MSFT"
    )
    
    ticker_symbol = format_symbol(ticker_input_raw, append_ns)
    st.sidebar.info(f"Target Symbol: **{ticker_symbol}**")

    fetch_button = st.sidebar.button("📥 Fetch Stock Data", width="stretch", type="primary")

    if ticker_input_raw:
        with st.spinner(f"Fetching {timeframe_option.lower()} data for **{ticker_symbol}**..."):
            try:
                ticker_obj = yf.Ticker(ticker_symbol)
                df = ticker_obj.history(
                    start=start_date,
                    end=end_date + timedelta(days=1),
                    interval=selected_interval,
                    auto_adjust=False
                )

                if df.empty:
                    st.warning(f"No data found for symbol '{ticker_symbol}' in range {start_date} to {end_date}. Check symbol spelling or suffix.")
                else:
                    df = df.reset_index()

                    if 'Date' in df.columns:
                        df['Date'] = pd.to_datetime(df['Date']).dt.date
                    elif 'Datetime' in df.columns:
                        df['Date'] = pd.to_datetime(df['Datetime']).dt.date
                        df.drop(columns=['Datetime'], inplace=True, errors='ignore')

                    expected_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
                    present_cols = [c for c in expected_cols if c in df.columns]
                    df = df[present_cols]

                    float_cols = ['Open', 'High', 'Low', 'Close', 'Adj Close']
                    for col in float_cols:
                        if col in df.columns:
                            df[col] = df[col].round(2)

                    st.subheader(f"📊 Market Summary for {ticker_symbol} ({timeframe_option})")
                    
                    m1, m2, m3, m4 = st.columns(4)
                    latest_row = df.iloc[-1]
                    earliest_row = df.iloc[0]

                    latest_close = float(latest_row['Close'])
                    price_change = latest_close - float(earliest_row['Close'])
                    pct_change = (price_change / float(earliest_row['Close'])) * 100 if float(earliest_row['Close']) != 0 else 0.0

                    m1.metric("Latest Close", f"{latest_close:,.2f}")
                    m2.metric("Period Change", f"{price_change:+,.2f}", f"{pct_change:+.2f}%")
                    m3.metric("Highest High", f"{df['High'].max():,.2f}")
                    m4.metric("Lowest Low", f"{df['Low'].min():,.2f}")

                    st.markdown("---")

                    tab_chart, tab_table, tab_download = st.tabs(["📉 Price Chart", "📋 Data Table", "💾 Export CSV"])

                    with tab_chart:
                        st.write("#### Historical Price Trend")
                        try:
                            go = importlib.import_module("plotly.graph_objects")

                            fig = go.Figure()
                            fig.add_trace(go.Candlestick(
                                x=df['Date'],
                                open=df['Open'],
                                high=df['High'],
                                low=df['Low'],
                                close=df['Close'],
                                name="OHLC"
                            ))
                            fig.update_layout(
                                title=f"{ticker_symbol} Candlestick Chart ({start_date} to {end_date})",
                                xaxis_title="Date",
                                yaxis_title="Price",
                                template="plotly_white",
                                xaxis_rangeslider_visible=False,
                                height=500
                            )
                            st.plotly_chart(fig, width="stretch")
                        except (ImportError, ModuleNotFoundError):
                            chart_df = df.set_index('Date')[['Close', 'Open']]
                            st.line_chart(chart_df)

                    with tab_table:
                        st.write(f"#### OHLC Data ({len(df)} records)")
                        st.dataframe(df, width="stretch")

                    with tab_download:
                        st.write("#### Download CSV File")
                        csv_data = df.to_csv(index=False)
                        file_name = f"{ticker_symbol}_{selected_interval}_{start_date}_to_{end_date}.csv"

                        st.download_button(
                            label=f"📥 Download {file_name}",
                            data=csv_data,
                            file_name=file_name,
                            mime="text/csv",
                            type="primary",
                            width="stretch"
                        )

            except Exception as e:
                st.error(f"Error fetching data for '{ticker_symbol}': {e}")

# ==============================================================================
# MODE 2: BATCH CSV UPLOAD MODE
# ==============================================================================
elif app_mode == "Batch CSV Upload Mode":
    st.subheader("📁 Batch Download Stock Data from CSV File")
    st.write("Upload a CSV file containing a list of stock symbols (e.g., `ind_niftytotalmarket_list.csv`). The app will fetch OHLC data for all symbols and package them into a downloadable **ZIP archive**.")

    uploaded_file = st.file_uploader(
        "Upload CSV File with 'symbol' column",
        type=["csv"],
        help="CSV must contain a column named 'Symbol' or similar"
    )

    if uploaded_file is not None:
        try:
            input_df = pd.read_csv(uploaded_file)
            st.success(f"Successfully loaded CSV file with **{len(input_df)} rows** and columns: `{list(input_df.columns)}`")

            # Identify Symbol column (case-insensitive search)
            symbol_col = None
            for col in input_df.columns:
                if col.strip().lower() in ['symbol', 'ticker', 'code', 'symbol name', 'stock']:
                    symbol_col = col
                    break
            
            if symbol_col is None:
                symbol_col = st.selectbox(
                    "Could not auto-detect 'symbol' column. Please select the symbol column manually:",
                    options=list(input_df.columns)
                )

            # Extract symbols
            raw_symbols = input_df[symbol_col].dropna().unique().tolist()
            formatted_symbols = [format_symbol(sym, append_ns) for sym in raw_symbols]

            st.write(f"Found **{len(formatted_symbols)} unique symbols** to process.")

            # Symbol Preview
            with st.expander("👁️ View Preview of Symbols", expanded=False):
                st.write("**Sample Formatted Symbols (First 20):**")
                st.write(formatted_symbols[:20])

            # Limit / Subset option for safety
            col_opt1, col_opt2 = st.columns(2)
            with col_opt1:
                max_symbols = st.number_input(
                    "Maximum symbols to process (set equal to total to process all)",
                    min_value=1,
                    max_value=len(formatted_symbols),
                    value=min(50, len(formatted_symbols)),
                    step=10
                )
            with col_opt2:
                st.write("")
                st.write("")
                process_batch_btn = st.button("🚀 Fetch Data & Generate ZIP File", type="primary", width="stretch")

            symbols_to_process = formatted_symbols[:max_symbols]

            if process_batch_btn:
                st.markdown("---")
                st.subheader("⏳ Processing Batch Stock Data...")

                progress_bar = st.progress(0)
                status_text = st.empty()

                zip_buffer = io.BytesIO()
                successful_symbols = []
                failed_symbols = []
                all_dataframes = []

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    total = len(symbols_to_process)

                    for idx, sym in enumerate(symbols_to_process):
                        status_text.text(f"[{idx+1}/{total}] Fetching data for: {sym}...")
                        progress_bar.progress((idx + 1) / total)

                        try:
                            ticker_obj = yf.Ticker(sym)
                            df = ticker_obj.history(
                                start=start_date,
                                end=end_date + timedelta(days=1),
                                interval=selected_interval,
                                auto_adjust=False
                            )

                            if df.empty:
                                failed_symbols.append(sym)
                                continue

                            df = df.reset_index()

                            if 'Date' in df.columns:
                                df['Date'] = pd.to_datetime(df['Date']).dt.date
                            elif 'Datetime' in df.columns:
                                df['Date'] = pd.to_datetime(df['Datetime']).dt.date
                                df.drop(columns=['Datetime'], inplace=True, errors='ignore')

                            expected_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
                            present_cols = [c for c in expected_cols if c in df.columns]
                            df = df[present_cols]

                            # Add Symbol column to dataframe for reference
                            df.insert(0, 'Symbol', sym)

                            # Save to CSV string and add to ZIP archive
                            csv_content = df.to_csv(index=False)
                            clean_filename = f"{sym.replace('/', '_')}.csv"
                            zip_file.writestr(clean_filename, csv_content)

                            successful_symbols.append(sym)
                            all_dataframes.append(df)

                        except Exception as e:
                            failed_symbols.append(sym)

                    # Add a Summary CSV into the ZIP as well
                    summary_df = pd.DataFrame({
                        "Symbol": symbols_to_process,
                        "Status": ["Success" if s in successful_symbols else "Failed/No Data" for s in symbols_to_process]
                    })
                    zip_file.writestr("_batch_download_summary.csv", summary_df.to_csv(index=False))

                zip_buffer.seek(0)
                status_text.success("🎉 Batch Processing Complete!")

                # Results Summary
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.success(f"✅ Successfully Downloaded: **{len(successful_symbols)} stocks**")
                with col_res2:
                    if failed_symbols:
                        st.warning(f"⚠️ Failed / Empty Data: **{len(failed_symbols)} stocks**")
                    else:
                        st.info("ℹ️ Failed / Empty Data: 0 stocks")

                if failed_symbols:
                    with st.expander("See Failed Symbols List"):
                        st.write(failed_symbols)

                # Download ZIP Button
                zip_filename = f"stock_data_batch_{selected_interval}_{start_date}_to_{end_date}.zip"
                st.download_button(
                    label=f"💾 Download Zipped Stock Data ({zip_filename})",
                    data=zip_buffer.getvalue(),
                    file_name=zip_filename,
                    mime="application/zip",
                    type="primary",
                    width="stretch"
                )

        except Exception as e:
            st.error(f"Error reading CSV file: {e}")

# ==============================================================================
# MODE 3: STOCK SCREENER MODE
# ==============================================================================
else:
    st.subheader("🔍 Stock Screener - Multi-Indicator (MA, RSI, Supertrend)")
    st.write(
        "Upload a CSV file containing a list of stock symbols. Configure Moving Average, RSI, and Supertrend parameters in the sidebar. "
        "Filter stocks independently or combine active filters using **AND** (match all) / **OR** (match any) logic."
    )

    uploaded_file = st.file_uploader(
        "Upload CSV File with 'symbol' column for Screening",
        type=["csv"],
        help="CSV must contain a column named 'Symbol' or similar",
        key="screener_csv"
    )

    if uploaded_file is not None:
        try:
            input_df = pd.read_csv(uploaded_file)
            st.success(f"Successfully loaded CSV file with **{len(input_df)} rows** and columns: `{list(input_df.columns)}`")

            # Identify Symbol column (case-insensitive search)
            symbol_col = None
            for col in input_df.columns:
                if col.strip().lower() in ['symbol', 'ticker', 'code', 'symbol name', 'stock']:
                    symbol_col = col
                    break

            if symbol_col is None:
                symbol_col = st.selectbox(
                    "Could not auto-detect 'symbol' column. Please select the symbol column manually:",
                    options=list(input_df.columns),
                    key="screener_sym_col"
                )

            # Extract symbols
            raw_symbols = input_df[symbol_col].dropna().unique().tolist()
            formatted_symbols = [format_symbol(sym, append_ns) for sym in raw_symbols]

            st.write(f"Found **{len(formatted_symbols)} unique symbols** to screen.")

            # Batch Limit & Action Button
            st.markdown("---")
            col_scr1, col_scr2 = st.columns([1, 2])
            with col_scr1:
                max_symbols = st.number_input(
                    "Maximum Symbols to Screen",
                    min_value=1,
                    max_value=len(formatted_symbols),
                    value=min(50, len(formatted_symbols)),
                    step=10,
                    help="Limit maximum symbols to avoid long processing times",
                    key="screener_max_sym"
                )
            with col_scr2:
                st.write("")
                st.write("")
                run_screener_btn = st.button("🚀 Run Multi-Indicator Screener", type="primary", width="stretch")

            symbols_to_process = formatted_symbols[:max_symbols]
            ma_type_code = "SMA" if "SMA" in ma_type else "EMA"

            if run_screener_btn:
                st.subheader(f"⏳ Screening {len(symbols_to_process)} stocks (Logic: {'ALL' if 'AND' in filter_logic else 'ANY'} active filters)...")

                progress_bar = st.progress(0)
                status_text = st.empty()

                passed_stocks = []
                failed_stocks = []
                error_stocks = []

                total = len(symbols_to_process)
                min_bars_needed = max(int(ma_period), int(rsi_period), int(st_period)) + 2

                for idx, sym in enumerate(symbols_to_process):
                    status_text.text(f"[{idx+1}/{total}] Processing symbol: {sym}...")
                    progress_bar.progress((idx + 1) / total)

                    try:
                        df = get_cached_stock_data(sym, start_date, end_date, selected_interval)

                        if df.empty or len(df) < min_bars_needed:
                            error_stocks.append({"Symbol": sym, "Reason": f"Insufficient data (less than {min_bars_needed} bars)" if not df.empty else "No data returned"})
                            continue

                        df = df.copy()

                        # Calculate Moving Average
                        if ma_type_code == "SMA":
                            df['MA'] = df['Close'].rolling(window=int(ma_period)).mean()
                        else:
                            df['MA'] = df['Close'].ewm(span=int(ma_period), adjust=False).mean()

                        # Calculate RSI
                        df['RSI'] = calculate_rsi(df['Close'], period=int(rsi_period))

                        # Calculate Supertrend
                        st_df = calculate_supertrend(df, period=int(st_period), multiplier=float(st_multiplier))
                        df['Supertrend'] = st_df['Supertrend']
                        df['ST_Trend'] = st_df['ST_Trend']

                        valid_df = df.dropna(subset=['Close', 'MA', 'RSI', 'Supertrend'])
                        if valid_df.empty:
                            error_stocks.append({"Symbol": sym, "Reason": "Unable to compute indicators"})
                            continue

                        latest_row = valid_df.iloc[-1]
                        latest_close = float(latest_row['Close'])
                        latest_ma = float(latest_row['MA'])
                        latest_rsi = float(latest_row['RSI'])
                        latest_st = float(latest_row['Supertrend'])
                        latest_st_trend = int(latest_row['ST_Trend'])
                        latest_date = latest_row['Date']

                        diff = latest_close - latest_ma
                        pct_above = (diff / latest_ma) * 100 if latest_ma != 0 else 0.0

                        # Indicator Status determinations
                        if latest_rsi >= rsi_overbought:
                            rsi_status = "🔴 Overbought"
                        elif latest_rsi <= rsi_oversold:
                            rsi_status = "🟢 Oversold"
                        else:
                            rsi_status = "⚪ Normal"

                        if latest_st_trend == 1:
                            st_status = "🟢 Bullish / Green"
                        else:
                            st_status = "🔴 Bearish / Red"

                        # Active evaluations collection
                        active_evaluations = []

                        # 1. MA Evaluation
                        if ma_condition == "Close > MA":
                            active_evaluations.append(latest_close > latest_ma)
                        elif ma_condition == "Close < MA":
                            active_evaluations.append(latest_close < latest_ma)

                        # 2. RSI Evaluation
                        if rsi_condition == "Overbought or Oversold (RSI >= High or RSI <= Low)":
                            active_evaluations.append((latest_rsi >= rsi_overbought) or (latest_rsi <= rsi_oversold))
                        elif rsi_condition == "Overbought Only (RSI >= High Threshold)":
                            active_evaluations.append(latest_rsi >= rsi_overbought)
                        elif rsi_condition == "Oversold Only (RSI <= Low Threshold)":
                            active_evaluations.append(latest_rsi <= rsi_oversold)
                        elif rsi_condition == "Normal Range Only (Low < RSI < High)":
                            active_evaluations.append(rsi_oversold < latest_rsi < rsi_overbought)

                        # 3. Supertrend Evaluation
                        if st_condition == "Bullish / Green (Close > Supertrend)":
                            active_evaluations.append(latest_st_trend == 1)
                        elif st_condition == "Bearish / Red (Close < Supertrend)":
                            active_evaluations.append(latest_st_trend == -1)

                        # Filter combination logic
                        if not active_evaluations:
                            passed = True
                        elif "AND" in filter_logic:
                            passed = all(active_evaluations)
                        else:
                            passed = any(active_evaluations)

                        record = {
                            "Symbol": sym,
                            "Latest Date": latest_date,
                            "Latest Close": round(latest_close, 2),
                            f"MA ({ma_type_code} {ma_period})": round(latest_ma, 2),
                            f"RSI ({rsi_period})": round(latest_rsi, 2),
                            "RSI Status": rsi_status,
                            f"Supertrend ({st_period}, {st_multiplier})": round(latest_st, 2),
                            "Supertrend Signal": st_status,
                            "Diff Above MA": round(diff, 2),
                            "% Above MA": round(pct_above, 2)
                        }

                        if passed:
                            passed_stocks.append(record)
                        else:
                            failed_stocks.append(record)

                    except Exception as e:
                        error_stocks.append({"Symbol": sym, "Reason": str(e)})

                progress_bar.progress(1.0)
                status_text.success("🎉 Screening Complete!")

                # Store screener results in session state for interactive persistent view
                st.session_state['screener_results'] = {
                    'passed': passed_stocks,
                    'failed': failed_stocks,
                    'errors': error_stocks,
                    'ma_type': ma_type_code,
                    'ma_period': ma_period,
                    'rsi_period': rsi_period,
                    'rsi_overbought': rsi_overbought,
                    'rsi_oversold': rsi_oversold,
                    'st_period': st_period,
                    'st_multiplier': st_multiplier,
                    'ma_condition': ma_condition,
                    'rsi_condition': rsi_condition,
                    'st_condition': st_condition,
                    'filter_logic': filter_logic
                }

            # Display Screened Results if available in session state
            if 'screener_results' in st.session_state:
                res = st.session_state['screener_results']
                passed = res['passed']
                failed = res['failed']
                errors = res['errors']
                p_ma_type = res['ma_type']
                p_ma_period = res['ma_period']
                p_rsi_period = res.get('rsi_period', 14)
                p_rsi_overbought = res.get('rsi_overbought', 70.0)
                p_rsi_oversold = res.get('rsi_oversold', 30.0)
                p_st_period = res.get('st_period', 10)
                p_st_multiplier = res.get('st_multiplier', 3.0)
                p_filter_logic = res.get('filter_logic', 'AND')

                st.markdown("---")
                st.subheader(f"📊 Screener Output Summary (Logic: {'ALL' if 'AND' in p_filter_logic else 'ANY'})")

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Screened", f"{len(passed) + len(failed) + len(errors)}")
                m2.metric("Stocks Passed Filter", f"{len(passed)}", delta=f"{len(passed)} stocks", delta_color="normal")
                m3.metric("Stocks Did Not Match", f"{len(failed)}")
                m4.metric("Errors / Missing Data", f"{len(errors)}")

                if passed:
                    st.success(f"✅ Found **{len(passed)} stocks** matching your active filter criteria!")

                    passed_df = pd.DataFrame(passed)
                    # Sort options
                    col_sort1, col_sort2 = st.columns([1, 2])
                    with col_sort1:
                        sort_by_col = st.selectbox(
                            "Sort Results By:",
                            options=["Symbol", f"RSI ({p_rsi_period})", "% Above MA", "Latest Close"],
                            index=0
                        )

                    ascending = True if sort_by_col == "Symbol" else False
                    passed_df = passed_df.sort_values(by=sort_by_col, ascending=ascending)

                    st.write(f"### 📋 Filtered Stocks Table ({len(passed_df)} stocks)")
                    st.dataframe(passed_df, width="stretch")

                    col_dl, _ = st.columns([1, 1])
                    with col_dl:
                        csv_data = passed_df.to_csv(index=False)
                        st.download_button(
                            label=f"💾 Download Screened Stocks CSV ({len(passed)} stocks)",
                            data=csv_data,
                            file_name=f"screener_results_{datetime.today().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            type="primary",
                            width="stretch"
                        )

                    # Interactive Chart Visualizer for Screened Stocks
                    st.markdown("---")
                    st.subheader("📉 Visualizer with Price, MA, Supertrend & RSI")
                    selected_chart_sym = st.selectbox(
                        "Select a passed stock to view interactive multi-indicator chart:",
                        options=passed_df["Symbol"].tolist()
                    )

                    if selected_chart_sym:
                        with st.spinner(f"Loading chart for {selected_chart_sym}..."):
                            try:
                                chart_data = get_cached_stock_data(selected_chart_sym, start_date, end_date, selected_interval).copy()

                                if p_ma_type == "SMA":
                                    chart_data['MA'] = chart_data['Close'].rolling(window=int(p_ma_period)).mean()
                                else:
                                    chart_data['MA'] = chart_data['Close'].ewm(span=int(p_ma_period), adjust=False).mean()

                                chart_data['RSI'] = calculate_rsi(chart_data['Close'], period=int(p_rsi_period))

                                st_chart = calculate_supertrend(chart_data, period=int(p_st_period), multiplier=float(p_st_multiplier))
                                chart_data['Supertrend'] = st_chart['Supertrend']
                                chart_data['ST_Trend'] = st_chart['ST_Trend']
                                chart_data['ST_Bull'] = chart_data['Supertrend'].where(chart_data['ST_Trend'] == 1, np.nan)
                                chart_data['ST_Bear'] = chart_data['Supertrend'].where(chart_data['ST_Trend'] == -1, np.nan)

                                try:
                                    go = importlib.import_module("plotly.graph_objects")
                                    make_subplots = importlib.import_module("plotly.subplots").make_subplots

                                    fig = make_subplots(
                                        rows=2, cols=1,
                                        shared_xaxes=True,
                                        row_heights=[0.7, 0.3],
                                        vertical_spacing=0.06,
                                        subplot_titles=(
                                            f"{selected_chart_sym} Price, {p_ma_type} ({p_ma_period}) & Supertrend ({p_st_period}, {p_st_multiplier})",
                                            f"RSI ({p_rsi_period}) Indicator"
                                        )
                                    )

                                    # Candlestick chart
                                    fig.add_trace(go.Candlestick(
                                        x=chart_data['Date'],
                                        open=chart_data['Open'],
                                        high=chart_data['High'],
                                        low=chart_data['Low'],
                                        close=chart_data['Close'],
                                        name="OHLC"
                                    ), row=1, col=1)

                                    # MA Line
                                    fig.add_trace(go.Scatter(
                                        x=chart_data['Date'],
                                        y=chart_data['MA'],
                                        mode='lines',
                                        name=f"{p_ma_type} {p_ma_period}",
                                        line=dict(color='orange', width=2)
                                    ), row=1, col=1)

                                    # Supertrend Bullish Line
                                    fig.add_trace(go.Scatter(
                                        x=chart_data['Date'],
                                        y=chart_data['ST_Bull'],
                                        mode='lines',
                                        name="Supertrend (Bullish)",
                                        line=dict(color='green', width=2)
                                    ), row=1, col=1)

                                    # Supertrend Bearish Line
                                    fig.add_trace(go.Scatter(
                                        x=chart_data['Date'],
                                        y=chart_data['ST_Bear'],
                                        mode='lines',
                                        name="Supertrend (Bearish)",
                                        line=dict(color='red', width=2)
                                    ), row=1, col=1)

                                    # RSI Line
                                    fig.add_trace(go.Scatter(
                                        x=chart_data['Date'],
                                        y=chart_data['RSI'],
                                        mode='lines',
                                        name=f"RSI {p_rsi_period}",
                                        line=dict(color='purple', width=2)
                                    ), row=2, col=1)

                                    # RSI Threshold Lines
                                    fig.add_hline(y=p_rsi_overbought, line_dash="dash", line_color="red", annotation_text="Overbought", row=2, col=1)
                                    fig.add_hline(y=p_rsi_oversold, line_dash="dash", line_color="green", annotation_text="Oversold", row=2, col=1)

                                    fig.update_layout(
                                        template="plotly_white",
                                        xaxis_rangeslider_visible=False,
                                        height=700,
                                        margin=dict(l=40, r=40, t=60, b=40)
                                    )
                                    fig.update_yaxes(title_text="Price", row=1, col=1)
                                    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)

                                    st.plotly_chart(fig, width="stretch")

                                except (ImportError, ModuleNotFoundError, AttributeError):
                                    st.info("💡 Displaying native Streamlit charts for Price, Supertrend & RSI.")
                                    chart_df = chart_data.set_index('Date')[['Close', 'MA', 'Supertrend']].copy()
                                    chart_df.rename(columns={'MA': f"{p_ma_type} {p_ma_period}"}, inplace=True)
                                    st.line_chart(chart_df)

                                    rsi_chart_df = chart_data.set_index('Date')[['RSI']].copy()
                                    st.line_chart(rsi_chart_df)

                            except Exception as chart_err:
                                st.error(f"Error plotting chart for {selected_chart_sym}: {chart_err}")
                else:
                    st.warning("No stocks found matching the selected filter criteria.")

                if errors:
                    with st.expander("See Skipped / Error Symbols"):
                        st.dataframe(pd.DataFrame(errors))

        except Exception as e:
            st.error(f"Error reading CSV file: {e}")
