import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def analyze_pdf_full(pdf_stream, master_keys):
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, pd.DataFrame([{"エラー": "表未検出"}])
        raw_df = tables[0].df

        # 1. [0,0]から拠点(location)を特定し、[1,0]の値とする
        raw_0_0 = str(raw_df.iloc[0, 0])
        location = "T1" # デフォルト
        for k in master_keys:
            if k in normalize_text(raw_0_0):
                location = k
                break
        
        # 2. [0,0]の文字列から日付と曜日を分離抽出
        # 日付: [0,0]から location と 曜日 を除いたもの
        # 曜日: [0,0]から location と 日付 を除いたもの
        all_text = raw_0_0.replace('\n', ' ')
        
        # 数字(日付)と曜日文字をすべて抽出
        found_dates = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', all_text)
        found_days = re.findall(r'[月火水木金土日]', all_text)

        # 3. 再構成
        final_rows = []
        # 行0: [日付タイトル] + 抽出した日付リスト
        final_rows.append(["日付"] + found_dates)
        # 行1: [拠点名] + 抽出した曜日リスト
        final_rows.append([location] + found_days)
        
        max_name_len = len(location)
        # 2行目以降: 氏名と資格を交互に配置[cite: 12]
        for i in range(2, len(raw_df)):
            cell_0 = str(raw_df.iloc[i, 0]).strip()
            if not cell_0 or "nan" in cell_0.lower(): continue
            
            parts = cell_0.split('\n')
            name = parts[0]
            license = parts[1] if len(parts) > 1 else ""
            
            shift_data = raw_df.iloc[i, 1:].tolist()
            # 氏名行
            final_rows.append([name] + shift_data)
            # 資格行 (氏名の直下)
            final_rows.append([license] + [""] * len(shift_data))
            
            max_name_len = max(max_name_len, len(name))

        final_df = pd.DataFrame(final_rows)
        l = math.ceil(max_name_len)
        
        return {"df": final_df, "location": location, "l": l}, pd.DataFrame([{"状態": "定義通り分解完了"}])
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
