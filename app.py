import streamlit as st
import pdfplumber
import re
import calendar
import tempfile

# --- 第1関門：修正版検索ロジック ---
def check_first_gate(pdf_path, year, month):
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    with pdfplumber.open(pdf_path) as pdf:
        # ページを後ろから探索（通常、月末データは表の後半か最終ページにあるため）
        for page in reversed(pdf.pages):
            text = page.extract_text()
            if not text: continue
            
            # ページ内から「28, 29, 30, 31」を探す
            all_dates = re.findall(r'\b(28|29|30|31)\b', text)
            if all_dates:
                # ページ内で最大の日付を月末候補とする
                candidate_date = int(max(all_dates))
                # その日付の「後ろ」にある曜日を検索（正規表現：日付の後の10文字以内）
                pattern = re.compile(rf'{candidate_date}.{{0,10}}?([月火水木金土日])')
                match = pattern.search(text)
                
                if match:
                    actual_date = candidate_date
                    actual_weekday = match.group(1)
                    return (actual_date == last_day and actual_weekday == expected_weekday), actual_date, actual_weekday

    return False, None, None

# --- Streamlit メインUI ---
st.title("シフトカレンダー取込システム")
uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # ファイル名から年月を抽出（より広く検索）
    # 2025年6月 または 2025_6 などのパターンを想定
    match = re.search(r'(\d{4}).*?(\d{1,2})', uploaded_file.name)
    
    # ユーザー入力フォーム（自動判定値を初期値に）
    year = st.number_input("年", value=int(match.group(1)) if match else 2025)
    month = st.number_input("月", value=int(match.group(2)) if match else 6)

    if st.button("解析実行"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        success1, d, w = check_first_gate(tmp_path, year, month)
        
        if not success1:
            st.error(f"【停止】理論値とPDF抽出値が不一致です。抽出結果: {d}日({w})")
            st.stop()
        
        st.success("第1関門通過")
        # 第2関門へ
