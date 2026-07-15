import streamlit as st
import pandas as pd
import io
import camelot
import re
import calendar
from datetime import datetime

# --- [1] 時程表読込 (表示はしない) ---
def get_time_schedule():
    # 既存のロジックでデータを取得・辞書登録
    # ... (既存の認証やデータ取得処理) ...
    # return location_data
    pass

# --- [2] PDFシフト表読み込みロジック ---

# 年月抽出用（ファイル名から）
def extract_year_month(filename):
    # 4桁の数字=年、月の前の数字=月
    match = re.search(r'(\d{4}).*?(\d{1,2})月', filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

# A：PDFから最終日付と曜日を抽出
def get_pdf_last_date_info(df):
    for i in range(len(df)):
        row_text = " ".join(df.iloc[i].astype(str))
        # 数字と曜日が含まれる行をヘッダーとみなす
        if re.search(r'\d+', row_text) and re.search(r'[月火水木金土日]', row_text):
            # 行から数字と曜日を抽出
            # ... (ヘッダー抽出ロジック) ...
            return last_date, last_day
    return None, None

# B：年月からその月の末日と末日の曜日を算出
def get_expected_last_date_info(year, month):
    last_day_num = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day_num)
    days = ["月", "火", "水", "木", "金", "土", "日"]
    last_day_str = days[last_date_obj.weekday()]
    return last_day_num, last_day_str

# --- メイン処理 ---
st.title("シフトカレンダー登録")

uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")

if uploaded_file:
    # 1. Camelotで読み込み
    tables = camelot.read_pdf(uploaded_file, pages='all')
    df = tables[0].df # 必要に応じて結合
    
    # 2. 第1関門
    # ① 0列目からkeyを検索
    # ... (key検索ロジック) ...
    if not key_found:
        st.error(f"「{key}」が見当たりません。シフト表ではないようです。ファイルを確認してください。")
        st.write(df)
        st.stop()
    
    # ② PDFからAを抽出
    A_date, A_day = get_pdf_last_date_info(df)
    
    # ③ ファイル名から年月を取得
    year, month = extract_year_month(uploaded_file.name)
    
    # ④ Bを算出
    B_date, B_day = get_expected_last_date_info(year, month)
    
    # ⑤・⑥ 比較と判定
    if A_date != B_date or A_day != B_day:
        st.error("エラー：ファイル名とPDF内の日付情報が一致しません。")
        st.write(f"【PDF内（A）】最終日付: {A_date}日、最終曜日: {A_day}曜日")
        st.write(f"【ファイル名（B）】最終日付: {B_date}日、最終曜日: {B_day}曜日")
        st.write("--- 対象のPDFの内容 ---")
        st.write(df)
        st.stop()
        
    st.success("ファイルチェックOKです。次のステップへ進みます。")
