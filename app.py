import streamlit as st
import camelot
import re
import tempfile
import os

def extract_latest_date_from_t1(uploaded_file):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # PDFを解析
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        full_text = "\n".join([table.df.to_string() for table in tables])
        
        # 1. ノイズ除去：罫線（+ | -）をスペースに置き換える
        clean_text = re.sub(r'[+|\-\|]', ' ', full_text)
        
        # 2. 最初の「T1」の位置を探す
        t1_index = clean_text.find("T1")
        if t1_index == -1:
            return None, None, "T1が見つかりませんでした。"
        
        # T1以降のテキストに絞り込む
        relevant_text = clean_text[t1_index:]
        
        # 3. 1〜31の数字だけを抽出
        all_numbers = re.findall(r'\b(0?[1-9]|[12]\d|3[01])\b', relevant_text)
        
        if not all_numbers:
            return None, None, "T1以降に日付が見つかりませんでした。"
        
        # 4. 数字に変換して最大のものを取得（その月の最終日）
        int_dates = [int(n) for n in all_numbers]
        last_date = max(int_dates)
        
        # 5. 最終日の直後（20文字以内）に曜日があるか探す
        pattern = str(last_date) + r'[^\n\d]*?([日月火水木金土])'
        day_match = re.search(pattern, relevant_text)
        
        last_day = day_match.group(1) if day_match else "曜日特定不可"
        
        return last_date, last_day, None
            
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# UI構築
st.title("シフト表自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        last_date, last_day, error = extract_latest_date_from_t1(uploaded_pdf)
        
        if error:
            st.error(error)
        else:
            st.success("解析成功")
            st.write(f"最終日付: {last_date}日")
            st.write(f"最終曜日: {last_day}曜日")
