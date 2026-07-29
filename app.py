import pdfplumber
import pandas as pd
import streamlit as st

st.title("人名抽出テスト")
uploaded_pdf = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        # 1ページ目を読み込み
        page = pdf.pages[0]
        # 表を抽出
        table = page.extract_table()
        
        if table:
            df = pd.DataFrame(table)
            
            # --- 人名抽出のロジック ---
            # 2列目（index 1）に名前があるはずなので、そこを抽出します
            name_column = df.iloc[:, 1] 
            
            # リスト化して整形
            name_list = []
            for val in name_column:
                # 文字列に変換し、空白を除去
                name = str(val).strip()
                # Noneや空文字、短すぎる文字列を除外
                if name != "None" and len(name) >= 2:
                    name_list.append(name)
            
            # 結果を表示
            st.write("### 抽出された人名リスト")
            st.write(name_list)
            
            # デバッグ用に元データも表示
            st.write("### (参考) 読み込んだテーブルデータの一部")
            st.dataframe(df.head(10))
        else:
            st.error("表が抽出できませんでした。")
