import streamlit as st
import pdfplumber
import pandas as pd
import re
import calendar
from datetime import datetime

# 1. 抽出ロジック（デバッグ情報付き）
def extract_date_day_pairs(uploaded_file, key):
    uploaded_file.seek(0)
    all_extracted_data = [] # デバッグ用
    
    with pdfplumber.open(uploaded_file) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table_idx, table in enumerate(tables):
                df = pd.DataFrame(table).fillna('')
                all_extracted_data.append(df) # 読み取ったテーブルを保存
                
                table_str = " ".join([" ".join(row) for row in df.astype(str).values])
                if key not in table_str:
                    continue
                
                # キー発見後の日付行探索
                target_date_idx = -1
                for i in range(len(df)):
                    row_vals = df.iloc[i].values
                    digit_count = sum(1 for v in row_vals if re.search(r'^\d+$', str(v).strip()))
                    if digit_count >= 5:
                        target_date_idx = i
                        break
                
                if target_date_idx != -1:
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
                        return last_date, pairs[last_date], None, all_extracted_data
        return None, None, f"キー '{key}' と有効な日付データが見つかりません。", all_extracted_data

# 2. メインロジック
st.title("シフトカレンダー自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    y, m = 2026, 1
    expected_end_of_month = calendar.monthrange(y, m)[1]
    expected_day_of_week = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, expected_end_of_month)]

    last_date, last_day, error, debug_data = None, None, None, []
    
    # 検索実行
    for k in ["T1", "T2"]:
        last_date, last_day, error, debug_data = extract_date_day_pairs(uploaded_pdf, k)
        if error is None:
            break
    
    if error:
        st.error(error)
        st.subheader("【デバッグ情報】読み取れたテーブル内容")
        st.write("プログラムがPDFから読み取ったデータ構造です。")
        for i, df in enumerate(debug_data):
            st.write(f"テーブル {i+1}:")
            st.dataframe(df) # これでPDFの中身が数値データとして見えます
    else:
        if last_date != expected_end_of_month:
            st.error("日付の整合性がとれませんでした。")
            st.write(f"① ファイル内容からの抽出：A={last_date}日({last_day}曜日)")
            st.write(f"② 設定年月からの算出：B={expected_end_of_month}日({expected_day_of_week}曜日)")
            st.subheader("【デバッグ情報】読み取れたテーブル内容")
            for i, df in enumerate(debug_data):
                st.write(f"テーブル {i+1}:")
                st.dataframe(df) # これでPDFの中身が見えます
            st.stop()
        
        st.success(f"解析成功：{y}年{m}月 ({last_date}日 {last_day}曜日)")
