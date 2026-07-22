import streamlit as st
import camelot
import pandas as pd
import re
import tempfile
import os
import datetime
import calendar

# [1] マスタデータ（シフトカレンダー.xlsx）の読み込み
def load_master_data():
    """
    シフトカレンダー.xlsxを読み込み、Dataframeを返す。
    存在しない場合はNoneを返す。
    """
    file_path = 'シフトカレンダー.xlsx'
    if os.path.exists(file_path):
        return pd.read_excel(file_path, sheet_name='time_schdule')
    return None

# [2]〈1〉(1)〜(3)② PDF解析・整合性チェックロジック
def process_pdf_shift(uploaded_file):
    # (1) 一時ファイル経由でのPDF読み込み（Camelot用）
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # Camelotでテーブル読み込み（streamモードがPDF解析に安定）
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        full_text = "\n".join([table.df.to_string() for table in tables])
        
        # (2) Key検索（T1またはT2）
        # Keyが含まれる行以降のテキストに絞る
        key_pattern = r"(T1|T2)"
        match_key = re.search(key_pattern, full_text)
        
        if not match_key:
            return None, None, "Key (T1/T2) が見つかりませんでした。"
        
        target_area = full_text[match_key.start():]
        
        # (3) 最終日付・曜日の抽出
        # 末尾にある「31 土」のようなパターンを抽出[cite: 2]
        # 正規表現：数字(1-31) + 空白 + 曜日
        date_day_matches = re.findall(r'(\d{1,2})\s+([日月火水木金土])', target_area)
        
        if not date_day_matches:
            return None, None, "日付と曜日の情報が抽出できませんでした。"
        
        # リストの最後が最終日となる
        last_date_str, last_day = date_day_matches[-1]
        last_date = int(last_date_str)
        
        # (3)② 整合性チェック（期待値との比較）
        # ファイル名から年月を取得または推測（例: 2026年1月）
        # ここでは簡易的に現在の年月を使用するが、ファイル名から抽出することも可能
        today = datetime.date.today()
        _, last_day_num = calendar.monthrange(today.year, today.month)
        
        # 曜日計算
        last_date_dt = datetime.date(today.year, today.month, last_date)
        expected_day = ["月", "火", "水", "木", "金", "土", "日"][last_date_dt.weekday()]
        
        if last_date != last_day_num or last_day != expected_day:
            return last_date, last_day, f"整合性エラー: 期待値({last_day_num}日 {expected_day})と不一致です。"
            
        return last_date, last_day, None
        
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# --- UI構築 ---
st.title("シフト表自動読込プログラム")

# [1] マスタデータの確認
df_master = load_master_data()
if df_master is not None:
    st.write("マスタデータ読込完了")
else:
    st.warning("シフトカレンダー.xlsxが見つかりません。")

# [2] PDFアップロードボタン
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        last_date, last_day, error = process_pdf_shift(uploaded_pdf)
        
        if error:
            st.error(error)
        else:
            st.success(f"解析成功！")
            st.write(f"最終日付: {last_date}日")
            st.write(f"最終曜日: {last_day}曜日")
