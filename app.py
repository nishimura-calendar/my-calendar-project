import streamlit as st
import pdfplumber
import pandas as pd
import re
import calendar
from datetime import datetime

# 1. 抽出ロジック（pdfplumber専用版・camelot不使用）
def extract_date_day_pairs(uploaded_file, key):
    # pdfplumberでアップロードされたファイルを直接開く
    with pdfplumber.open(uploaded_file) as pdf:
        # 1ページ目を解析
        first_page = pdf.pages[0]
        tables = first_page.extract_tables()
        if not tables:
            return None, None, "表が見つかりませんでした。"
            
        df = pd.DataFrame(tables[0])
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
                # 数字が5個以上並んでいる行を日付行とみなす
                digit_count = sum(1 for v in row_vals if re.search(r'^\d+$', str(v).strip()))
                if digit_count >= 5:
                    target_date_idx = i
                    break
        
        if target_date_idx == -1:
            return None, None, f"キー '{key}' 付近に日付データが見つかりません。"

        # 抽出処理
        date_row = df.iloc[target_date_idx].values
        # 曜日行は日付行のすぐ下と想定
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
    # 2026年1月固定の設定
    y, m = 2026, 1
    expected_end_of_month = calendar.monthrange(y, m)[1]
    # 曜日を算出
    days = ["月", "火", "水", "木", "金", "土", "日"]
    expected_day_of_week = days[calendar.weekday(y, m, expected_end_of_month)]

    k = "T1" # 検索キー
    last_date, last_day, error = extract_date_day_pairs(uploaded_pdf, k)
    
    if error:
        st.error(error)
    else:
        # 整合性チェックと停止ロジック
        if last_date != expected_end_of_month:
            st.error("日付の整合性がとれませんでした。")
            
            # ご指定の形式で表示
            st.write(f"① ファイル内容からの抽出：A={last_date}日({last_day}曜日)")
            st.write(f"② 設定年月からの算出：B={expected_end_of_month}日({expected_day_of_week}曜日)")
            
            st.subheader("アップロードされたPDFファイル")
            st.write(uploaded_pdf.name)
            
            # 停止
            st.stop() 
        
        # 正常な場合の処理
        st.success(f"解析成功：{y}年{m}月 ({last_date}日 {last_day}曜日)")
