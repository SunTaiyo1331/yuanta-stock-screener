import sqlite3
import requests
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import re

DB_PATH = 'market_data.db'

def create_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_quotes (
            date TEXT,
            symbol TEXT,
            name TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (date, symbol)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS screened_history (
            date TEXT,
            symbol TEXT,
            name TEXT,
            screened_price REAL,
            strategy TEXT,
            PRIMARY KEY (date, symbol, strategy)
        )
    ''')
    conn.commit()
    conn.close()

def clean_number(text):
    if not isinstance(text, str):
        return text
    text = text.replace(',', '').strip()
    if text == '--' or text == '---' or text == '':
        return None
    try:
        return float(text)
    except:
        return None

def fetch_twse(date_str):
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALLBUT0999"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        if data.get('stat') != 'OK':
            return []
            
        # Table 8 or 9 usually contains the price data. Look for fields with '證券代號'
        records = []
        for table in data.get('tables', []):
            if 'fields' in table and len(table['fields']) > 8 and table['fields'][0] == '證券代號':
                for row in table['data']:
                    symbol = row[0].strip()
                    # Filter out non-ordinary stocks if desired, or just keep them
                    # if not re.match(r'^\d{4}$', symbol): continue # Only 4-digit symbols
                    name = row[1].strip()
                    vol = clean_number(row[2])
                    open_p = clean_number(row[5])
                    high_p = clean_number(row[6])
                    low_p = clean_number(row[7])
                    close_p = clean_number(row[8])
                    
                    if close_p is not None:
                        records.append((symbol, name, open_p, high_p, low_p, close_p, vol))
                break
        return records
    except Exception as e:
        print(f"TWSE error for {date_str}: {e}")
        return []

def fetch_tpex(date_str):
    # TPEx uses ROC year
    roc_year = int(date_str[:4]) - 1911
    tpex_date = f"{roc_year}/{date_str[4:6]}/{date_str[6:8]}"
    url = f"https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=json&d={tpex_date}&se=AL"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        
        records = []
        for table in data.get('tables', []):
            if len(table.get('data', [])) > 0:
                for row in table['data']:
                    if len(row) < 8: continue
                    symbol = row[0].strip()
                    name = row[1].strip()
                    close_p = clean_number(row[2])
                    open_p = clean_number(row[4])
                    high_p = clean_number(row[5])
                    low_p = clean_number(row[6])
                    vol = clean_number(row[7])
                    
                    if close_p is not None:
                        records.append((symbol, name, open_p, high_p, low_p, close_p, vol))
                break
        return records
    except Exception as e:
        print(f"TPEx error for {date_str}: {e}")
        return []

def init_database(days_needed=60):
    create_table()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    current_date = datetime.now()
    days_collected = 0
    
    print(f"開始下載過去 {days_needed} 個交易日的大表資料...")
    
    while days_collected < days_needed:
        # Skip weekends
        if current_date.weekday() >= 5:
            current_date -= timedelta(days=1)
            continue
            
        date_str = current_date.strftime('%Y%m%d')
        db_date_str = current_date.strftime('%Y-%m-%d')
        
        # Check if already in DB
        cursor.execute("SELECT COUNT(*) FROM daily_quotes WHERE date = ?", (db_date_str,))
        if cursor.fetchone()[0] > 0:
            print(f"{db_date_str} 資料已存在，跳過。")
            days_collected += 1
            current_date -= timedelta(days=1)
            continue
            
        print(f"下載 {db_date_str} 資料...")
        twse_data = fetch_twse(date_str)
        tpex_data = fetch_tpex(date_str)
        
        if len(twse_data) == 0 and len(tpex_data) == 0:
            print(f"  {db_date_str} 無資料 (可能是假日)，繼續往前找...")
        else:
            # Insert into DB
            insert_data = []
            for r in twse_data:
                # date, symbol, name, open, high, low, close, volume
                insert_data.append((db_date_str, f"{r[0]}.TW", r[1], r[2], r[3], r[4], r[5], r[6]))
            for r in tpex_data:
                insert_data.append((db_date_str, f"{r[0]}.TWO", r[1], r[2], r[3], r[4], r[5], r[6]))
                
            cursor.executemany('''
                INSERT OR IGNORE INTO daily_quotes 
                (date, symbol, name, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', insert_data)
            conn.commit()
            
            print(f"  {db_date_str}: 成功寫入上市 {len(twse_data)} 檔，上櫃 {len(tpex_data)} 檔。")
            days_collected += 1
            
        current_date -= timedelta(days=1)
        time.sleep(3) # 避免被證交所封鎖
        
    conn.close()
    print("資料庫初始化完成！")

if __name__ == '__main__':
    # 測試時先抓 60 天
    init_database(60)
