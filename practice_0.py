import streamlit as st
import pandas as pd
import re
import unicodedata

# --- [中略: get_unified_services, normalize_text 等は既存のまま] ---

def convert_float_to_time(val):
    """数値(6.25)を時間表記(6:15)に変換する"""
    try:
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours}:{minutes:02d}"
    except:
        return val

def extract_col_range(loc_df):
    """
    D列(インデックス3)以降で、最初の数値から最後の数値までの列範囲を
    拠点ごとに動的に特定して抽出する
    """
    if loc_df.empty:
        return loc_df

    # 1行目（時間軸候補）をリスト化
    header_row = loc_df.iloc[0].tolist()
    
    # 数値（整数、小数、負数）にマッチする正規表現
    num_pattern = re.compile(r'^-?\d+(\.\d+)?$')
    
    # D列(3)以降で数値が入っているインデックスを探す
    num_indices = [
        i for i, val in enumerate(header_row) 
        if i >= 3 and num_pattern.match(str(val).strip())
    ]
    
    if not num_indices:
        # 数値が見つからない場合は、最低限A-C列のみ返す
        return loc_df.iloc[:, 0:3]
    
    col_start = min(num_indices)
    col_end = max(num_indices) + 1  # 最後の数値列まで含める
    
    # A-C列(0:3) と 特定した時間軸列を結合
    res_df = pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)
    
    # 【重要】抽出した時間軸を時間表記に変換 (6.25 -> 6:15)
    if not res_df.empty:
        current_header = res_df.iloc[0].tolist()
        # 3列目以降（結合した時間列部分）を変換
        new_header = [convert_float_to_time(h) if i >= 3 else h for i, h in enumerate(current_header)]
        res_df.iloc[0] = new_header
        
    return res_df

# --- [中略: time_schedule_from_drive は既存のまま] ---
