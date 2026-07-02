import streamlit as st
import camelot
import re
import calendar
import tempfile
from datetime import datetime

# --- 第1関門：PDFの末尾日付と曜日を抽出・照合 ---
def check_first_gate(pdf_path, year, month):
    # A：理論値算出
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # B：PDFから抽出（ペア検索による堅牢なロジック）
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    full_text = " ".join([" ".join(row) for table in tables for row in table.df.values.astype(str)])
    
    # 正規表現：日付(28-31)の後、4文字以内に曜日があるパターンを探す
    # 複数の候補から、日付が最大のものを末尾情報として採用
    matches = re.finditer(r'(28|29|30|31)[\s\S]{0,10}?([月火水木金土日])', full_text)
    candidates = []
    for m in matches:
        candidates.append((int(m.group(1)), m.group(2)))
    
    if not candidates:
        return False, None, None
        
    actual_last_date, actual_last_weekday = max(candidates, key=lambda x: x[0])

    # ⑤ 判定
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        return True, actual_last_date, actual_last_weekday
    else:
        return False, actual_last_date, actual_last_weekday

# --- 第2関門：勤務地keyの存在確認 ---
def check_second_gate(pdf_path, key_inf):
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    full_text = " ".join([" ".join(row) for table in tables for row in table.df.values.astype(str)])
    
    # 完全一致で検索
    if key_inf in full_text:
        return True
    return False

# --- メインUI ---
st.title("シフトカレンダー取込システム")

uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # ① 年月取得
    match = re.search(r'(\d{4}).*?(\d{1,2})', uploaded_file.name)
    year = st.number_input("年", value=int(match.group(1)) if match else 2026)
    month = st.number_input("月", value=int(match.group(2)) if match else 1)

    if st.button("解析実行"):
        # 一時ファイル作成（Streamlit Cloud環境への対応）
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        # 第1関門実行
        with st.spinner("第1関門チェック中..."):
            success1, d, w = check_first_gate(tmp_path, year, month)
        
        if not success1:
            st.error(f"【停止】理論値とPDF抽出値が不一致です。")
            st.write(f"判定: 理論上は {calendar.monthrange(year, month)[1]}日、PDFからは {d}日({w}) が抽出されました。")
            st.stop()
        
        st.success(f"第1関門通過: {d}日({w})")

        # 第2関門実行
        target_key = "勤務地" # 手順書に基づき検索するkey
        with st.spinner("第2関門チェック中..."):
            success2 = check_second_gate(tmp_path, target_key)
            
        if not success2:
            st.error(f"【停止】勤務地-{target_key}-が時程表に設定されていません。確認が必要です。")
            st.stop()
        
        st.success("第2関門通過：詳細読込へ進みます。")
