import streamlit as st
import camelot
import re
import tempfile
import os

def extract_from_first_t1(uploaded_file):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # PDFからテーブルテキストを抽出
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        full_text = "\n".join([table.df.to_string() for table in tables])
        
        # 最初に出現する "T1" の位置を探す
        t1_index = full_text.find("T1")
        
        if t1_index == -1:
            return None, None, "T1が見つかりませんでした。"
        
        # T1以降のテキストのみを対象にする
        relevant_text = full_text[t1_index:]
        
        # 日付と曜日のペアを全抽出
        matches = re.findall(r'(\d{1,2})[\s\n]+([日月火水木金土])', relevant_text)
        
        if matches:
            # 最後に見つかったペア（＝最終日付）を返す
            last_date, last_day = matches[-1]
            return int(last_date), last_day, None
            
        return None, None, "T1以降に日付情報が見つかりませんでした。"
        
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# --- UI構築 ---
st.title("シフト表自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        last_date, last_day, error = extract_from_first_t1(uploaded_pdf)
        
        if error:
            st.error(error)
        else:
            st.success("解析成功")
            st.write(f"最終日付: {last_date}日")
            st.write(f"最終曜日: {last_day}曜日")
