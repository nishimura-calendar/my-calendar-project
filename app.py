import streamlit as st
import practice_0 as p0
import camelot
import os
import re

st.set_page_config(layout="wide")
st.title("📅 シフト・時程表 統合システム")

uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
target_staff = st.text_input("検索する氏名", value="四村 和義")

if uploaded_file and st.button("解析実行"):
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # --- 打ち合わせ通りのロジック：勤務地と名前を比較 ---
    # 日本語1文字15pt + マージン
    name_width = len(target_staff) * 15 + 20
    location_width = 10 * 15 + 20 # 勤務地(目安10文字分)
    
    # 120は含めず、純粋にどちらか長い方を境界線にする
    column_boundary = max(name_width, location_width)
    
    # 安全策：100を超えると日付を飲み込むリスクが高いため上限を設ける
    if column_boundary > 90:
        column_boundary = 90

    try:
        tables = camelot.read_pdf(
            "temp.pdf", 
            pages='1', 
            flavor='stream', 
            columns=[str(column_boundary)]
        )
        
        if not tables:
            st.error("表を検出できませんでした。")
        else:
            # 解析エンジン呼び出し
            p0.pdf_reader(uploaded_file.name, tables[0].df, target_staff)
            
    except Exception as e:
        st.error(f"解析中にエラーが発生しました: {e}")
