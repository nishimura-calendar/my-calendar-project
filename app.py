import streamlit as st
import pdfplumber
import pandas as pd
import re
import calendar
import base64
from datetime import datetime

# --- PDF表示用のHTML埋め込み関数 ---
def show_pdf_preview(uploaded_file):
    base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

# 1. 抽出ロジック（pdfplumber専用版）
def extract_date_day_pairs(uploaded_file, key):
    # ファイルポインタを先頭に戻す（念のため）
    uploaded_file.seek(0)
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table).fillna('')
                table_str = " ".join([" ".join(row) for row in df.astype(str).values])
                if key not in table_str:
                    continue
                
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
                        return last_date, pairs[last_date], None
        return None, None, f"キー '{key}' と有効な日付データが見つかりません。"

# 2. メインロジック
st.title("シフトカレンダー自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    y, m = 2026, 1
    expected_end_of_month = calendar.monthrange(y, m)[1]
    expected_day_of_week = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, expected_end_of_month)]

    last_date, last_day, error = None, None, None
    for k in ["T1", "T2"]:
        last_date, last_day, error = extract_date_day_pairs(uploaded_pdf, k)
        if error is None:
            break
    
    if error:
        st.error(error)
        st.write("---")
        st.subheader("アップロードされたPDFファイルの内容")
        show_pdf_preview(uploaded_pdf) # ここでプレビューを表示
    else:
        if last_date != expected_end_of_month:
            st.error("日付の整合性がとれませんでした。")
            st.write(f"① ファイル内容からの抽出：A={last_date}日({last_day}曜日)")
            st.write(f"② 設定年月からの算出：B={expected_end_of_month}日({expected_day_of_week}曜日)")
            
            st.write("---")
            st.subheader("アップロードされたPDFファイルの内容")
            show_pdf_preview(uploaded_pdf) # ここでプレビューを表示
            
            st.stop() # ここで停止
        
        st.success(f"解析成功：{y}年{m}月 ({last_date}日 {last_day}曜日)")
