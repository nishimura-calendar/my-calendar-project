import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os

# --- (認証系関数は変更なし) ---

def convert_to_time_string(val):
    """Excelシリアル値等を時刻文字列(HH:MM)に変換"""
    if isinstance(val, (int, float)):
        total_minutes = int(round(val * 24 * 60))
        hours = (total_minutes // 60) % 24
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"
    return str(val)

def time_schedule_from_drive(sheets_service, file_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    sheets = spreadsheet.get('sheets', [])
    location_data_dic = {}

    for s in sheets:
        title = s.get("properties", {}).get("title")
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
        vals = result.get('values', [])
        if not vals: continue

        df = pd.DataFrame(vals).fillna('')
        
        # 行方向の走査
        current_key = None
        start_row = 0
        
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_key is not None:
                    # 前の拠点の範囲を確定。その拠点の最初の行（勤務地行）を基準に列判定
                    location_data_dic[normalize_text(current_key)] = extract_by_key_row(df.iloc[start_row:i, :])
                current_key = val_a
                start_row = i
        
        # 最後の拠点
        if current_key is not None:
            location_data_dic[normalize_text(current_key)] = extract_by_key_row(df.iloc[start_row:, :])
                
    return location_data_dic

def extract_by_key_row(loc_df):
    """
    勤務地行(loc_dfの0行目)を基準に時間列の範囲を特定し、A-C列と結合する
    """
    # 勤務地行（拠点の1行目）を取得
    key_row = loc_df.iloc[0, :].tolist()
    
    col_start = 3 # デフォルトD列
    col_end = len(key_row)
    
    # 1. 勤務地行において、最初に数値(時間)が現れる列を探す
    for c in range(3, len(key_row)):
        val = key_row[c]
        # 数値、または数値形式の文字列をチェック
        if re.match(r'^-?\d+(\.\d+)?$', str(val)) and str(val).strip() != "":
            col_start = c
            break
            
    # 2. その後、数値が途切れ、最初に文字列が現れる列を探す[cite: 8]
    for c in range(col_start, len(key_row)):
        val = str(key_row[c]).strip()
        if val != "" and not re.match(r'^-?\d+(\.\d+)?$', val):
            col_end = c
            break
            
    # A-C列 (0:3) と 特定した時間範囲を抽出[cite: 8]
    base_info = loc_df.iloc[:, 0:3]
    time_data = loc_df.iloc[:, col_start:col_end].copy()
    
    # 時間データをHH:MMに一括変換[cite: 8]
    for col in time_data.columns:
        time_data[col] = time_data[col].apply(convert_to_time_string)
            
    return pd.concat([base_info, time_data], axis=1)
