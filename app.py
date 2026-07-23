import streamlit as st
import camelot
import re
import tempfile
import os

def extract_last_date_debug(uploaded_file):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        # 全テーブルのテキストを結合
        full_text = "\n".join([table.df.to_string() for table in tables])
        
        # 1. 最初のT1以降に絞る
        t1_index = full_text.find("T1")
        relevant_text = full_text[t1_index:] if t1_index != -1 else full_text
        
        # 2. パターンを少し広げて、改行やスペースがあっても拾えるようにする
        # 数字の直後に曜日が来る、あるいは数字の後に記号などを挟んで曜日が来るケースを考慮
        # 例: "31 土", "31\n土", "31...土"
        matches = re.findall(r'(\d{1,2})[^\d\n]*([日月火水木金土])', relevant_text)
        
        if not matches:
            return None, None, f"抽出失敗: テキストが見つかりません。抽出テキスト: {relevant_text[:200]}"
            
        # 3. 抽出された全ペアをリスト化して、最後に確認されたペアを返す
        # デバッグのために抽出されたリストを表示
        st.write("抽出された全候補:", matches)
        
        # 数字でソートして、最大の数字を選ぶ（31日を確実に取るため）
        sorted_matches = sorted(matches, key=lambda x: int(x[0]))
        last_date, last_day = sorted_matches[-1]
        
        return int(last_date), last_day, None
            
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# --- UI構築 ---
st.title("シフト表自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        last_date, last_day, error = extract_last_date_debug(uploaded_pdf)
        
        if error:
            st.error(error)
        else:
            st.success("解析成功")
            st.write(f"最終日付: {last_date}日")
            st.write(f"最終曜日: {last_day}曜日")
