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
    """統一的 yfinance 下載入口（使用 Ticker.history 避免多執行緒共用狀態污染）"""
    try:
        df = yf.Ticker(symbol).history(period=period)
        if not df.empty and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
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
    cursor_check.execute('SELECT COUNT(DISTINCT date), MAX(date) FROM daily_quotes')
    existing_days, max_date_str = cursor_check.fetchone()
    conn_check.close()

    if existing_days < 120:
        days_needed = 150 - existing_days
        print(f"  資料庫只有 {existing_days} 天，需補充至 150 天...")
        init_database(days_needed)
    else:
        # 依據最新交易日差距天數自動補齊，避免隔數日未執行時漏抓中間交易日
        if max_date_str:
            gap_days = max(1, (datetime.now() - datetime.strptime(max_date_str, '%Y-%m-%d')).days + 1)
            init_database(min(gap_days, 30))
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
# 資料來源（依優先順序）：
#   1. FinMind TaiwanStockPrice          ：官方日線 (未調整 OHLCV，源自 TWSE)
#   2. TWSE MIS 即時報價 (mis.twse.com.tw)：當日收盤 (FinMind 盤後尚未更新時補上今天)
#   3. FinMind TaiwanStockDividendResult ：除息結果 (配息金額 + 官方除息前參考價)
#   4. FinMind TaiwanStockSplitPrice     ：股票分割 (例：0050 1拆4、0052 1拆7)
#   5. yfinance                          ：以上皆失敗時的備援 (已知會漏日、分割調整不一致)
# 可設定環境變數 FINMIND_TOKEN 提高 FinMind 呼叫額度。

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

ETF_FREQ_TIMES = {'月配息': 12, '季配息': 4, '半年配': 2, '年配息': 1}


def _finmind_get(dataset, data_id, start_date, retries=2):
    """呼叫 FinMind API，回傳 DataFrame（失敗回傳空 DataFrame）"""
    params = {'dataset': dataset, 'data_id': data_id, 'start_date': start_date}
    token = os.environ.get('FINMIND_TOKEN')
    if token:
        params['token'] = token
    for attempt in range(retries + 1):
        try:
            res = requests.get(FINMIND_API, params=params, timeout=20)
            data = res.json()
            if data.get('status') == 200:
                return pd.DataFrame(data.get('data', []))
            print(f"  FinMind {dataset} {data_id} 回應異常: {data.get('msg')}")
        except Exception as e:
            print(f"  FinMind {dataset} {data_id} 連線失敗 ({attempt + 1}): {e}")
    return pd.DataFrame()


def _twse_realtime_quotes(symbols):
    """TWSE MIS 即時/當日報價。回傳 {sym: {date, open, high, low, close, prev_close, volume}}"""
    out = {}
    try:
        ex_ch = '|'.join(f"tse_{s}.tw" for s in symbols)
        res = requests.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                           params={'ex_ch': ex_ch, 'json': 1, 'delay': 0}, timeout=15)
        for q in res.json().get('msgArray', []):
            def _num(k):
                try:
                    return float(q.get(k))
                except (TypeError, ValueError):
                    return None
            trade_z = None
            if isinstance(q.get('trade'), dict):
                try:
                    trade_z = float(q['trade'].get('z'))
                except (TypeError, ValueError):
                    trade_z = None
            close = _num('z') or _num('pz') or trade_z
            if close is None:
                continue
            out[q['c']] = {
                'date': pd.Timestamp(datetime.strptime(q['d'], '%Y%m%d')),
                'open': _num('o') or close, 'high': _num('h') or close,
                'low': _num('l') or close, 'close': close,
                'prev_close': _num('y'),
                'volume': (_num('v') or 0) * 1000,  # MIS 的 v 單位是「張」
            }
    except Exception as e:
        print(f"  TWSE MIS 即時報價取得失敗: {e}")
    return out


def _yf_etf_fallback(sym, start_date):
    """yfinance 備援：回傳與 FinMind 相同欄位格式的未調整日線"""
    try:
        df = yf.Ticker(f"{sym}.TW").history(start=start_date, auto_adjust=False)
        if df.empty:
            return pd.DataFrame()
        df = df.dropna(subset=['Close'])
        return pd.DataFrame({
            'open': df['Open'].values, 'high': df['High'].values, 'low': df['Low'].values,
            'close': df['Close'].values, 'volume': df['Volume'].values,
        }, index=pd.DatetimeIndex(df.index.tz_localize(None) if df.index.tz else df.index))
    except Exception:
        return pd.DataFrame()


def _infer_div_freq(div_dates):
    """依除息日間隔中位數推估配息頻率"""
    if len(div_dates) < 2:
        return None
    gaps = pd.Series(sorted(div_dates)).diff().dropna().dt.days.tail(4)
    g = float(gaps.median())
    if g <= 45:
        return '月配息'
    if g <= 135:
        return '季配息'
    if g <= 270:
        return '半年配'
    return '年配息'


def process_etfs():
    long_etf_symbols = ['0050', '006208', '00631L', '00981A', '0052', '00662', '009816']
    high_div_etf_symbols = ['0056', '00878', '00919', '00929']

    # 僅用於「設計上不配息」的 ETF；其餘頻率依實際除息紀錄自動推估
    freq_override = {'00631L': '不配息', '009816': '不配息', '00662': '不配息'}

    ch_names = {
        '0050': '元大台灣50', '006208': '富邦台50', '00631L': '元大台灣50正2',
        '00981A': '主動統一台股增長', '0052': '富邦科技', '00662': '富邦NASDAQ',
        '009816': '凱基台灣TOP50',
        '0056': '元大高股息', '00878': '國泰永續高股息',
        '00919': '群益台灣精選高息', '00929': '復華台灣科技優息'
    }

    all_symbols = long_etf_symbols + high_div_etf_symbols
    today = datetime.utcnow() + timedelta(hours=8)
    start_date = f"{today.year - 2}-12-01"   # 涵蓋「前年底」以計算去年績效
    realtime = _twse_realtime_quotes(all_symbols)

    def _process_single_etf(sym):
        try:
            name = ch_names.get(sym, sym)
            source = 'FinMind'

            # ---- 1. 日線 (官方未調整價) ----
            px = _finmind_get('TaiwanStockPrice', sym, start_date)
            if not px.empty:
                px = px[px['close'] > 0]
                df = pd.DataFrame({
                    'open': px['open'].astype(float).values, 'high': px['max'].astype(float).values,
                    'low': px['min'].astype(float).values, 'close': px['close'].astype(float).values,
                    'volume': px['Trading_Volume'].astype(float).values,
                }, index=pd.to_datetime(px['date']))
            else:
                df = _yf_etf_fallback(sym, start_date)
                source = 'yfinance(備援)'
            if df.empty:
                return None
            df = df.sort_index()
            df = df[~df.index.duplicated(keep='last')]

            # 補上「今天」：FinMind 盤後約傍晚才更新，先用 TWSE MIS 當日報價
            rt = realtime.get(sym)
            if rt and rt['date'] > df.index[-1]:
                if rt['prev_close'] and abs(rt['prev_close'] - df['close'].iloc[-1]) > 0.011:
                    print(f"  ⚠️ {sym} 昨收不一致：TWSE={rt['prev_close']} / {source}={df['close'].iloc[-1]}")
                df.loc[rt['date']] = [rt['open'], rt['high'], rt['low'], rt['close'], rt['volume']]
                source += '+TWSE即時'

            current_price = float(df['close'].iloc[-1])
            prev_price = float(df['close'].iloc[-2]) if len(df) > 1 else current_price
            change = current_price - prev_price
            change_percent = (change / prev_price) * 100 if prev_price else 0
            volume = int(df['volume'].iloc[-1] / 1000)
            recent_low = float(df['low'].tail(5).min())
            curr_date = df.index[-1]
            date_str = curr_date.strftime('%Y-%m-%d')
            curr_year, last_year = curr_date.year, curr_date.year - 1

            # ---- 2. 除息 / 分割事件 ----
            div_df = _finmind_get('TaiwanStockDividendResult', sym, start_date)
            split_df = _finmind_get('TaiwanStockSplitPrice', sym, start_date)

            divs = []   # {date, cash, before}
            if not div_df.empty:
                for _, r in div_df.iterrows():
                    cash = float(r.get('stock_and_cache_dividend') or 0)
                    before = float(r.get('before_price') or 0)
                    if cash > 0 and before > 0:
                        divs.append({'date': pd.Timestamp(r['date']), 'cash': cash,
                                     'before': before, 'after': float(r.get('after_price') or before - cash)})
            elif source.startswith('yfinance'):
                # 備援：yfinance 配息 + 除息前一日收盤
                try:
                    for d, v in yf.Ticker(f"{sym}.TW").dividends.items():
                        d = pd.Timestamp(d.date())
                        prev = df[df.index < d]
                        if v > 0 and not prev.empty:
                            b = float(prev['close'].iloc[-1])
                            divs.append({'date': d, 'cash': float(v), 'before': b, 'after': b - float(v)})
                except Exception:
                    pass
            divs.sort(key=lambda x: x['date'])

            splits = []  # {date, ratio(before/after)}
            if not split_df.empty:
                for _, r in split_df.iterrows():
                    b, a = float(r.get('before_price') or 0), float(r.get('after_price') or 0)
                    if b > 0 and a > 0:
                        splits.append({'date': pd.Timestamp(r['date']), 'ratio': b / a,
                                       'before': b, 'after': a})

            # ---- 3. 單純股價累計漲跌幅 (不含息，僅還原股票分割如 0050 一拆四、0052 一拆七) ----
            adj = df['close'].copy()
            for ev in splits:
                adj[adj.index < ev['date']] *= ev['after'] / ev['before']

            listing_date = df.index[0]
            listing_price_adj = float(df['open'].iloc[0]) * float(adj.iloc[0] / df['close'].iloc[0])
            fetched_from_start = listing_date > pd.Timestamp(start_date) + pd.Timedelta(days=10)

            def _year_end(y):
                s = adj[adj.index.year == y]
                return float(s.iloc[-1]) if not s.empty else None

            def _year_end_raw(y):
                s = df['close'][df.index.year == y]
                return (s.index[-1].strftime('%m/%d'), float(s.iloc[-1])) if not s.empty else (None, None)

            end_last = _year_end(last_year)
            end_before = _year_end(last_year - 1)
            end_last_md, end_last_raw = _year_end_raw(last_year)
            end_before_md, end_before_raw = _year_end_raw(last_year - 1)

            # 今年迄今報酬
            ytd_note = None
            if end_last:
                ytd = (float(adj.iloc[-1]) / end_last - 1) * 100
            elif fetched_from_start:
                ytd = (float(adj.iloc[-1]) / listing_price_adj - 1) * 100
                ytd_note = '上市起'
            else:
                ytd = None

            # 去年報酬
            ly_note = None
            if end_last and end_before:
                last_year_perf = (end_last / end_before - 1) * 100
            elif end_last and fetched_from_start and listing_date.year == last_year:
                last_year_perf = (end_last / listing_price_adj - 1) * 100
                ly_note = '上市起'
            else:
                last_year_perf = None

            # ---- 4. 殖利率 ----
            def _split_factor_after(d):
                """d 之後發生的分割倍數乘積 (把舊配息換算成現在的每單位金額)"""
                f = 1.0
                for s in splits:
                    if s['date'] > d:
                        f *= s['ratio']
                return f

            ytd_divs = [d for d in divs if d['date'].year == curr_year]
            ly_divs = [d for d in divs if d['date'].year == last_year]
            ttm_divs = [d for d in divs if d['date'] > curr_date - pd.Timedelta(days=365)]

            ytd_yield = sum(d['cash'] / d['before'] for d in ytd_divs) * 100
            last_year_yield = sum(d['cash'] / d['before'] for d in ly_divs) * 100
            ttm_cash = sum(d['cash'] / _split_factor_after(d['date']) for d in ttm_divs)
            ttm_yield = ttm_cash / current_price * 100 if current_price else 0

            freq_str = freq_override.get(sym) or _infer_div_freq([d['date'] for d in divs])
            if not freq_str:
                freq_str = '尚未配息' if not divs else '未知'
            n_times = ETF_FREQ_TIMES.get(freq_str, 0)

            latest = divs[-1] if divs else None
            if latest and n_times:
                annualized_yield = round(latest['cash'] / latest['before'] * n_times * 100, 2)
            else:
                annualized_yield = None

            # ---- 5. 去年投入 100 萬台幣之總損益 (含價差 + 現金股息 + 股票分割) ----
            ly_1m_profit = None
            ly_1m_price_profit = None
            ly_1m_div_profit = None
            if end_last_raw is not None:
                p_start_ly = end_before_raw if end_before_raw is not None else (
                    float(df['open'][df.index.year == last_year].iloc[0])
                    if (fetched_from_start and listing_date.year == last_year) else None
                )
                if p_start_ly and p_start_ly > 0:
                    shares_1m = 1_000_000.0 / p_start_ly
                    ly_events = []
                    for s in splits:
                        if s['date'].year == last_year:
                            ly_events.append(('split', s['date'], s['ratio']))
                    for d in ly_divs:
                        ly_events.append(('div', d['date'], d['cash']))
                    ly_events.sort(key=lambda x: x[1])
                    cash_received = 0.0
                    for etype, _, val in ly_events:
                        if etype == 'split':
                            shares_1m *= val
                        elif etype == 'div':
                            cash_received += shares_1m * val
                    end_stock_val = shares_1m * end_last_raw
                    ly_1m_price_profit = round(end_stock_val - 1_000_000.0)
                    ly_1m_div_profit = round(cash_received)
                    ly_1m_profit = round((end_stock_val + cash_received) - 1_000_000.0)

            etf_data = {
                "symbol": sym, "name": name,
                "price": round(current_price, 2), "change": round(change, 2),
                "change_percent": round(change_percent, 2), "volume": volume,
                "suggested_buy_price": round(recent_low, 2), "date": date_str,
                "ytd": round(ytd, 2) if ytd is not None else None,
                "ytd_note": ytd_note,
                "last_year_perf": round(last_year_perf, 2) if last_year_perf is not None else None,
                "last_year_note": ly_note,
                "last_year_close": round(end_last_raw, 2) if end_last_raw is not None else None,
                "last_year_close_adj": round(end_last, 2) if end_last is not None else None,
                "last_year_end_md": end_last_md,
                "before_year_close": round(end_before_raw, 2) if end_before_raw is not None else None,
                "before_year_close_adj": round(end_before, 2) if end_before is not None else None,
                "last_year_1m_profit": ly_1m_profit,
                "last_year_1m_price_profit": ly_1m_price_profit,
                "last_year_1m_div_profit": ly_1m_div_profit,
                "listing_date": listing_date.strftime('%Y-%m-%d') if fetched_from_start else None,
                "div_freq": freq_str,
                "latest_div": round(latest['cash'], 4) if latest else None,
                "latest_ex_date": latest['date'].strftime('%Y-%m-%d') if latest else None,
                "annualized_yield": annualized_yield,
                "ttm_cash": round(ttm_cash, 4),
                "ttm_yield": round(ttm_yield, 2) if divs else None,
                "ytd_yield": round(ytd_yield, 2) if ytd_divs else None,
                "last_year_yield": round(last_year_yield, 2) if ly_divs else None,
                "ytd_div_count": len(ytd_divs),
                "last_year_div_count": len(ly_divs),
                "splits": [
                    {
                        "date": s['date'].strftime('%Y-%m-%d'),
                        "ratio": int(round(s['ratio'])),
                        "before": round(s['before'], 2),
                        "after": round(s['after'], 2),
                    }
                    for s in splits if s['date'].year >= last_year
                ],
                "data_source": source,
            }
            return (sym, etf_data)
        except Exception as e:
            print(f"Error processing ETF {sym}: {e}")
            return None

    long_etfs = []
    high_div_etfs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
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

def _fetch_sox_constituent_volumes():
    """Yahoo Finance 與 Nasdaq 官方對 ^SOX 指數本身不提供總成交量 (回傳 0)。
    此處抓取費城半導體 30 檔成分股每日成交股數加總（若失敗則以 SOXX ETF 成交量備援）。"""
    sox_tickers = [
        'NVDA', 'TSM', 'AVGO', 'AMD', 'QCOM', 'TXN', 'MU', 'AMAT', 'INTC', 'LRCX',
        'ADI', 'KLAC', 'ASML', 'MRVL', 'NXPI', 'MPWR', 'ON', 'MCHP', 'TER', 'ENTG',
        'STM', 'SWKS', 'GFS', 'ONTO', 'LSCC', 'QRVO', 'AMKR', 'MTSI', 'COHR', 'ARM'
    ]
    vol_map = {}
    try:
        df_sox = yf.download(sox_tickers, period='6mo', progress=False, threads=True)
        if not df_sox.empty and 'Volume' in df_sox:
            vol_series = df_sox['Volume'].sum(axis=1)
            for d, val in vol_series.items():
                if pd.notna(val) and val > 0:
                    vol_map[d.strftime('%Y-%m-%d')] = int(val)
    except Exception as e:
        print(f"Warning: SOX constituent volume fetch error: {e}")

    if not vol_map:
        try:
            df_soxx = _download_yf('SOXX', period='6mo')
            for d, row in df_soxx.iterrows():
                vol_map[d.strftime('%Y-%m-%d')] = int(row['Volume'])
        except Exception:
            pass
    return vol_map


def _fetch_taiex_finmind():
    """從 FinMind (TaiwanStockPrice: TAIEX) 取得台股加權指數 K 線與台幣成交金額 (單位: 億元)"""
    start_str = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
    df = _finmind_get("TaiwanStockPrice", "TAIEX", start_str)
    if df is None or df.empty:
        return None
    df = df.sort_values('date').reset_index(drop=True)
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['open'] = pd.to_numeric(df['open'], errors='coerce')
    df['max'] = pd.to_numeric(df['max'], errors='coerce')
    df['min'] = pd.to_numeric(df['min'], errors='coerce')
    df['Trading_money'] = pd.to_numeric(df['Trading_money'], errors='coerce').fillna(0)
    df = df.dropna(subset=['close'])
    if df.empty:
        return None

    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()

    current = float(df['close'].iloc[-1])
    prev = float(df['close'].iloc[-2]) if len(df) > 1 else current
    change = current - prev
    change_percent = (change / prev) * 100 if prev else 0

    history_data = []
    for _, row in df.tail(60).iterrows():
        # 台股加權指數成交量改以「台幣成交金額（億元）」呈現，符合台股看盤習慣
        money_100m = round(float(row['Trading_money']) / 1e8, 2)
        history_data.append({
            "date": str(row['date']),
            "open": round(float(row['open']), 2),
            "close": round(float(row['close']), 2),
            "low": round(float(row['min']), 2),
            "high": round(float(row['max']), 2),
            "volume": money_100m,
            "ma5": round(float(row['ma5']), 2) if not pd.isna(row['ma5']) else None,
            "ma20": round(float(row['ma20']), 2) if not pd.isna(row['ma20']) else None
        })

    return {
        "symbol": "^TWII",
        "name": "台股加權指數",
        "price": round(current, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume_unit": "億元",
        "history": history_data
    }


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

    sox_vol_map = _fetch_sox_constituent_volumes()

    def _fetch_single_index(idx):
        try:
            if idx['symbol'] == '^TWII':
                taiex_item = _fetch_taiex_finmind()
                if taiex_item:
                    return taiex_item

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
                "change_percent": round(change_percent, 2),
                "volume_unit": "股"
            }

            if idx['symbol'] in chart_symbols:
                df['ma5'] = df['Close'].rolling(window=5).mean()
                df['ma20'] = df['Close'].rolling(window=20).mean()
                history_data = []
                for d, row in df.tail(60).iterrows():
                    date_str = d.strftime('%Y-%m-%d')
                    vol_val = int(row['Volume']) if pd.notna(row['Volume']) else 0
                    if idx['symbol'] == '^SOX' and vol_val == 0:
                        vol_val = sox_vol_map.get(date_str, 0)
                    history_data.append({
                        "date": date_str,
                        "open": round(float(row['Open']), 2),
                        "close": round(float(row['Close']), 2),
                        "low": round(float(row['Low']), 2),
                        "high": round(float(row['High']), 2),
                        "volume": vol_val,
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

    clean_output = scrub_nans(output)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(clean_output, f, ensure_ascii=False, indent=4)

    # 同步輸出 data.js，支援直接雙擊 index.html (file://) 免伺服器讀取最新本地資料
    js_output_file = os.path.splitext(output_file)[0] + '.js'
    with open(js_output_file, 'w', encoding='utf-8') as f:
        f.write('window.__LOCAL_STOCK_DATA__ = ')
        json.dump(clean_output, f, ensure_ascii=False)
        f.write(';\n')

    print(f"分析完成！茶葉:{len(data['tea'])} 止月:{len(data['moon'])} 50大:{len(data['fifty'])}")
