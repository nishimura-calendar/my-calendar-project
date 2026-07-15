import streamlit as st
import pandas as pd
import camelot
import re
import calendar
import io

# --- [1]．時程表読込 ---
def process_data(df):
    location_data = {}
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0]).strip()
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else df.index[-1] + 1
        schedule = df.iloc[start_idx:end_idx].copy()
        location_data[key] = schedule
    return location_data

# --- [2]〈1〉．pdfシフト表ファイル読込 ---
def process_pdf_shift(uploaded_file, data_dict):
    # (1) camelotを使用して読込
    tables = camelot.read_pdf(uploaded_file, flavor='lattice', pages='all')
    df = tables[0].df

    # (2) 第1関門
    found_key = None
    key_row_idx = -1
    for idx, row in df.iterrows():
        cell_val = str(row[0])
        clean_cell = re.sub(r'[\s ]', '', cell_val)
        for key in data_dict.keys():
            if re.sub(r'[\s ]', '', key) in clean_cell:
                found_key = key
                key_row_idx = idx
                break
        if found_key: break

    if not found_key:
        st.error(f"「{found_key}」が見当りません。シフト表ではないようです。ファイルを確認して下さい。")
        st.dataframe(df)
        st.stop()

    # (3) 第2関門
    # ② Key行より前の行から数値(1-31)の最大値(A)を抽出
    max_date_a = 0
    target_area = df.iloc[:key_row_idx, :]
    for col in range(target_area.shape[1]):
        for val in target_area.iloc[:, col]:
            try:
                n = float(val)
                if 1 <= n <= 31 and n > max_date_a:
                    max_date_a = int(n)
            except (ValueError, TypeError):
                continue

    # ③ ファイル名から年月を取得
    file_name = uploaded_file.name
    date_match = re.search(r'(\d{4}).*?(\d{1,2})', file_name)
    
    # ④ 取得できない場合は入力フォーム
    if not date_match:
        year = st.number_input("年を入力してください", 2026)
        month = st.number_input("月を入力してください", 1)
    else:
        year, month = int(date_match.group(1)), int(date_match.group(2))

    # ⑤ B：取得した年月から最終日付を取得
    _, last_day_b = calendar.monthrange(year, month)
    
    # ⑥⑦⑧ 判定
    if max_date_a == last_day_b:
        st.success("第2関門通過")
        return found_key, df, key_row_idx
    else:
        st.error(f"日付の不一致: PDF最大日付={max_date_a}日、{year}年{month}月の最終日={last_day_b}日")
        st.dataframe(df)
        st.stop()

# --- メイン処理 ---
# data_dict = load_and_process_data() # スプレッドシート読み込み関数
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
if uploaded_file:
    found_key, df_pdf, key_row = process_pdf_shift(uploaded_file, data_dict)
