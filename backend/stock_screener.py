import sqlite3
import pandas as pd
import json
import os
import requests
import concurrent.futures
from datetime import datetime, timedelta
import yfinance as yf
from init_database import init_database, DB_PATH
import sys

# 解決 Windows 終端機 Unicode 輸出問題
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

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
    df['ma60'] = df['close'].rolling(window=60).mean()
    ma20 = df['close'].rolling(window=20).mean()
    std20 = df['close'].rolling(window=20).std()
    df['bb_upper'] = ma20 + (2 * std20)
    df['bb_lower'] = ma20 - (2 * std20)
    df = df.where(pd.notnull(df), None)
    return df

def get_db_data():
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT date, symbol, name, open, high, low, close, volume FROM daily_quotes ORDER BY symbol, date"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def check_cumulative_yoy_3_months(symbol):
    try:
        clean_symbol = symbol.replace('.TW', '').replace('.TWO', '')
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id={clean_symbol}&start_date=2024-01-01"
        res = requests.get(url, timeout=10)
        data = res.json()
        if data['status'] != 200 or not data['data']:
            return False 
        df_rev = pd.DataFrame(data['data'])
        if len(df_rev) < 15:
            return False
        df_rev = df_rev.sort_values(by=['revenue_year', 'revenue_month']).reset_index(drop=True)
        latest_3_months = df_rev.tail(3)
        
        current_sum = 0
        last_year_sum = 0
        
        for index, row in latest_3_months.iterrows():
            last_year_month = df_rev[(df_rev['revenue_year'] == row['revenue_year'] - 1) & 
                                     (df_rev['revenue_month'] == row['revenue_month'])]
            if last_year_month.empty:
                return False
            current_sum += row['revenue']
            last_year_sum += last_year_month.iloc[0]['revenue']
            
        return current_sum > last_year_sum
    except Exception:
        return False

def check_institutional_buy_2_days(symbol):
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
            
        last_2_dates = dates[-2:]
        
        foreign_buy_streak = True
        trust_buy_streak = True
        
        for d in last_2_dates:
            day_df = df[df['date'] == d]
            foreign = day_df[day_df['name'] == 'Foreign_Investor']
            trust = day_df[day_df['name'] == 'Investment_Trust']
            
            foreign_net = foreign.iloc[0]['buy'] - foreign.iloc[0]['sell'] if not foreign.empty else 0
            trust_net = trust.iloc[0]['buy'] - trust.iloc[0]['sell'] if not trust.empty else 0
            
            if foreign_net <= 0:
                foreign_buy_streak = False
            if trust_net <= 0:
                trust_buy_streak = False
                
        return foreign_buy_streak or trust_buy_streak
    except Exception:
        return False

def format_history(df, sym):
    chart_df = df.tail(60)
    
    ma_data = None
    try:
        yf_df = yf.download(sym, period="2y", progress=False)
        if not yf_df.empty:
            if isinstance(yf_df.columns, pd.MultiIndex):
                yf_df.columns = yf_df.columns.droplevel(1)
                
            yf_df['ma5'] = yf_df['Close'].rolling(window=5).mean()
            yf_df['ma10'] = yf_df['Close'].rolling(window=10).mean()
            yf_df['ma60'] = yf_df['Close'].rolling(window=60).mean()
            yf_df['ma248'] = yf_df['Close'].rolling(window=248).mean()
            
            ma20 = yf_df['Close'].rolling(window=20).mean()
            std20 = yf_df['Close'].rolling(window=20).std()
            yf_df['bb_upper'] = ma20 + (2 * std20)
            yf_df['bb_lower'] = ma20 - (2 * std20)
            
            yf_df.index = yf_df.index.strftime('%Y-%m-%d')
            ma_data = yf_df
    except Exception:
        pass

    history_data = []
    def safe_round(val, decimals):
        return None if pd.isna(val) else round(val, decimals)
        
    for _, r in chart_df.iterrows():
        date_str = r['date']
        
        # Default to local DB calculations if yf fails, though local may have NaNs for early days
        ma5_val = r['ma5']
        ma10_val = r['ma10']
        ma60_val = r['ma60']
        bb_upper_val = r['bb_upper']
        bb_lower_val = r['bb_lower']
        ma248_val = None
        
        if ma_data is not None and date_str in ma_data.index:
            yf_row = ma_data.loc[date_str]
            ma5_val = yf_row['ma5']
            ma10_val = yf_row['ma10']
            ma60_val = yf_row['ma60']
            ma248_val = yf_row['ma248']
            bb_upper_val = yf_row['bb_upper']
            bb_lower_val = yf_row['bb_lower']
            
        history_data.append({
            'date': r['date'], 'open': r['open'], 'high': r['high'], 'low': r['low'],
            'close': r['close'], 'volume': int(r['volume'] / 1000) if pd.notna(r['volume']) else 0,
            'ma5': safe_round(ma5_val, 2), 
            'ma10': safe_round(ma10_val, 2), 
            'ma60': safe_round(ma60_val, 2),
            'ma248': safe_round(ma248_val, 2),
            'bb_upper': safe_round(bb_upper_val, 2), 
            'bb_lower': safe_round(bb_lower_val, 2),
            'macd': safe_round(r['macd'], 4), 'signal': safe_round(r['Signal'], 4), 'hist': safe_round(r['Hist'], 4)
        })
    return history_data

def format_stock_output(stock_info):
    last_day = stock_info['last_day']
    prev_day = stock_info['prev_day']
    df = stock_info['df']
    price = round(last_day['close'], 2)
    change = round(last_day['close'] - prev_day['close'], 2)
    change_percent = round((change / prev_day['close']) * 100, 2)
    recent_low = df['low'].tail(5).min()
    yf_sym = stock_info['symbol']
    if yf_sym.endswith('.TWO'):
        yf_sym = yf_sym.replace('.TWO', '.TWO') # yf uses .TWO for OTC
    return {
        "symbol": stock_info['symbol'].replace('.TW', '').replace('.TWO', ''),
        "name": stock_info['name'],
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "volume": int(last_day['volume'] / 1000), 
        "suggested_buy_price": round(recent_low, 2),
        "date": last_day['date'],
        "history": format_history(df, yf_sym)
    }

def run_screener():
    print("【第一步】更新本地資料庫 (自動補齊最新交易日)...")
    init_database(1)
    
    print("【第二步】載入全市場歷史資料...")
    df_all = get_db_data()
    if df_all.empty:
        print("資料庫為空！")
        return {"tea": [], "test": [], "moon": []}
        
    symbol_groups = df_all.groupby('symbol')
    
    tea_candidates = []
    test_candidates = []
    moon_candidates = []
    
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
        prev_day_3 = df.iloc[-4]
        
        if pd.isna(last_day['volume']): continue
        vol_shares = last_day['volume']
        
        h0, h1, h2, h3 = last_day['Hist'], prev_day_1['Hist'], prev_day_2['Hist'], prev_day_3['Hist']
        
        shrink_2 = (h0 < 0 and h1 < 0 and h2 < 0 and h0 > h1 and h1 > h2)
        shrink_3 = (shrink_2 and h3 < 0 and h2 > h3)
        
        stock_info = {
            'symbol': symbol, 'name': last_day['name'],
            'last_day': last_day, 'prev_day': prev_day_1, 'df': df
        }
        
        # Tea: Volume > 3000, Daily MACD > 0, Shrink 2 days
        if vol_shares > 3000000 and last_day['macd'] > 0 and shrink_2:
            tea_candidates.append(stock_info)
            
        # Test: Volume > 3000, Shrink 2 days
        if vol_shares > 3000000 and shrink_2:
            test_candidates.append(stock_info)
            
        # Moon: Volume > 1000, Shrink 3 days
        if vol_shares > 1000000 and shrink_3:
            moon_candidates.append(stock_info)

    print(f"初篩通過數 -> 茶葉:{len(tea_candidates)} 測試:{len(test_candidates)} 止月:{len(moon_candidates)}")
    
    # ------------------
    # Process Tea
    # ------------------
    tea_results = []
    print("【進階處理】茶葉智慧站...")
    for s in tea_candidates:
        sym = s['symbol']
        try:
            yf_df = yf.download(sym, period="1y", progress=False)
            if yf_df.empty: continue
            if isinstance(yf_df.columns, pd.MultiIndex):
                yf_df.columns = yf_df.columns.droplevel(1)
                
            w_df = yf_df['Close'].resample('W-FRI').last().to_frame(name='close')
            w_macd, _, _ = calculate_macd(w_df)
            if w_macd.iloc[-1] <= 0:
                continue
                
        except Exception as e:
            continue
            
        if not check_institutional_buy_2_days(sym):
            continue
            
        tea_results.append(format_stock_output(s))

    # ------------------
    # Process Test
    # ------------------
    test_results = []
    print("【進階處理】測試...")
    def process_test(s):
        if check_cumulative_yoy_3_months(s['symbol']) and check_institutional_buy_2_days(s['symbol']):
            return format_stock_output(s)
        return None
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(process_test, test_candidates):
            if res: test_results.append(res)

    # ------------------
    # Process Moon
    # ------------------
    moon_results = []
    print("【進階處理】止月...")
    for s in moon_candidates:
        sym = s['symbol']
        try:
            yf_df = yf.download(sym, period="ytd", progress=False)
            if yf_df.empty: continue
            if isinstance(yf_df.columns, pd.MultiIndex):
                yf_df.columns = yf_df.columns.droplevel(1)
                
            ytd_low = yf_df['Low'].min()
            ytd_high = yf_df['High'].max()
            today_low = s['last_day']['low']
            today_close = s['last_day']['close']
            
            if today_low <= ytd_low or today_close <= (ytd_high * 0.70):
                moon_results.append(format_stock_output(s))
        except Exception:
            continue

    return {
        "tea": tea_results,
        "test": test_results,
        "moon": moon_results
    }

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_database(60)
        
    data = run_screener()
    
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        output_file = 'data.json'
    else:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
        output_file = os.path.join(output_dir, 'data.json')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        print("【進階處理】長期ETF區與高股息ETF區...")
    
    def process_etfs():
        long_etf_symbols = ['0050', '006208', '00631L', '00981A', '0052', '009816']
        high_div_etf_symbols = ['0056', '00878', '00919', '00929']
        
        div_freq = {
            '0056': '季配息',
            '00878': '季配息',
            '00919': '季配息',
            '00929': '月配息'
        }
        
        ch_names = {
            '0050': '元大台灣50',
            '006208': '富邦台50',
            '00631L': '元大台灣50正2',
            '00981A': '統一台股增長',
            '0052': '富邦科技',
            '009816': '凱基台灣TOP50',
            '0056': '元大高股息',
            '00878': '國泰永續高股息',
            '00919': '群益台灣精選高息',
            '00929': '復華台灣科技優息'
        }
        
        long_etfs = []
        high_div_etfs = []
        
        all_symbols = long_etf_symbols + high_div_etf_symbols
        
        for sym in all_symbols:
            try:
                name = ch_names.get(sym, sym)
                yf_sym = f"{sym}.TW"
                ticker = yf.Ticker(yf_sym)
                
                df = yf.download(yf_sym, start="2024-12-01", progress=False)
                if df.empty:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                    
                # Calculate stats
                current_price = float(df['Close'].iloc[-1])
                prev_price = float(df['Close'].iloc[-2]) if len(df) > 1 else current_price
                change = current_price - prev_price
                change_percent = (change / prev_price) * 100 if prev_price else 0
                volume = int(df['Volume'].iloc[-1] / 1000)
                recent_low = df['Low'].tail(5).min()
                date_str = df.index[-1].strftime('%Y-%m-%d')
                
                df_2025 = df[df.index.year <= 2025]
                price_end_2025 = float(df_2025['Close'].iloc[-1]) if not df_2025.empty else float(df['Close'].iloc[0])
                
                df_2024 = df[df.index.year <= 2024]
                price_end_2024 = float(df_2024['Close'].iloc[-1]) if not df_2024.empty else price_end_2025
                
                ytd = ((current_price / price_end_2025) - 1) * 100 if price_end_2025 else 0
                last_year_perf = ((price_end_2025 / price_end_2024) - 1) * 100 if price_end_2024 else 0
                
                # Prepare chart df
                chart_df = df.copy()
                chart_df.columns = [c.lower() for c in chart_df.columns]
                chart_df = chart_df.reset_index()
                chart_df['date'] = chart_df['Date'].dt.strftime('%Y-%m-%d')
                macd, signal, hist = calculate_macd(chart_df)
                chart_df = chart_df.assign(macd=macd, Signal=signal, Hist=hist)
                chart_df = calculate_indicators(chart_df)
                history = format_history(chart_df, yf_sym)
                
                etf_data = {
                    "symbol": sym,
                    "name": name,
                    "price": round(current_price, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_percent, 2),
                    "volume": volume,
                    "suggested_buy_price": round(recent_low, 2),
                    "date": date_str,
                    "ytd": round(ytd, 2),
                    "last_year_perf": round(last_year_perf, 2),
                    "history": history
                }
                
                if sym in long_etf_symbols:
                    long_etfs.append(etf_data)
                    
                if sym in high_div_etf_symbols:
                    divs = ticker.dividends
                    divs_2025 = divs[divs.index.year == 2025].sum() if not divs.empty else 0
                    yield_2025 = (divs_2025 / price_end_2025) * 100 if price_end_2025 else 0
                    
                    divs_2026 = divs[divs.index.year == 2026].sum() if not divs.empty else 0
                    ytd_yield = (divs_2026 / current_price) * 100 if current_price else 0
                    
                    etf_data["div_freq"] = div_freq.get(sym, '未知')
                    etf_data["last_year_yield"] = round(yield_2025, 2)
                    etf_data["ytd_yield"] = round(ytd_yield, 2)
                    high_div_etfs.append(etf_data)
                    
            except Exception as e:
                print(f"Error processing ETF {sym}: {e}")
                
        return long_etfs, high_div_etfs

    long_etfs_res, high_div_etfs_res = process_etfs()

    print("抓取全球指數資料...")
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
        
        results = []
        for idx in indices_list:
            try:
                period_to_fetch = '6mo' if idx['symbol'] == '^TWII' else '5d'
                df = yf.download(idx['symbol'], period=period_to_fetch, progress=False)
                if not df.empty:
                    if hasattr(df.columns, 'levels'):
                        df.columns = df.columns.droplevel(1)
                    current = float(df['Close'].iloc[-1])
                    prev = float(df['Close'].iloc[-2]) if len(df) > 1 else current
                    change = current - prev
                    change_percent = (change / prev) * 100 if prev else 0
                    
                    item = {
                        "name": idx['name'],
                        "price": round(current, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_percent, 2)
                    }
                    
                    if idx['symbol'] == '^TWII':
                        df['ma5'] = df['Close'].rolling(window=5).mean()
                        df['ma20'] = df['Close'].rolling(window=20).mean()
                        history_data = []
                        chart_df = df.tail(60)
                        for d, row in chart_df.iterrows():
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
                        
                    results.append(item)
            except Exception as e:
                print(f"Error fetching index {idx['symbol']}: {e}")
        return results

    indices_res = fetch_indices()

    print("處理篩選歷史與統計...")
    today_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Insert today's data
    for strat, records in [('tea', data['tea']), ('test', data['test']), ('moon', data['moon'])]:
        for rec in records:
            cursor.execute('''
                INSERT OR IGNORE INTO screened_history (date, symbol, name, screened_price, strategy)
                VALUES (?, ?, ?, ?, ?)
            ''', (today_str, rec['symbol'], rec['name'], rec['price'], strat))
            
    conn.commit()
    
    # Delete history older than 30 days
    thirty_days_ago = (datetime.utcnow() + timedelta(hours=8) - timedelta(days=30)).strftime("%Y-%m-%d")
    cursor.execute("DELETE FROM screened_history WHERE date < ?", (thirty_days_ago,))
    conn.commit()
    
    # Fetch all history to build statistics
    cursor.execute("SELECT date, symbol, name, screened_price, strategy FROM screened_history ORDER BY date DESC")
    history_records = cursor.fetchall()
    
    # Query current prices
    cursor.execute("SELECT symbol, close FROM daily_quotes WHERE date = (SELECT MAX(date) FROM daily_quotes)")
    latest_prices = {row[0]: row[1] for row in cursor.fetchall()}
    
    statistics = {'tea': [], 'test': [], 'moon': []}
    for row in history_records:
        r_date, r_symbol, r_name, r_price, r_strat = row
        current_price = latest_prices.get(r_symbol)
        
        perf = None
        if current_price is not None and r_price is not None and r_price > 0:
            perf = round(((current_price - r_price) / r_price) * 100, 2)
            
        if r_strat in statistics:
            statistics[r_strat].append({
                "date": r_date,
                "symbol": r_symbol,
                "name": r_name,
                "screened_price": round(r_price, 2) if r_price else None,
                "current_price": round(current_price, 2) if current_price else None,
                "performance": perf
            })
            
    conn.close()

    print("匯出資料至 JSON...")
    output = {
        "updated_at": (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
        "data": {
            "tea": sorted(data['tea'], key=lambda x: x['symbol']),
            "test": sorted(data['test'], key=lambda x: x['symbol']),
            "moon": sorted(data['moon'], key=lambda x: x['symbol']),
            "long_etf": long_etfs_res,
            "high_div": high_div_etfs_res,
            "indices": indices_res,
            "statistics": statistics
        }
    }
    
    def scrub_nans(obj):
        import math
        if isinstance(obj, dict):
            return {k: scrub_nans(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [scrub_nans(v) for v in obj]
        elif isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        return obj

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(scrub_nans(output), f, ensure_ascii=False, indent=4)
        
    print(f"分析完成！茶葉:{len(data['tea'])} 測試:{len(data['test'])} 止月:{len(data['moon'])}")
