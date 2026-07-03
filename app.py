import streamlit as st
import pdfplumber
import re
import calendar
import tempfile
import base64
from datetime import datetime

# --- 第1関門の解析ロジック ---
def analyze_pdf_last_date(pdf_path, year, month):
    """PDF全体から曜日を全量抽出し、最終日の曜日を特定する"""
    last_day = calendar.monthrange(year, month)[1]
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    
    # PDF全体から曜日をすべて抽出
    all_weekdays = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                # 曜日文字のみを順番に取得
                found = re.findall(r'[月火水木金土日]', text)
                all_weekdays.extend(found)
    
    # 最終的な判定
    if len(all_weekdays) >= last_day:
        actual_last_date = len(all_weekdays)
        actual_last_weekday = all_weekdays[last_day - 1]
        return actual_last_date, actual_last_weekday
    return None, None

# --- Streamlit メインUI ---
st.title("シフトカレンダー取込システム")

uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # 1. 年月の自動検出
    year_match = re.search(r'(20\d{2})', uploaded_file.name)
    month_match = re.search(r'([1-9]|1[0-2])(?=月)', uploaded_file.name)
    
    if year_match and month_match:
        year = int(year_match.group(1))
        month = int(month_match.group(1))
        st.success(f"ファイルを認識しました：{year}年{month}月")
    else:
        st.warning("ファイル名から年月を自動検出できませんでした。入力してください。")
        year = st.number_input("年", value=2026, min_value=2000, max_value=2100)
        month = st.number_input("月", value=1, min_value=1, max_value=12)

    # 2. 解析実行
    if st.button("解析実行"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        # 計算上の最終データ
        last_day = calendar.monthrange(year, month)[1]
        weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
        expected_weekday = weekdays_jp[datetime(year, month, last_day).weekday()]
        
        # PDFからの実データ
        actual_last_date, actual_last_weekday = analyze_pdf_last_date(tmp_path, year, month)

        # 3. 判定ロジック
        if actual_last_date == last_day:
            st.success(f"解析成功：最終日は{last_day}日（{actual_last_weekday}曜日）です。")
            # 次のステップ（第2関門へ）
        else:
            st.error("【エラー】PDFのデータが不一致です。")
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("計算上の期待値")
                st.write(f"最終日付: {last_day}日")
                st.write(f"最終曜日: {expected_weekday}")
            
            with col2:
                st.subheader("PDFからの検出値")
                st.write(f"最終日付: {actual_last_date}日")
                st.write(f"最終曜日: {actual_last_weekday}")
            
            # PDFファイルの表示
            st.subheader("アップロードされたPDFファイル")
            with open(tmp_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="500" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
