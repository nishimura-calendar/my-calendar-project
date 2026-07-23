import streamlit as st
import camelot
import pandas as pd
import tempfile
import os

def extract_date_day_pairs(uploaded_file):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # テーブル解析
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        
        for table in tables:
            df = table.df
            # テーブル全体を走査して「T1」を含む行を探す
            for i in range(len(df)):
                row_values = df.iloc[i].astype(str).tolist()
                if "T2" in row_values:
                    # T1行の次の行を「曜日行」、その上の行を「日付行」と仮定
                    # 表の構造に合わせて調整（必要であれば i+1 や i-1 などで微調整）
                    date_row = df.iloc[i-1].values if i > 0 else None
                    day_row = df.iloc[i+1].values if i < len(df)-1 else None
                    
                    if date_row is not None and day_row is not None:
                        # 日付と曜日をペアにする（列ごとに処理）
                        pairs = {}
                        for col in range(len(date_row)):
                            d = str(date_row[col]).strip()
                            day = str(day_row[col]).strip()
                            # 日付が数字1-31で、曜日が日月火水木金土であるか
                            if d.isdigit() and day in "日月火水木金土":
                                pairs[int(d)] = day
                        
                        if pairs:
                            # 最終日を取得
                            last_date = max(pairs.keys())
                            return last_date, pairs[last_date], None
        
        return None, None, "T1行付近から日付と曜日のペアを抽出できませんでした。"
            
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# UI
st.title("シフト表自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        last_date, last_day, error = extract_date_day_pairs(uploaded_pdf)
        if error:
            st.error(error)
        else:
            st.success("解析成功")
            st.write(f"最終日付: {last_date}日")
            st.write(f"最終曜日: {last_day}曜日")
