import sqlite3
import pandas as pd
import json
import os
import math
import requests
import concurrent.futures
from datetime import datetime, timedelta
import yfinance as yf
from init_database import init_database, DB_PATH
import sys

# 解決 Windows 終端機 Unicode 輸出問題
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# ---------------------------------------------------------------------------
# 技術指標計算
# ---------------------------------------------------------------------------

def calculate_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def calculate_indicators(df):
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma60'] = df['close'].rolling(window=60).mean()
    std20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['ma20'] + (2 * std20)
    df['bb_lower'] = df['ma20'] - (2 * std20)
    df = df.where(pd.notnull(df), None)
    return df

# ---------------------------------------------------------------------------
# 資料來源
# ---------------------------------------------------------------------------

def get_db_data():
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT date, symbol, name, open, high, low, close, volume FROM daily_quotes ORDER BY symbol, date"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_stock_industry_map():
    """取得台股全市場產業類別對應表"""
    try:
        url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
        res = requests.get(url, timeout=10)
        data = res.json()
        return {d['stock_id']: d.get('industry_category', '') for d in data.get('data', []) if d.get('stock_id')}
    except Exception as e:
        print(f"無法取得產業類別: {e}")
        return {}

def _download_yf(symbol, period="2y"):
    """統一的 yfinance 下載入口，自動處理 MultiIndex"""
    try:
        df = yf.download(symbol, period=period, progress=False)
        if not df.empty and isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        return df
    except Exception:
        return pd.DataFrame()

# ---------------------------------------------------------------------------
# 篩選輔助函數
# ---------------------------------------------------------------------------

def check_monthly_macd_shrink(symbol, yf_df=None):
    """檢查月MACD是否也呈現綠柱2連縮。可傳入已下載的 yf_df 避免重複下載。"""
    try:
        if yf_df is None:
            yf_df = _download_yf(symbol)
        if yf_df.empty:
            return False, yf_df

        m_df = yf_df['Close'].resample('ME').last().to_frame(name='close').dropna()
        if len(m_df) < 6:
            return False, yf_df
        _, _, m_hist = calculate_macd(m_df)

        h0, h1, h2 = float(m_hist.iloc[-1]), float(m_hist.iloc[-2]), float(m_hist.iloc[-3])
        return (h0 < 0 and h1 < 0 and h2 < 0 and h0 > h1 and h1 > h2), yf_df
    except Exception:
        return False, pd.DataFrame()

def check_institutional_buy_2_days(symbol):
    """檢查近兩日外資或投信是否有連續買超"""
    try:
        clean_symbol = symbol.replace('.TW', '').replace('.TWO', '')
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={clean_symbol}&start_date={start_date}"
        res = requests.get(url, timeout=10)
        data = res.json()
        if data['status'] != 200 or not data['data']:
            return False

        df = pd.DataFrame(data['data'])
        if df.empty:
            return False

        dates = sorted(df['date'].unique())
        if len(dates) < 2:
            return False

        foreign_buy_streak = True
        trust_buy_streak = True

        for d in dates[-2:]:
            day_df = df[df['date'] == d]
            foreign = day_df[day_df['name'] == 'Foreign_Investor']
            trust = day_df[day_df['name'] == 'Investment_Trust']

            if not foreign.empty and (foreign.iloc[0]['buy'] - foreign.iloc[0]['sell']) <= 0:
                foreign_buy_streak = False
            if not trust.empty and (trust.iloc[0]['buy'] - trust.iloc[0]['sell']) <= 0:
                trust_buy_streak = False

        return foreign_buy_streak or trust_buy_streak
    except Exception:
        return False

# ---------------------------------------------------------------------------
# 格式化輸出
# ---------------------------------------------------------------------------

def _safe_round(val, decimals):
    return None if pd.isna(val) else round(val, decimals)

def format_history(df, sym, yf_df_cache=None):
    """將本地 DB 資料轉為前端 K 線格式。yf_df_cache 可傳入已下載的 2 年資料複用。"""
    chart_df = df.tail(60)

    ma248_lookup = {}
    yf_df = yf_df_cache if yf_df_cache is not None and not yf_df_cache.empty else _download_yf(sym)
    if not yf_df.empty:
        yf_df['ma248'] = yf_df['Close'].rolling(window=248).mean()
        for d, row in yf_df.iterrows():
            if pd.notna(row['ma248']):
                ma248_lookup[d.strftime('%Y-%m-%d')] = round(float(row['ma248']), 2)

    history_data = []
    for _, r in chart_df.iterrows():
        history_data.append({
            'date': r['date'],
            'open': _safe_round(r['open'], 2), 'high': _safe_round(r['high'], 2),
            'low': _safe_round(r['low'], 2), 'close': _safe_round(r['close'], 2),
            'volume': int(r['volume'] / 1000) if pd.notna(r['volume']) else 0,
            'ma5': _safe_round(r['ma5'], 2), 'ma10': _safe_round(r['ma10'], 2),
            'ma60': _safe_round(r['ma60'], 2), 'ma248': ma248_lookup.get(r['date']),
            'bb_upper': _safe_round(r['bb_upper'], 2), 'bb_lower': _safe_round(r['bb_lower'], 2),
            'macd': _safe_round(r['macd'], 4), 'signal': _safe_round(r['Signal'], 4),
            'hist': _safe_round(r['Hist'], 4)
        })
    return history_data

def format_stock_output(stock_info, yf_df_cache=None):
    """格式化單檔股票輸出，可傳入 yf_df_cache 以複用已下載的資料。"""
    last_day = stock_info['last_day']
    prev_day = stock_info['prev_day']
    df = stock_info['df']
    price = round(last_day['close'], 2)
    change = round(last_day['close'] - prev_day['close'], 2)
    change_percent = round((change / prev_day['close']) * 100, 2)
    recent_low = df['low'].tail(5).min()
    return {
        "symbol": stock_info['symbol'].replace('.TW', '').replace('.TWO', ''),
        "name": stock_info['name'],
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "volume": int(last_day['volume'] / 1000),
        "suggested_buy_price": round(recent_low, 2),
        "date": last_day['date'],
        "history": format_history(df, stock_info['symbol'], yf_df_cache)
    }

# ---------------------------------------------------------------------------
# 主選股邏輯
# ---------------------------------------------------------------------------

def run_screener():
    print("【第一步】更新本地資料庫 (自動補齊最新交易日)...")
    conn_check = sqlite3.connect(DB_PATH)
    cursor_check = conn_check.cursor()
    cursor_check.execute('SELECT COUNT(DISTINCT date) FROM daily_quotes')
    existing_days = cursor_check.fetchone()[0]
    conn_check.close()

    if existing_days < 120:
        days_needed = 150 - existing_days
        print(f"  資料庫只有 {existing_days} 天，需補充至 150 天...")
        init_database(days_needed)
    else:
        init_database(1)

    print("【第二步】載入全市場歷史資料與產業分類...")
    stock_industry = get_stock_industry_map()
    target_electronic_keywords = ['電子', '半導體', '零組件', '光電', '電腦', '通信', '資訊服務']

    df_all = get_db_data()
    if df_all.empty:
        print("資料庫為空！")
        return {"tea": [], "moon": [], "fifty": []}

    symbol_groups = df_all.groupby('symbol')

    tea_candidates = []
    moon_candidates = []
    fifty_candidates = []

    # 0050 成分股清單 (台灣50指數)
    fifty_symbols = [
        '2330', '2454', '2317', '2308', '2382', '3711', '2303', '2881', '2891', '2882',
        '2886', '3034', '2412', '2884', '3231', '2357', '6669', '1303', '2002', '1301',
        '2880', '5880', '1326', '5871', '2892', '3037', '2885', '2883', '3661', '4904',
        '2887', '6505', '1101', '2395', '3045', '2207', '4938', '9910', '2603', '2301',
        '5876', '2327', '1216', '2379', '6446', '8046', '3017', '8069', '2345', '6526'
    ]

    for symbol, df in symbol_groups:
        if len(df) < 35: continue
        clean_symbol = symbol.replace('.TW', '').replace('.TWO', '')
        if len(clean_symbol) != 4: continue

        df = df.sort_values('date').reset_index(drop=True)
        macd, signal, hist = calculate_macd(df)
        df = df.assign(macd=macd, Signal=signal, Hist=hist)
        df = calculate_indicators(df)

        last_day = df.iloc[-1]
        prev_day_1 = df.iloc[-2]
        prev_day_2 = df.iloc[-3]

        if pd.isna(last_day['volume']): continue
        vol_shares = last_day['volume']

        h0, h1, h2 = last_day['Hist'], prev_day_1['Hist'], prev_day_2['Hist']
        shrink_2 = (h0 < 0 and h1 < 0 and h2 < 0 and h0 > h1 and h1 > h2)

        stock_info = {
            'symbol': symbol, 'name': last_day['name'],
            'last_day': last_day, 'prev_day': prev_day_1, 'df': df
        }

        # Tea: Volume > 3000張, Daily MACD > 0, 綠柱2連縮
        if vol_shares > 3000000 and last_day['macd'] > 0 and shrink_2:
            tea_candidates.append(stock_info)

        # Fifty: 0050 成分股 + 綠柱2連縮
        if clean_symbol in fifty_symbols and shrink_2:
            fifty_candidates.append(stock_info)

        # Moon (止月策略): 電子/半導體/零組件 + 近3日內有觸及兩個月最低價
        cat = stock_industry.get(clean_symbol, '')
        is_electronic_sector = any(k in cat for k in target_electronic_keywords)
        if is_electronic_sector and len(df) >= 42 and vol_shares >= 100000:
            df_2m = df.tail(42)
            min_2m_low = df_2m['low'].min()
            # 最近 3 個交易日內任一天的最低價觸及 2 個月低點即納入
            recent_3_lows = df.tail(3)['low']
            if recent_3_lows.min() <= min_2m_low:
                moon_candidates.append(stock_info)

    print(f"初篩通過數 -> 茶葉:{len(tea_candidates)} 止月:{len(moon_candidates)} 50大:{len(fifty_candidates)}")

    # ------------------
    # Process Tea (多執行緒：yf 週 MACD + 籌碼面 + K線)
    # ------------------
    tea_results = []
    print("【進階處理】茶葉智慧站...")

    def process_tea(s):
        sym = s['symbol']
        try:
            yf_df = _download_yf(sym, period="2y")
            if yf_df.empty:
                return None
            # 週 MACD > 0
            w_df = yf_df['Close'].resample('W-FRI').last().to_frame(name='close')
            w_macd, _, _ = calculate_macd(w_df)
            if w_macd.iloc[-1] <= 0:
                return None
        except Exception:
            return None
        # 籌碼面
        if not check_institutional_buy_2_days(sym):
            return None
        return format_stock_output(s, yf_df_cache=yf_df)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(process_tea, tea_candidates):
            if res: tea_results.append(res)

    # ------------------
    # Process Moon (多執行緒：直接生成 K 線)
    # ------------------
    moon_results = []
    print("【進階處理】止月...")

    def process_moon(s):
        yf_df = _download_yf(s['symbol'], period="2y")
        return format_stock_output(s, yf_df_cache=yf_df)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(process_moon, moon_candidates):
            if res: moon_results.append(res)

    # ------------------
    # Process Fifty (多執行緒：月MACD + K線，共用一次下載)
    # ------------------
    fifty_results = []
    print("【進階處理】50大 (月MACD檢查)...")

    def process_fifty(s):
        yf_df = _download_yf(s['symbol'], period="2y")
        passed, yf_df = check_monthly_macd_shrink(s['symbol'], yf_df)
        if passed:
            return format_stock_output(s, yf_df_cache=yf_df)
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(process_fifty, fifty_candidates):
            if res: fifty_results.append(res)

    return {
        "tea": tea_results,
        "moon": moon_results,
        "fifty": fifty_results
    }

# ---------------------------------------------------------------------------
# ETF 專區
# ---------------------------------------------------------------------------

def process_etfs():
    long_etf_symbols = ['0050', '006208', '00631L', '00981A', '0052', '009816']
    high_div_etf_symbols = ['0056', '00878', '00919', '00929']

    div_freq = {'0056': '季配息', '00878': '季配息', '00919': '季配息', '00929': '月配息'}

    ch_names = {
        '0050': '元大台灣50', '006208': '富邦台50', '00631L': '元大台灣50正2',
        '00981A': '統一台股增長', '0052': '富邦科技', '009816': '凱基台灣TOP50',
        '0056': '元大高股息', '00878': '國泰永續高股息',
        '00919': '群益台灣精選高息', '00929': '復華台灣科技優息'
    }

    long_etfs = []
    high_div_etfs = []

    def _process_single_etf(sym):
        try:
            name = ch_names.get(sym, sym)
            yf_sym = f"{sym}.TW"
            ticker = yf.Ticker(yf_sym)

            df = yf.download(yf_sym, start="2024-12-01", progress=False)
            if df.empty: return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            df = df.dropna(subset=['Close'])
            if df.empty: return None

            current_price = float(df['Close'].iloc[-1])
            prev_price = float(df['Close'].iloc[-2]) if len(df) > 1 else current_price
            change = current_price - prev_price
            change_percent = (change / prev_price) * 100 if prev_price else 0
            volume = int(df['Volume'].iloc[-1] / 1000)
            recent_low = float(df['Low'].tail(5).min())
            date_str = df.index[-1].strftime('%Y-%m-%d')

            df_2025 = df[df.index.year <= 2025]
            price_end_2025 = float(df_2025['Close'].iloc[-1]) if not df_2025.empty else float(df['Close'].iloc[0])
            df_2024 = df[df.index.year <= 2024]
            price_end_2024 = float(df_2024['Close'].iloc[-1]) if not df_2024.empty else price_end_2025

            ytd = ((current_price / price_end_2025) - 1) * 100 if price_end_2025 else 0
            last_year_perf = ((price_end_2025 / price_end_2024) - 1) * 100 if price_end_2024 else 0

            # K 線資料 (複用已下載的 df，不再重新呼叫 yf.download)
            chart_df = df.copy()
            chart_df.columns = [c.lower() for c in chart_df.columns]
            chart_df = chart_df.reset_index()
            chart_df['date'] = chart_df['Date'].dt.strftime('%Y-%m-%d')
            macd_v, signal_v, hist_v = calculate_macd(chart_df)
            chart_df = chart_df.assign(macd=macd_v, Signal=signal_v, Hist=hist_v)
            chart_df = calculate_indicators(chart_df)
            # ETF 的 format_history 也複用同一份 df 資料，避免二次下載
            history = format_history(chart_df, yf_sym, yf_df_cache=df)

            etf_data = {
                "symbol": sym, "name": name,
                "price": round(current_price, 2), "change": round(change, 2),
                "change_percent": round(change_percent, 2), "volume": volume,
                "suggested_buy_price": round(recent_low, 2), "date": date_str,
                "ytd": round(ytd, 2), "last_year_perf": round(last_year_perf, 2),
                "history": history
            }

            if sym in high_div_etf_symbols:
                divs = ticker.dividends
                divs_2025 = float(divs[divs.index.year == 2025].sum()) if not divs.empty else 0
                yield_2025 = (divs_2025 / price_end_2025) * 100 if price_end_2025 else 0
                divs_2026 = float(divs[divs.index.year == 2026].sum()) if not divs.empty else 0
                ytd_yield = (divs_2026 / current_price) * 100 if (current_price and current_price > 0) else 0
                etf_data["div_freq"] = div_freq.get(sym, '未知')
                etf_data["last_year_yield"] = round(yield_2025, 2)
                etf_data["ytd_yield"] = round(ytd_yield, 2)

            return (sym, etf_data)
        except Exception as e:
            print(f"Error processing ETF {sym}: {e}")
            return None

    all_symbols = long_etf_symbols + high_div_etf_symbols
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for result in executor.map(_process_single_etf, all_symbols):
            if result is None: continue
            sym, etf_data = result
            if sym in long_etf_symbols:
                long_etfs.append(etf_data)
            if sym in high_div_etf_symbols:
                high_div_etfs.append(etf_data)

    return long_etfs, high_div_etfs

# ---------------------------------------------------------------------------
# 全球指數
# ---------------------------------------------------------------------------

def fetch_indices():
    indices_list = [
        {'symbol': '^TWII', 'name': '台股加權指數'},
        {'symbol': '^SOX', 'name': '費城半導體'},
        {'symbol': '^DJI', 'name': '道瓊工業'},
        {'symbol': '^IXIC', 'name': 'NASDAQ'},
        {'symbol': '^GSPC', 'name': 'S&P 500'},
        {'symbol': '^N225', 'name': '日經225'},
        {'symbol': '^HSI', 'name': '香港恒生'}
    ]
    chart_symbols = {'^TWII', '^SOX', '^DJI', '^IXIC', '^GSPC'}

    def _fetch_single_index(idx):
        try:
            period = '6mo' if idx['symbol'] in chart_symbols else '5d'
            df = _download_yf(idx['symbol'], period=period)
            if df.empty:
                return None

            current = float(df['Close'].iloc[-1])
            prev = float(df['Close'].iloc[-2]) if len(df) > 1 else current
            change = current - prev
            change_percent = (change / prev) * 100 if prev else 0

            item = {
                "symbol": idx['symbol'], "name": idx['name'],
                "price": round(current, 2), "change": round(change, 2),
                "change_percent": round(change_percent, 2)
            }

            if idx['symbol'] in chart_symbols:
                df['ma5'] = df['Close'].rolling(window=5).mean()
                df['ma20'] = df['Close'].rolling(window=20).mean()
                history_data = []
                for d, row in df.tail(60).iterrows():
                    history_data.append({
                        "date": d.strftime('%Y-%m-%d'),
                        "open": round(float(row['Open']), 2),
                        "close": round(float(row['Close']), 2),
                        "low": round(float(row['Low']), 2),
                        "high": round(float(row['High']), 2),
                        "volume": int(row['Volume']),
                        "ma5": round(float(row['ma5']), 2) if not pd.isna(row['ma5']) else None,
                        "ma20": round(float(row['ma20']), 2) if not pd.isna(row['ma20']) else None
                    })
                item["history"] = history_data

            return item
        except Exception as e:
            print(f"Error fetching index {idx['symbol']}: {e}")
            return None

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(_fetch_single_index, indices_list):
            if res: results.append(res)
    return results

# ---------------------------------------------------------------------------
# JSON 輸出與清理
# ---------------------------------------------------------------------------

def scrub_nans(obj):
    """遞迴將 NaN/Inf 轉為 None，確保 JSON 輸出安全"""
    if isinstance(obj, dict):
        return {k: scrub_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [scrub_nans(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj

# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_database(150)

    data = run_screener()

    if os.environ.get('GITHUB_ACTIONS') == 'true':
        output_file = 'data.json'
    else:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
        output_file = os.path.join(output_dir, 'data.json')

    print("【進階處理】長期ETF區與高股息ETF區...")
    long_etfs_res, high_div_etfs_res = process_etfs()

    print("抓取全球指數資料...")
    indices_res = fetch_indices()

    # 記錄篩選歷史 (保留寫入 DB，供未來追蹤使用)
    print("記錄篩選歷史...")
    today_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for strat, records in [('tea', data['tea']), ('moon', data['moon']), ('fifty', data['fifty'])]:
        for rec in records:
            cursor.execute('''
                INSERT OR IGNORE INTO screened_history (date, symbol, name, screened_price, strategy)
                VALUES (?, ?, ?, ?, ?)
            ''', (today_str, rec['symbol'], rec['name'], rec['price'], strat))
    conn.commit()

    # 清理 30 天前舊紀錄
    thirty_days_ago = (datetime.utcnow() + timedelta(hours=8) - timedelta(days=30)).strftime("%Y-%m-%d")
    cursor.execute("DELETE FROM screened_history WHERE date < ?", (thirty_days_ago,))

    # 清理 180 天前的舊行情資料並壓縮 DB
    cutoff = (datetime.utcnow() + timedelta(hours=8) - timedelta(days=180)).strftime("%Y-%m-%d")
    cursor.execute("DELETE FROM daily_quotes WHERE date < ?", (cutoff,))
    conn.commit()
    cursor.execute("VACUUM")
    conn.close()

    # 匯出 JSON
    print("匯出資料至 JSON...")
    output = {
        "updated_at": (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
        "data": {
            "tea": sorted(data['tea'], key=lambda x: x['symbol']),
            "moon": sorted(data['moon'], key=lambda x: x['symbol']),
            "fifty": sorted(data['fifty'], key=lambda x: x['symbol']),
            "long_etf": long_etfs_res,
            "high_div": high_div_etfs_res,
            "indices": indices_res
        }
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(scrub_nans(output), f, ensure_ascii=False, indent=4)

    print(f"分析完成！茶葉:{len(data['tea'])} 止月:{len(data['moon'])} 50大:{len(data['fifty'])}")
