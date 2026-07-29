import streamlit as st
import pandas as pd
import pdfplumber

st.title("人名リスト抽出アプリ")

# 1. アップロードボタン
uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

def get_clean_names(df):
    """0列目から名前だけを抽出し、クリーニングしてリストを返す"""
    raw_names = df.iloc[:, 0].dropna().astype(str).tolist()
    clean_names = []
    
    for item in raw_names:
        # キー（T1など）はスキップ
        if "T1" in item or "T2" in item:
            continue
        # 改行コードがある場合はその前までを取得
        name = item.split('\n')[0].strip()
        # 空文字や短すぎる文字列を除外
        if len(name) >= 2 and name not in clean_names:
            clean_names.append(name)
            
    return clean_names

if uploaded_pdf:
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        table = page.extract_table()
        
        if table:
            df_pdf = pd.DataFrame(table)
            
            # 人名リスト作成
            clean_names = get_clean_names(df_pdf)
            
            # 2. 人名選択メニューの表示
            if clean_names:
                selected_name = st.selectbox("シフトを確認する人を選択してください", clean_names)
                st.write(f"選択された人: **{selected_name}**")
            else:
                st.warning("人名が抽出できませんでした。")
        else:
            st.error("表データが見つかりませんでした。")
