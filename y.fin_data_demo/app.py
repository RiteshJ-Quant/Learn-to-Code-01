import streamlit as st
import yfinance as yf
import pandas as pd
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

# Screener MA Settings in Sidebar (when Stock Screener Mode is active)
if app_mode == "Stock Screener Mode":
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Moving Average Settings")
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

def format_symbol(sym: str, add_ns: bool) -> str:
    """Format symbol by trimming whitespaces and appending .NS if requested."""
    sym = str(sym).strip().upper()
    if add_ns and not sym.endswith(".NS"):
        sym = f"{sym}.NS"
    return sym

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
    st.subheader("🔍 Stock Screener - Moving Average Filter")
    st.write(
        "Upload a CSV file containing a list of stock symbols. Set your Moving Average parameters (SMA/EMA & period). "
        "The app will fetch price history and output all stocks whose latest close price is **above** their Moving Average."
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
                run_screener_btn = st.button("🚀 Run Moving Average Screener", type="primary", width="stretch")

            symbols_to_process = formatted_symbols[:max_symbols]
            ma_type_code = "SMA" if "SMA" in ma_type else "EMA"


            if run_screener_btn:
                st.subheader(f"⏳ Screening {len(symbols_to_process)} stocks for Close > {ma_period} {ma_type_code}...")

                progress_bar = st.progress(0)
                status_text = st.empty()

                passed_stocks = []
                failed_stocks = []
                error_stocks = []

                total = len(symbols_to_process)

                for idx, sym in enumerate(symbols_to_process):
                    status_text.text(f"[{idx+1}/{total}] Processing symbol: {sym}...")
                    progress_bar.progress((idx + 1) / total)

                    try:
                        ticker_obj = yf.Ticker(sym)
                        df = ticker_obj.history(
                            start=start_date,
                            end=end_date + timedelta(days=1),
                            interval=selected_interval,
                            auto_adjust=False
                        )

                        if df.empty or len(df) < ma_period:
                            error_stocks.append({"Symbol": sym, "Reason": f"Insufficient data (less than {ma_period} bars)" if not df.empty else "No data returned"})
                            continue

                        df = df.reset_index()

                        if 'Date' in df.columns:
                            df['Date'] = pd.to_datetime(df['Date']).dt.date
                        elif 'Datetime' in df.columns:
                            df['Date'] = pd.to_datetime(df['Datetime']).dt.date
                            df.drop(columns=['Datetime'], inplace=True, errors='ignore')

                        # Calculate Moving Average
                        if ma_type_code == "SMA":
                            df['MA'] = df['Close'].rolling(window=int(ma_period)).mean()
                        else:
                            df['MA'] = df['Close'].ewm(span=int(ma_period), adjust=False).mean()

                        valid_df = df.dropna(subset=['Close', 'MA'])
                        if valid_df.empty:
                            error_stocks.append({"Symbol": sym, "Reason": "Unable to compute Moving Average"})
                            continue

                        latest_row = valid_df.iloc[-1]
                        latest_close = float(latest_row['Close'])
                        latest_ma = float(latest_row['MA'])
                        latest_date = latest_row['Date']

                        diff = latest_close - latest_ma
                        pct_above = (diff / latest_ma) * 100 if latest_ma != 0 else 0.0

                        record = {
                            "Symbol": sym,
                            "Latest Date": latest_date,
                            "Latest Close": round(latest_close, 2),
                            f"MA ({ma_type_code} {ma_period})": round(latest_ma, 2),
                            "Diff Above MA": round(diff, 2),
                            "% Above MA": round(pct_above, 2)
                        }

                        if latest_close > latest_ma:
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
                    'ma_period': ma_period
                }

            # Display Screened Results if available in session state
            if 'screener_results' in st.session_state:
                res = st.session_state['screener_results']
                passed = res['passed']
                failed = res['failed']
                errors = res['errors']
                p_ma_type = res['ma_type']
                p_ma_period = res['ma_period']

                st.markdown("---")
                st.subheader(f"📊 Screener Output Summary (Close > {p_ma_period} {p_ma_type})")

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Screened", f"{len(passed) + len(failed) + len(errors)}")
                m2.metric("Stocks Above MA (Passed)", f"{len(passed)}", delta=f"{len(passed)} stocks", delta_color="normal")
                m3.metric("Stocks Below MA (Failed)", f"{len(failed)}")
                m4.metric("Errors / Missing Data", f"{len(errors)}")

                if passed:
                    st.success(f"✅ Found **{len(passed)} stocks** trading **ABOVE** the {p_ma_period} {p_ma_type}!")
                    
                    passed_df = pd.DataFrame(passed)
                    # Sort by % Above MA descending
                    passed_df = passed_df.sort_values(by="% Above MA", ascending=False)

                    st.write(f"### 📋 Stocks Above Moving Average ({len(passed_df)} stocks)")
                    st.dataframe(passed_df, width="stretch")

                    col_dl, _ = st.columns([1, 1])
                    with col_dl:
                        csv_data = passed_df.to_csv(index=False)
                        st.download_button(
                            label=f"💾 Download Screened Stocks CSV ({len(passed)} stocks)",
                            data=csv_data,
                            file_name=f"screener_above_{p_ma_type}{p_ma_period}_{datetime.today().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            type="primary",
                            width="stretch"
                        )

                    # Interactive Chart Visualizer for Screened Stocks
                    st.markdown("---")
                    st.subheader("📉 Visualizer for Screened Stocks")
                    selected_chart_sym = st.selectbox(
                        "Select a passed stock to view price chart & Moving Average line:",
                        options=passed_df["Symbol"].tolist()
                    )

                    if selected_chart_sym:
                        with st.spinner(f"Loading chart for {selected_chart_sym}..."):
                            try:
                                t_obj = yf.Ticker(selected_chart_sym)
                                chart_data = t_obj.history(
                                    start=start_date,
                                    end=end_date + timedelta(days=1),
                                    interval=selected_interval,
                                    auto_adjust=False
                                ).reset_index()

                                if 'Date' in chart_data.columns:
                                    chart_data['Date'] = pd.to_datetime(chart_data['Date']).dt.date
                                elif 'Datetime' in chart_data.columns:
                                    chart_data['Date'] = pd.to_datetime(chart_data['Datetime']).dt.date

                                if p_ma_type == "SMA":
                                    chart_data['MA'] = chart_data['Close'].rolling(window=int(p_ma_period)).mean()
                                else:
                                    chart_data['MA'] = chart_data['Close'].ewm(span=int(p_ma_period), adjust=False).mean()

                                try:
                                    go = importlib.import_module("plotly.graph_objects")
                                    fig = go.Figure()
                                    fig.add_trace(go.Candlestick(
                                        x=chart_data['Date'],
                                        open=chart_data['Open'],
                                        high=chart_data['High'],
                                        low=chart_data['Low'],
                                        close=chart_data['Close'],
                                        name="OHLC"
                                    ))
                                    fig.add_trace(go.Scatter(
                                        x=chart_data['Date'],
                                        y=chart_data['MA'],
                                        mode='lines',
                                        name=f"{p_ma_type} {p_ma_period}",
                                        line=dict(color='orange', width=2)
                                    ))
                                    fig.update_layout(
                                        title=f"{selected_chart_sym} - Close vs {p_ma_type} {p_ma_period}",
                                        xaxis_title="Date",
                                        yaxis_title="Price",
                                        template="plotly_white",
                                        xaxis_rangeslider_visible=False,
                                        height=500
                                    )
                                    st.plotly_chart(fig, width="stretch")
                                except (ImportError, ModuleNotFoundError):
                                    st.info("💡 `plotly` package is not installed in this Python environment. Displaying native chart. (Run `pip install plotly` for interactive candlestick charts).")
                                    chart_df = chart_data.set_index('Date')[['Close', 'MA']].copy()
                                    chart_df.rename(columns={'MA': f"{p_ma_type} {p_ma_period}"}, inplace=True)
                                    st.line_chart(chart_df)

                            except Exception as chart_err:
                                st.error(f"Error plotting chart for {selected_chart_sym}: {chart_err}")
                else:
                    st.warning(f"No stocks found trading above the {p_ma_period} {p_ma_type}.")

                if errors:
                    with st.expander("See Skipped / Error Symbols"):
                        st.dataframe(pd.DataFrame(errors))

        except Exception as e:
            st.error(f"Error reading CSV file: {e}")

