import pdfplumber
import pandas as pd
import streamlit as st

st.title("人名抽出テスト")
uploaded_pdf = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_pdf:
# [2]〈2〉①～③を実装する処理フロー
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        
        # ① アンカーから表の開始位置を整理
        t1_word = next(w for w in page.extract_words() if "T1" in w["text"])
        bbox = (0, t1_word["bottom"], page.width, page.height)
        df_pdf = pd.DataFrame(page.crop(bbox).extract_table())
    
        # ② 列の役割を整理して特定
        # 3列目以降に日付が並んでいる前提で、その左を人名列と判定
        date_col_idx = 3 # 3列目から日付が始まる場合
        name_col_idx = date_col_idx - 1 
        
        # ③ 整理されたロジックで抽出実行
        all_staff_names = df_pdf.iloc[2:, name_col_idx].dropna().tolist()
