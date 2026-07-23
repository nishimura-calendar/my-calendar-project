import streamlit as st
import camelot
import pandas as pd
import re
import tempfile
import os
import calendar
from datetime import datetime

# 1. 抽出ロジック（型エラー対策・Key基準の安定抽出版）
def extract_date_day_pairs(df, key):
    if df is None or df.empty:
        return None, None, "テーブルデータが空です。"
    
    df = df.fillna('') # 空セルのエラー対策

    # Key行の探索
    key_row_idx = -1
    for i in range(len(df)):
        row_values = df.iloc[i].values
        row_str = " ".join([str(v) for v in row_values])
        if key in row_str:
            key_row_idx = i
            break
            
    if key_row_idx == -1:
        return None, None, f"キー '{key}' が見つかりません。"

    # 日付行の探索（Keyの周辺で行う）
    target_date_idx = -1
    for i in [key_row_idx - 1, key_row_idx, key_row_idx + 1]:
        if 0 <= i < len(df):
            row_vals = df.iloc[i].values
            digit_count = sum(1 for v in row_vals if re.search(r'^\d+$', str(v).strip()))
            if digit_count >= 5: # 日付行の判定基準
                target_date_idx = i
                break
    
    if target_date_idx == -1:
        return None, None, f"キー '{key}' 付近に日付データが見つかりません。"

    # 抽出処理
    date_row = df.iloc[target_date_idx].values
    day_row = df.iloc[target_date_idx + 1].values if target_date_idx + 1 < len(df) else None
    
    pairs = {}
    for col in range(len(date_row)):
        d_val = str(date_row[col]).strip()
        day_val = str(day_row[col]).strip() if day_row is not None else ""
        
        d_digit = re.sub(r'\D', '', d_val)
        day = ""
        for char in day_val:
            if char in "日月火水木金土":
                day = char
                break
        
        if d_digit.isdigit() and day != "":
            pairs[int(d_digit)] = day
            
    if pairs:
        last_date = max(pairs.keys())
        return last_date, pairs[last_date], None
        
    return None, None, "日付と曜日のペアが抽出できませんでした。"

# 2. UI表示とメインロジック
st.title("シフトカレンダー自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    # PDFの年月設定（必要に応じて自動取得や入力フォームに変更してください）
    y, m = 2026, 1
    expected_end_of_month = calendar.monthrange(y, m)[1]
    expected_day_of_week = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, expected_end_of_month)]

    # PDFの解析（camelot等を使用）
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_pdf.read())
    tfile.close()
    
    tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
    df = tables[0].df # 最初の表を使用（必要に応じてループ処理に変更）
    
    k = "T1" # 検索キー
    last_date, last_day, error = extract_date_day_pairs(df, k)
    
    if error:
        st.error(error)
    else:
        # ここが整合性チェックと停止ロジック
        if last_date != expected_end_of_month:
            st.error("日付の整合性がとれませんでした。")
            st.write(f"① ファイル内容からの抽出：A={last_date}日({last_day}曜日)")
            st.write(f"② 設定年月からの算出：B={expected_end_of_month}日({expected_day_of_week}曜日)")
            
            st.subheader("アップロードされたPDFファイル")
            st.write(uploaded_pdf)
            st.stop() # ここで停止
        
        # 正常な場合の処理
        st.success(f"解析成功：{y}年{m}月 ({last_date}日 {last_day}曜日)")
        # ...以降のプログラム...
