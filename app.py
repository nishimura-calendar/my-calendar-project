import streamlit as st
import pandas as pd
import pdfplumber

st.title("シフト表解析アプリ")

# 1. ファイルアップロードボタン
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
            
            # 2. キー（T1/T2）の位置を自動特定
            row, col = find_key_position(df_pdf)
            
            if row is not None:
                st.success(f"キー '{df_pdf.iloc[row, col]}' を {row}行目, {col}列目で発見しました！")
                
                # キーの行を基準にデータを整理（その次の行から開始）
                df_data = df_pdf.iloc[row+1:, :].reset_index(drop=True)
                
                st.write("### 抽出されたデータ（キー以降）")
                st.dataframe(df_data)
                
                # 3. 0列目を抽出して表示
                column_zero = df_data.iloc[:, 0]
                
                st.write("### 0列目の全データ (リスト形式)")
                st.write(column_zero.tolist())
                
                st.write("### 0列目の詳細 (クリーン版)")
                cleaned_zero = column_zero.dropna()
                st.dataframe(cleaned_zero)
            else:
                st.error("PDF内に 'T1' または 'T2' が見つかりませんでした。")
        else:
            st.error("PDFから表を読み込めませんでした。")
