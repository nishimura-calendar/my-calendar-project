import streamlit as st
import camelot
import re
import calendar
from datetime import datetime
import os

def check_pdf_first_gate(pdf_path, year, month):
    # --- A：理論上の最終日付と最終曜日 ---
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # --- B：PDFから最終情報を抽出 ---
    # 手順：camelotを使用して読込
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    
    full_text = ""
    for table in tables:
        full_text += " ".join([" ".join(row) for row in table.df.values.astype(str)])
    
    # 日付(28-31)と曜日を抽出
    all_dates = re.findall(r'\b(28|29|30|31)\b', full_text)
    all_weekdays = re.findall(r'[月火水木金土日]', full_text)
    
    # 末尾を確定
    actual_last_date = int(all_dates[-1]) if all_dates else None
    actual_last_weekday = all_weekdays[-1] if all_weekdays else None

    # --- ⑤ A=Bなら通過、⑥ A≠Bなら停止 ---
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        return True, actual_last_date, actual_last_weekday
    else:
        return False, actual_last_date, actual_last_weekday

# Streamlit UI
st.title("シフトカレンダー取込システム")

# 1. ファイルアップローダー
uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # ファイル名から年月を取得 (①)
    match = re.search(r'(\d{4}).*?(\d{1,2})', uploaded_file.name)
    
    if match:
        year, month = int(match.group(1)), int(match.group(2))
    else:
        # ② 取得できない場合は手入力
        st.warning("ファイル名から年月を取得できませんでした。")
        year = st.number_input("年を入力", value=2026)
        month = st.number_input("月を入力", value=1)

    # 第1関門の実行
    if st.button("第1関門を実行"):
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        success, d, w = check_pdf_first_gate("temp.pdf", year, month)
        
        if success:
            st.success(f"通過: {d}日({w})")
        else:
            # ⑥ 停止処理
            st.error(f"【停止】理論値とPDF抽出値が不一致です。")
            st.write(f"抽出された最終日: {d}日({w})")
            # PDF表示処理
            st.write("対象PDFファイル:")
            st.download_button("PDFをダウンロードして確認", data=uploaded_file, file_name="target.pdf")
            st.stop() # ここでプログラムを停止
