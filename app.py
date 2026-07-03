import streamlit as st
import camelot
import re
import calendar
import tempfile
import base64
from datetime import datetime

# --- 第1関門のチェック関数（ロジック部分は前述の「最大値抽出」を採用） ---
def check_first_gate(pdf_path, year, month):
    # 理論値(A)
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # PDF抽出(B)
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    full_text = " ".join([str(cell).replace('\n', ' ') for table in tables for row in table.df.values for cell in row])
    
    # 28-31のいずれかの数値 ＋ 曜日を探す
    matches = re.finditer(r'(28|29|30|31).{0,4}?([月火水木金土日])', full_text)
    candidates = [(int(m.group(1)), m.group(2)) for m in matches]
    
    if not candidates:
        return False, None, None, last_day, expected_weekday
        
    actual_last_date, actual_last_weekday = max(candidates, key=lambda x: x[0])
    
    return (actual_last_date == last_day and actual_last_weekday == expected_weekday), \
           actual_last_date, actual_last_weekday, last_day, expected_weekday

# --- メインUI ---
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_file is not None:
    # ① ファイル名から年月を取得を試みる
    match = re.search(r'(\d{4}).*?(\d{1,2})', uploaded_file.name)
    
    if match:
        year = st.number_input("年", value=int(match.group(1)))
        month = st.number_input("月", value=int(match.group(2)))
    else:
        # 取得できない場合のみフォームを表示
        st.warning("ファイル名から年月を自動取得できませんでした。")
        year = st.number_input("年を入力してください", min_value=2000, max_value=2100, value=2026)
        month = st.number_input("月を入力してください", min_value=1, max_value=12, value=1)

    if st.button("解析実行"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        
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

        success, d, w, exp_d, exp_w = check_first_gate(tmp_path, year, month)
        
        # ② 不一致の場合の詳細表示
        if not success:
            st.error("【停止】理論値とPDF抽出値が不一致です。")
            col1, col2 = st.columns(2)
            col1.metric("理論値(A)", f"{exp_d}日({exp_w})")
            col2.metric("PDF抽出値(B)", f"{d}日({w})")
            
            # PDFファイルの表示
            st.subheader("アップロードされたPDF内容")
            with open(tmp_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="500" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
            st.stop()
        
        st.success("第1関門通過！")

        # 第2関門
        target_key = "勤務地" # 検索するkey
        success2 = check_second_gate(tmp_path, target_key)
        if not success2:
            st.error(f"【停止】勤務地-{target_key}-が時程表に設定されていません。")
            st.stop()
        
        st.success("第2関門通過：解析を継続します。")
