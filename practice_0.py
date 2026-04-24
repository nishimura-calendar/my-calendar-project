import pandas as pd
import camelot
import re
import unicodedata
import streamlit as st

def get_actual_info(df, sheet_id):
    """PDFの中から末日と勤務地を『検索』して特定する"""
    # 1. 末日の特定 (0行目から最大数字を探す)
    all_text_row0 = "".join(df.iloc[0, :].astype(str))
    days = re.findall(r'\d+', all_text_row0)
    actual_last_day = max([int(d) for d in days]) if days else 0
    
    # 2. 勤務地の特定 (時程表マスターの名前が0列目にあるか)
    # 本来はスプレッドシートから取得するが、一旦「T2」を優先検索
    detected_loc = "不明"
    search_col = df.iloc[:, 0].astype(str)
    if search_col.str.contains("T2").any():
        detected_loc = "T2"
    
    return actual_last_day, detected_loc

def rebuild_shift_data(df, sheet_id, target_staff, location):
    """時程表とPDFをガチャンと合体させる"""
    # 時程表の取得
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    try:
        time_master = pd.read_csv(url)
    except:
        return None

    # 本人行の特定
    clean_target = re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', target_staff)).lower()
    search_col = df.iloc[:, 0].astype(str).apply(lambda x: re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', x)).lower())
    
    indices = df.index[search_col == clean_target].tolist()
    if not indices:
        return None
    
    target_idx = indices[0]
    # 本人シフト（2行分、0列目以外）を抽出
    my_shift = df.iloc[target_idx:target_idx+2, 1:].copy()
    
    return {
        "my_shift": my_shift,
        "time_master": time_master
    }
