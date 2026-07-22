import streamlit as st
import camelot
import re
import tempfile
import os

def extract_date_from_t1_block(uploaded_file, target_key="T1"):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # Camelotでテキストを抽出
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        full_text = "\n".join([table.df.to_string() for table in tables])
        
        # 1. 最初のT1が出現する箇所を特定
        t1_index = full_text.find(target_key)
        if t1_index == -1:
            return None, None, "T1が見つかりません。"
            
        # 2. T1以降のブロックを切り出し
        block = full_text[t1_index:]
        
        # 3. ブロック内の数字（日付）と曜日を検索
        # 正規表現：日付と曜日の並び（例: 31\n土）を考慮
        # 構造的に日付が先に来て、その後に曜日がくるケースを最後から探す
        matches = list(re.finditer(r'\b(3[01]|[12]?[0-9])\s+([日月火水木金土])', block))
        
        if not matches:
            return None, None, "日付と曜日のペアが見つかりません。"
            
        # 4. 最後に見つかったペアを「最終日付・曜日」として取得
        last_match = matches[-1]
        return last_match.group(1), last_match.group(2), None

    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# UI
st.title("最終日・曜日抽出 (T1ブロック解析)")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    last_date, last_day, error = extract_date_from_t1_block(uploaded_pdf)
    if error:
        st.error(error)
    else:
        st.write(f"最終日付: {last_date}日")
        st.write(f"最終曜日: {last_day}曜日")
