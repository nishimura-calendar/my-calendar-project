import streamlit as st
import pandas as pd
import pdfplumber

st.title("シフト表解析アプリ（0列目抽出版）")

uploaded_pdf = st.file_uploader("シフト表PDFをアップロードしてください", type="pdf")

def find_key_position(df):
    for row_idx in range(df.shape[0]):
        for col_idx in range(df.shape[1]):
            val = str(df.iloc[row_idx, col_idx])
            if "T1" in val or "T2" in val:
                return row_idx, col_idx
    return None, None

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        table = page.extract_table()
        
        if table:
            df_pdf = pd.DataFrame(table)
            row, col = find_key_position(df_pdf)
            
            if row is not None:
                # 1. キー行の次からデータを取得
                df_data = df_pdf.iloc[row+1:, :].reset_index(drop=True)
                
                # 2. 【重要】0列目だけを抽出（他の列はすべて破棄）
                df_names = df_data.iloc[:, [0]]
                
                # 3. Noneや空文字を除去して表示
                df_clean = df_names.dropna().replace("", pd.NA).dropna()
                
                st.write("### 抽出された0列目（人名リスト等）")
                st.dataframe(df_clean)
                
                # 必要であればリスト化して表示
                st.write("### リスト表示")
                st.write(df_clean.iloc[:, 0].tolist())
                
            else:
                st.error("PDF内に 'T1' または 'T2' が見つかりませんでした。")
        else:
            st.error("PDFから表を読み込めませんでした。")
