import streamlit as st
import camelot
import re
import tempfile
import os

def extract_date_from_key_line(uploaded_file):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # CamelotでPDFからテーブルデータを抽出
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        
        # 行ごとに解析
        for table in tables:
            df = table.df
            # テーブルの各行を文字列に変換して検索
            for _, row in df.iterrows():
                row_text = " ".join([str(cell) for cell in row])
                
                # 「T1」または「T2」が含まれる行を探す
                if re.search(r"T[12]", row_text):
                    # その行から「数字（1-31）＋曜日」のペアを全抽出
                    matches = re.findall(r'(\d{1,2})\s+([日月火水木金土])', row_text)
                    
                    if matches:
                        # 抽出したリストから日付でソートして最大値を取得
                        # (数字部分で並び替え)
                        sorted_matches = sorted(matches, key=lambda x: int(x[0]))
                        last_date, last_day = sorted_matches[-1]
                        return int(last_date), last_day
        
        return None, None
        
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# UI構築
st.title("シフト表自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        last_date, last_day = extract_date_from_key_line(uploaded_pdf)
        
        if last_date:
            st.success("解析成功")
            st.write(f"最終日付: {last_date}日")
            st.write(f"最終曜日: {last_day}曜日")
        else:
            st.error("T1/T2行から日付を抽出できませんでした。")
