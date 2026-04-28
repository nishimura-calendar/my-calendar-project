import streamlit as st
import pandas as pd
import re
import unicodedata

# [中略: 認証サービスなどの既存コード]

def convert_float_to_time(val):
    """数値(6.25)を時間表記(6:15)に変換"""
    try:
        if val == "" or val == "なし": return ""
        f_val = float(val)
        hours = int(f_val)
        minutes = int(round((f_val - hours) * 60))
        return f"{hours}:{minutes:02d}"
    except (ValueError, TypeError):
        return val

def extract_col_range(loc_df):
    """
    各勤務地の1行目を走査し、D列(3)以降で
    『数値が最初に出現する列』から『数値が最後に出現する列』までを
    動的に特定して時間列として抽出する。
    """
    if loc_df.empty:
        return loc_df

    # 1行目（時間軸の定義行）をリスト化
    header_row = loc_df.iloc[0].tolist()
    
    # 数値判定用の正規表現（整数・小数を許容）
    num_pattern = re.compile(r'^-?\d+(\.\d+)?$')
    
    # D列(3)以降で数値が入っているインデックスをすべて抽出
    num_indices = [
        i for i, val in enumerate(header_row) 
        if i >= 3 and num_pattern.match(str(val).strip())
    ]
    
    if not num_indices:
        # 数値が見つからない場合は、基本のA-C列(0-2)のみを返す
        return loc_df.iloc[:, 0:3]
    
    # 最初の数値列と、最後の数値列を特定
    col_start = min(num_indices)
    col_end = max(num_indices) + 1  # スライス用に+1
    
    # A-C列(0:3) と、動的に特定した時間軸の全範囲を結合
    res_df = pd.concat([loc_df.iloc[:, 0:3], loc_df.iloc[:, col_start:col_end]], axis=1)
    
    # 表示用に1行目の数値を時間表記「H:MM」へ一括変換
    if not res_df.empty:
        # loc[0]だと元のdfに影響する場合があるため明示的にリスト取得
        current_header = res_df.iloc[0].tolist()
        new_header = []
        for i, val in enumerate(current_header):
            if i >= 3: # 時間軸列（D列以降）のみ変換
                new_header.append(convert_float_to_time(val))
            else:
                new_header.append(val)
        
        # 変換したリストで1行目を更新
        res_df.iloc[0] = new_header
        
    return res_df
