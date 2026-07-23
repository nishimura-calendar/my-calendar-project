import streamlit as st
import camelot
import re
import tempfile
import os

def extract_last_date_and_day(uploaded_file):
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tfile.write(uploaded_file.read())
    tfile.close()
    
    try:
        # streamモードで読み込み
        tables = camelot.read_pdf(tfile.name, flavor='stream', pages='all')
        
        for table in tables:
            df = table.df
            # テーブル内を走査
            for i in range(len(df) - 1): # 最終行以外をループ
                row_text = " ".join([str(cell) for cell in df.iloc[i]])
                
                # T1 または T2 が見つかった場合
                if re.search(r"T[12]", row_text):
                    # その行（日付行）と次の行（曜日行）を取得
                    date_row = df.iloc[i].values
                    day_row = df.iloc[i+1].values
                    
                    # 数字と曜日のペアを探す
                    pairs = []
                    for j in range(len(date_row)):
                        # 日付が数字（1-31）か確認
                        if re.match(r'^\d{1,2}$', str(date_row[j]).strip()):
                            day = str(day_row[j]).strip()
                            # 曜日っぽい文字があればペアとして保存
                            if re.match(r'^[日月火水木金土]$', day):
                                pairs.append((int(date_row[j]), day))
                    
                    if pairs:
                        # 日付でソートして最後を返す
                        pairs.sort(key=lambda x: x[0])
                        return pairs[-1]
        
        return None, None
    finally:
        if os.path.exists(tfile.name):
            os.remove(tfile.name)

# UI
st.title("シフト表自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    with st.spinner('解析中...'):
        last_date, last_day = extract_last_date_and_day(uploaded_pdf)
        if last_date:
            st.success("解析成功")
            st.write(f"最終日付: {last_date}日")
            st.write(f"最終曜日: {last_day}曜日")
        else:
            st.error("日付と曜日を特定できませんでした。")
