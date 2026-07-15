import streamlit as st
import pandas as pd
import io
import re
import camelot
import unicodedata

# --- [1] 年月抽出ロジックの修正 ---
def extract_date_from_filename(filename):
    # 4桁の数字（年）と、その後の何らかの文字を経て「〇月」となっているパターンを抽出
    # 例: "免税店シフト表 1月度 第1ターミナル 2026.pdf"
    # 1. (\d{4}) で4桁の年を検索
    # 2. (\d+)月 で月の数字を検索
    year_match = re.search(r'(\d{4})', filename)
    month_match = re.search(r'(\d+)月', filename)
    
    year = year_match.group(1) if year_match else None
    month = month_match.group(1) if month_match else None
    return year, month

# --- メイン処理内での呼び出し部分 ---
# [2] PDFアップロード
st.subheader("[2] シフト表ファイルアップロード")
uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # A: ファイル名からの年月取得
    file_year, file_month = extract_date_from_filename(uploaded_file.name)
    
    if file_year and file_month:
        st.write(f"ファイル名から **{file_year}年{file_month}月** を検出しました。")
    else:
        st.warning("ファイル名から年月を特定できませんでした。")
        # ユーザーによる手動入力フォーム
        year_month = st.text_input("年月を入力してください (例: 2026年1月)")
        if year_month:
            # 入力があった場合の処理をここに記述
            pass
        else:
            st.stop() # 年月が確定するまでここで停止
