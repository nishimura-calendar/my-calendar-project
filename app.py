import streamlit as st
import pdfplumber
import re
import calendar
import tempfile
import base64
from datetime import datetime

# --- 第1関門の検索ロジック ---
def check_first_gate(pdf_path, year, month):
    # 理論値算出(A)
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # PDF全テキストの抽出
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    
    # 1. 28-31の数字を大きい順に抽出
    all_numbers = sorted(list(set([int(d) for d in re.findall(r'\b(28|29|30|31)\b', full_text)])), reverse=True)
    
    actual_last_date = None
    actual_last_weekday = None
    
    # 2. 検索ロジック：日付の直後の文字列をチェック
    for candidate_date in all_numbers:
        # 数字の直後から10文字以内に曜日があるか検索
        pattern = re.compile(rf'{candidate_date}.{{0,10}}?([月火水木金土日])')
        match = pattern.search(full_text)
        if match:
            actual_last_date = candidate_date
            actual_last_weekday = match.group(1)
            break
            
    is_match = (actual_last_date == last_day and actual_last_weekday == expected_weekday)
    return is_match, actual_last_date, actual_last_weekday, last_day, expected_weekday

# --- メインUI ---
st.title("シフトカレンダー取込システム")

uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # 1. ファイル名から年月の抽出を試みる
    match = re.search(r'(\d{4}).*?(\d{1,2})', uploaded_file.name)
    
    # 2. 自動検出できた場合とそうでない場合の分岐
    if match:
        default_year = int(match.group(1))
        default_month = int(match.group(2))
        st.info(f"ファイル名から {default_year}年{default_month}月 を検出しました。")
    else:
        st.warning("ファイル名から年月を自動検出できませんでした。入力してください。")
        default_year, default_month = 2026, 1
    
    # 手動入力欄（自動検出された場合も修正可能）
    year = st.number_input("年", value=default_year, min_value=2000, max_value=2100)
    month = st.number_input("月", value=default_month, min_value=1, max_value=12)

    if st.button("解析実行"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        with st.spinner("解析中..."):
            is_match, d, w, exp_d, exp_w = check_first_gate(tmp_path, year, month)
        
        # 判定
        if not is_match:
            st.error("【停止】理論値とPDF抽出値が不一致です。")
            
            # 不一致の理由を比較表示
            col1, col2 = st.columns(2)
            col1.metric("理論値(A)", f"{exp_d}日({exp_w})")
            col2.metric("PDF抽出値(B)", f"{d}日({w})")
            
            st.write("---")
            st.subheader("アップロードされたPDFファイル")
            
            # PDFの直接表示
            with open(tmp_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
            st.stop()
        
        st.success(f"第1関門通過: 最終日は {d}日({w}) です。")
        # --- ここから第2関門（勤務地検索など）の処理を追加可能 ---
