import streamlit as st
import pandas as pd
import camelot
import re
import calendar
from datetime import datetime

def get_pdf_metadata(file_path, file_name):
    # PDF全体のテーブルを読み込み
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    full_df = pd.concat([t.df for t in tables], ignore_index=True)
    
    all_dates = []
    
    # 検索用パターン
    # T1/T2などのキー、日付(1-31)、曜日(月火水木金土日)をそれぞれ抽出
    key_pattern = re.compile(r'T[12]')
    date_pattern = re.compile(r'\b([12]?\d|3[01])\b')
    weekday_pattern = re.compile(r'[月火水木金土日]')
    
    # 全行を走査し、キーが検知されたらその後続行をブロックとして扱う
    is_in_block = False
    
    for _, row in full_df.iterrows():
        row_str = " ".join([str(v) for v in row]).replace('\n', ' ').strip()
        
        # 1. キー行(T1/T2)の検知
        if key_pattern.search(row_str):
            is_in_block = True
            continue
            
        # 2. ブロック内での処理
        if is_in_block:
            # 日付情報が含まれているか確認
            found_dates = date_pattern.findall(row_str)
            # 曜日情報が含まれているか確認
            found_weekday = weekday_pattern.search(row_str)
            
            # 日付があればリストに追加
            if found_dates:
                all_dates.extend([int(d) for d in found_dates])
                
            # 曜日情報がなく、かつ日付情報もない場合はブロック終了とみなす
            if not found_dates and not found_weekday:
                is_in_block = False
    
    # 3. 最大日付の算出
    max_date = max(all_dates) if all_dates else 0
    
    # 4. 最終曜日の算出（最大日付に対応する曜日をカレンダーから取得）
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month
    
    try:
        weekday_idx = calendar.weekday(year, month, max_date)
        last_weekday = ["月", "火", "水", "木", "金", "土", "日"][weekday_idx]
    except:
        last_weekday = "不明"
        
    return max_date, last_weekday
