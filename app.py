import streamlit as st
import camelot
import re
import tempfile
import os

def extract_correct_date_robust(uploaded_file):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        full_text = "\n".join([table.df.to_string() for table in tables])
        
        # 【重要】
        # 1. \b で数字の境界を指定（他の数字とくっついていないもののみ）
        # 2. (0?[1-9]|[12]\d|3[01]) で 1〜31 の数値のみに限定
        # 3. \s* で曜日との間のスペースや改行を許容
        # 4. ([日月火水木金土]) で曜日を抽出
        pattern = r'\b(0?[1-9]|[12]\d|3[01])\s*([日月火水木金土])'
        
        matches = re.findall(pattern, full_text)
        
        if not matches:
            return None, None, "日付情報が見つかりませんでした。"
            
        # 抽出したリストから「日付部分」を数値に変換し、最大値を取得
        # これにより「68」のような誤検出を無視し、正しい最終日（31など）だけを残す
        valid_dates = []
        for d, day in matches:
            valid_dates.append((int(d), day))
            
        # 日付でソートして最大値を取得
        valid_dates.sort(key=lambda x: x[0])
        last_date, last_day = valid_dates[-1]
        
        return last_date, last_day, None
            
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# --- UI構築 ---
st.title("シフト表自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        last_date, last_day, error = extract_correct_date_robust(uploaded_pdf)
        
        if error:
            st.error(error)
        else:
            st.success("解析成功")
            st.write(f"最終日付: {last_date}日")
            st.write(f"最終曜日: {last_day}曜日")
