import streamlit as st
import camelot
import re
import tempfile
import os

def extract_shift_header(uploaded_file, target_key="T1"):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # Camelotでテーブルとして読み込み
        tables = camelot.read_pdf(tfile.name, flavor='lattice', pages='all')
        
        for table in tables:
            df = table.df
            # テーブルの全セルからKeyを探す
            for i, row in df.iterrows():
                if target_key in row.values:
                    # Keyが見つかった行の「日付行」と「曜日行」を抽出
                    # レイアウト上、Key行のすぐ下の行に日付、その下に曜日があると仮定
                    if i + 2 < len(df):
                        date_row = df.iloc[i + 1] # 上段（日付）
                        day_row = df.iloc[i + 2]  # 下段（曜日）
                        
                        # 日付行から数値のみ抽出（1〜31）
                        dates = [int(cell) for cell in date_row if str(cell).isdigit() and 1 <= int(cell) <= 31]
                        
                        if dates:
                            # 抽出できた日付の最大値（＝最終日）と、それに対応する曜日を返す
                            # ここでは単純化のため、リストの最後の日付と曜日をペアで返す
                            last_date = max(dates)
                            # 曜日は日付と同じ列のインデックスを取得
                            return last_date, day_row[len(date_row)-1]
        return None, None
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# --- UI構築 ---
st.title("最終日・曜日抽出プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    last_date, last_day = extract_shift_header(uploaded_pdf)
    if last_date:
        st.success(f"最終日付: {last_date}日")
        st.write(f"最終曜日: {last_day}曜日")
    else:
        st.error("日付と曜日の行を特定できませんでした。")
