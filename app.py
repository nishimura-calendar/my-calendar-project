import streamlit as st
import camelot
import re
import calendar
import tempfile
from datetime import datetime

# --- 第1関門：PDFの末尾日付と曜日をペアで抽出・照合 ---
def check_first_gate(pdf_path, year, month):
    # A：理論値算出
    last_day = calendar.monthrange(year, month)[1]
    last_date_obj = datetime(year, month, last_day)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_weekday = weekdays_jp[last_date_obj.weekday()]

    # B：PDFから抽出（ペア検索による堅牢なロジック）
    # flavor='stream'でPDFの表構造を読み込みます
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    
    # セル内の改行をスペースに置換し、全セルを連結して平坦なテキストにします
    full_text = " ".join([str(cell).replace('\n', ' ') for table in tables for row in table.df.values for cell in row])
    
    # 【改良点】
    # 日付(28-31)の直後（0〜4文字の間）に曜日があるペアを全て抽出
    # この正規表現なら、行跨ぎや余計な文字が入ってもペアを認識します
    matches = re.finditer(r'(28|29|30|31).{0,4}?([月火水木金土日])', full_text)
    
    candidates = []
    for m in matches:
        candidates.append((int(m.group(1)), m.group(2)))
    
    if not candidates:
        return False, None, None
        
    # 日付が最大のものを「末尾のデータ」として確定（これでヘッダー等の誤検知を回避）
    actual_last_date, actual_last_weekday = max(candidates, key=lambda x: x[0])

    # 判定
    if actual_last_date == last_day and actual_last_weekday == expected_weekday:
        return True, actual_last_date, actual_last_weekday
    else:
        return False, actual_last_date, actual_last_weekday

# --- 第2関門：勤務地keyの存在確認 ---
def check_second_gate(pdf_path, key_inf):
    tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
    full_text = " ".join([str(cell).replace('\n', ' ') for table in tables for row in table.df.values for cell in row])
    
    if key_inf in full_text:
        return True
    return False

# --- メインUI ---
st.title("シフトカレンダー取込システム")

uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    match = re.search(r'(\d{4}).*?(\d{1,2})', uploaded_file.name)
    year = st.number_input("年", value=int(match.group(1)) if match else 2026)
    month = st.number_input("月", value=int(match.group(2)) if match else 1)

    if st.button("解析実行"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        # 第1関門
        with st.spinner("第1関門チェック中..."):
            success1, d, w = check_first_gate(tmp_path, year, month)
        
        if not success1:
            st.error(f"【停止】理論値とPDF抽出値が不一致です。")
            st.write(f"判定: 理論上は {calendar.monthrange(year, month)[1]}日、PDFからは {d}日({w}) が抽出されました。")
            st.stop()
        
        st.success(f"第1関門通過: {d}日({w})")

        # 第2関門
        target_key = "勤務地" 
        with st.spinner("第2関門チェック中..."):
            success2 = check_second_gate(tmp_path, target_key)
            
        if not success2:
            st.error(f"【停止】勤務地-{target_key}-が時程表に設定されていません。確認が必要です。")
            st.stop()
        
        st.success("第2関門通過：詳細読込へ進みます。")
