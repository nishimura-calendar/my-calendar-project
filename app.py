import streamlit as st
import camelot
import re
import calendar
import tempfile
import base64
from datetime import datetime

# --- 第1関門の検索ロジック ---
def check_first_gate(pdf_path, year, month):
    # A：理論値算出
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # PDF全テキストの抽出と平坦化
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    full_text = " ".join([str(cell).replace('\n', '') for table in tables for row in table.df.values for cell in row])
    
    # 1. 28-31の数字を抽出（大きい順）
    all_numbers = sorted(list(set([int(d) for d in re.findall(r'\b(28|29|30|31)\b', full_text)])), reverse=True)
    
    actual_last_date = None
    actual_last_weekday = None
    
    # 2. 検索ロジック：日付の直後の文字列をチェックし、曜日なら確定
    for candidate_date in all_numbers:
        pattern = re.compile(rf'{candidate_date}.{{0,10}}?([月火水木金土日])')
        match = pattern.search(full_text)
        if match:
            actual_last_date = candidate_date
            actual_last_weekday = match.group(1)
            break
            
    # 3. 判定
    is_match = (actual_last_date == last_day and actual_last_weekday == expected_weekday)
    return is_match, actual_last_date, actual_last_weekday, last_day, expected_weekday

# --- メインUI ---
st.title("シフトカレンダー取込システム")
uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # 年月の自動抽出ロジック（シンプルに修正）
    match = re.search(r'(\d{4}).*?(\d{1,2})', uploaded_file.name)
    
    # 修正箇所：三項演算子の複雑さを解消
    default_year = int(match.group(1)) if match else 2026
    default_month = int(match.group(2)) if match else 1
    
    year = st.number_input("年", value=default_year)
    month = st.number_input("月", value=default_month)

    if st.button("解析実行"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        with st.spinner("第1関門チェック中..."):
            is_match, d, w, exp_d, exp_w = check_first_gate(tmp_path, year, month)
        
        if not is_match:
            st.error("【停止】理論値とPDF抽出値が不一致です。")
            col1, col2 = st.columns(2)
            col1.metric("理論値(A)", f"{exp_d}日({exp_w})")
            col2.metric("PDF抽出値(B)", f"{d}日({w})")
            
            st.write("---")
            st.subheader("アップロードされたPDFファイル（加工なし）")
            with open(tmp_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
            st.stop()
        
        st.success(f"第1関門通過: {d}日({w})")
