import streamlit as st
import camelot
import re
import calendar
import os
import tempfile
from datetime import datetime

# --- 第1関門の関数 ---
def check_first_gate(pdf_path, year, month):
    # A：理論値算出
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # B：PDFから抽出（Camelotの表読み込み）
    # pdfplumberへの切り替えが確実ですが、Camelotで継続する場合の改良案です
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    full_text = " ".join([str(cell).replace('\n', ' ') for table in tables for row in table.df.values for cell in row])
    
    # 【訂正箇所】日付(28-31)を抽出して数値リスト化し、その中から最大値を取得
    # これにより、ヘッダーの年号(例:2031)が含まれていても、より確実に日付を特定します
    date_matches = re.findall(r'\b(28|29|30|31)\b', full_text)
    
    if not date_matches:
        return False, None, None
        
    # 日付リストを数値に変換して最大値を取得
    date_ints = [int(d) for d in date_matches]
    actual_last_date = max(date_ints)
    
    # 曜日抽出（抽出された日付の近傍など特定が難しい場合、曜日リストの最後を取るのが現状の最適解）
    all_weekdays = re.findall(r'[月火水木金土日]', full_text)
    actual_last_weekday = all_weekdays[-1] if all_weekdays else None

    # ⑤ 判定
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        return True, actual_last_date, actual_last_weekday
    else:
        return False, actual_last_date, actual_last_weekday
        
# --- 第2関門の関数 ---
def check_second_gate(pdf_path, key_inf):
    # PDFからテキストを抽出して勤務地keyを検索
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    full_text = " ".join([" ".join(row) for table in tables for row in table.df.values.astype(str)])
    
    # 完全一致で検索
    if key_inf in full_text:
        return True
    return False

# --- Streamlit メインUI ---
st.title("シフトカレンダー取込システム")

uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # ① 年月取得
    match = re.search(r'(\d{4}).*?(\d{1,2})', uploaded_file.name)
    year = st.number_input("年", value=int(match.group(1)) if match else 2026)
    month = st.number_input("月", value=int(match.group(2)) if match else 1)

    if st.button("解析実行"):
        # 一時ファイル作成
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        # 第1関門
        success1, d, w = check_first_gate(tmp_path, year, month)
        if not success1:
            st.error(f"【停止】理論値とPDF抽出値が不一致です: {d}日({w})")
            st.stop()
        
        st.success("第1関門通過")

        # 第2関門
        target_key = "勤務地" # 検索するkey
        success2 = check_second_gate(tmp_path, target_key)
        if not success2:
            st.error(f"【停止】勤務地-{target_key}-が時程表に設定されていません。")
            st.stop()
        
        st.success("第2関門通過：解析を継続します。")
