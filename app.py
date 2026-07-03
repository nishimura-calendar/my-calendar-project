import streamlit as st
import pdfplumber
import re
import calendar
import tempfile
import base64
from datetime import datetime

# --- 第1関門の検索ロジック ---
def check_first_gate(pdf_path, year, month):
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    actual_last_date = None
    actual_last_weekday = None

    with pdfplumber.open(pdf_path) as pdf:
        # 表のセルを走査して月末日を探す
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    row_text = " ".join([str(cell) for cell in row if cell])
                    # 最終日（last_day）が含まれる行を探す
                    if str(last_day) in row_text:
                        actual_last_date = last_day
                        # その行内に曜日があるかチェック
                        for w in weekdays_jp:
                            if w in row_text:
                                actual_last_weekday = w
                                break
    
    is_match = (actual_last_date == last_day and actual_last_weekday == expected_weekday)
    return is_match, actual_last_date, actual_last_weekday, last_day, expected_weekday

# --- メインUI ---
st.title("シフトカレンダー取込システム")
uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # ファイル名から「4桁の年」と「1〜12の月」を抽出する正規表現
    # 例: "2026", "1" を検索
    # 年: 2000-2999, 月: 1-12
    year_match = re.search(r'(20\d{2})', uploaded_file.name)
    month_match = re.search(r'([1-9]|1[0-2])(?=月)', uploaded_file.name)
    
    default_year = int(year_match.group(1)) if year_match else 2026
    default_month = int(month_match.group(1)) if month_match else 1
    
    year = st.number_input("年", value=default_year, min_value=2000, max_value=2100)
    month = st.number_input("月", value=default_month, min_value=1, max_value=12)

    if st.button("解析実行"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        is_match, d, w, exp_d, exp_w = check_first_gate(tmp_path, year, month)
        
        if not is_match:
            st.error("【停止】理論値とPDF抽出値が不一致です。")
            col1, col2 = st.columns(2)
            col1.metric("理論値(A)", f"{exp_d}日({exp_w})")
            col2.metric("PDF抽出値(B)", f"{d}日({w})")
            st.stop()
        
        st.success(f"第1関門通過: 最終日は {d}日({w}) です。")
