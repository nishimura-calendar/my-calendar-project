import streamlit as st
import pandas as pd
import pdfplumber

st.title("シフト表解析アプリ")

# 1. ファイルアップロードボタンの表示
uploaded_pdf = st.file_uploader("シフト表PDFをアップロードしてください", type="pdf")

def find_key_position(df):
    """DataFrameの中から 'T1' または 'T2' を探し、位置を返す"""
    for row_idx in range(df.shape[0]):
        for col_idx in range(df.shape[1]):
            val = str(df.iloc[row_idx, col_idx])
            if "T1" in val or "T2" in val:
                return row_idx, col_idx
    return None, None

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        # 表を抽出
        table = page.extract_table()
        if table:
            df_pdf = pd.DataFrame(table)
            
# 0列目（人名や管理情報が入っているはずの列）を抽出
                column_zero = df_data.iloc[:, 0]
                
                st.write("### 0列目の全データ")
                # ストリームライトでリストとして表示
                st.write(column_zero.tolist())
                
                # デバッグ用にデータフレーム形式で表示（空文字などを除外して確認）
                st.write("### 0列目の詳細（クリーン版）")
                cleaned_zero = column_zero.dropna()
                st.dataframe(cleaned_zero)
