import streamlit as st
import camelot
import re
import os
import tempfile
import pandas as pd
import datetime
import calendar

# [1] 時程表読み込み (マスタデータ)
def load_master_data():
    # 実際には共有スプレッドシートのIDを指定して読み込む箇所
    # ここではローカルのシフトカレンダー.xlsxを読み込む想定
    if os.path.exists('シフトカレンダー.xlsx'):
        return pd.read_excel('シフトカレンダー.xlsx', sheet_name='time_schdule')
    return None

# [2]〈1〉(1)〜(3) PDFシフト表読込・解析
def process_pdf_shift(uploaded_file):
    # 一時ファイルの作成
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # Camelotで読み込み
        tables = camelot.read_pdf(tfile.name, flavor='lattice', pages='all')
        full_text = ""
        for table in tables:
            full_text += table.df.to_string()
            
        # (2) 第1関門: Key検索 (T1)
        key_list = ["T1", "T2"]
        found_key = next((k for k in key_list if re.search(rf"\b{re.escape(k)}\b", full_text)), None)
        
        if not found_key:
            return None, None, None, "Keyが見当たりません。シフト表ではないようです。"
        
        # (3) 第2関門: 年月特定と整合性チェック
        # PDF名から年月取得
        match = re.search(r'(\d{4})年(\d{1,2})月', uploaded_file.name)
        year, month = (int(match.group(1)), int(match.group(2))) if match else (2026, 1)
        
        # 期待値計算
        _, last_day_num = calendar.monthrange(year, month)
        last_date_dt = datetime.date(year, month, last_day_num)
        expected_day = ["月", "火", "水", "木", "金", "土", "日"][last_date_dt.weekday()]
        
        # 実測値取得
        header_area = full_text[re.search(rf"\b{re.escape(found_key)}\b", full_text).end():]
        all_dates = re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', header_area)
        all_days = re.findall(r'[日月火水木金土]', header_area)
        
        actual_date = int(all_dates[-1]) if all_dates else 0
        actual_day = all_days[-1] if all_days else ""
        
        # 整合性チェック
        if actual_date != last_day_num or actual_day != expected_day:
            return found_key, actual_date, actual_day, f"エラー: PDFの日付がカレンダーと一致しません (期待値: {last_day_num}日 {expected_day}曜)"
            
        return found_key, actual_date, actual_day, None
        
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# --- UI構築 ---
st.title("シフト表自動読込プログラム")

# アップロードボタン
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        key, l_date, l_day, error = process_pdf_shift(uploaded_pdf)
        
        if error:
            st.error(error)
        else:
            st.success(f"解析成功: {key}")
            st.write(f"最終日付: {l_date}日 / 最終曜日: {l_day}曜日")
            st.balloons()
