import streamlit as st
import camelot
import re
import pandas as pd

# [1] 時程表読込 (ダミー関数: 実際は辞書を読み込んでくる)
def get_valid_keys():
    # 実際の実装では、ここでスプレッドシートから読み込んだ辞書のKeyを返す
    return ["T1", "T2"]

# [2] PDFシフト表ファイル読込（Streamlit対応版）
def process_pdf_shift(pdf_file, valid_keys):
    # ファイル保存（camelot用）
    with open("temp.pdf", "wb") as f:
        f.write(pdf_file.getbuffer())

    # (1) camelotを使用して読込
    tables = camelot.read_pdf("temp.pdf", pages='1', flavor='stream')
    full_text_lines = []
    for table in tables:
        full_text_lines.extend(table.df.astype(str).values.tolist())

    # (2) 第1関門: Key検索
    found_key = None
    key_line_index = -1
    
    for i, line in enumerate(full_text_lines):
        line_str = "".join(line)
        for key in valid_keys:
            if re.sub(r'[\s ]', '', key) in re.sub(r'[\s ]', '', line_str):
                found_key = key
                key_line_index = i
                break
        if found_key: break
    
    if not found_key:
        st.error(f"“key”が見当りません。シフト表ではないようです。ファイルを確認して下さい。")
        st.stop() # プログラム停止

    # (3) 第2関門: 日付と曜日の紐付け
    # インデックスのズレを考慮 (Key行+1=日付, Key行+2=曜日)
    if key_line_index + 2 >= len(full_text_lines):
        st.error("PDFの構造が不正です。日付・曜日行が見つかりません。")
        st.stop()

    date_line = full_text_lines[key_line_index + 1]
    day_line = full_text_lines[key_line_index + 2]
    
    # 日付リスト・曜日リスト抽出
    dates = [int(s) for s in re.findall(r'\d+', " ".join(date_line)) if s.isdigit()]
    days = [s for s in re.findall(r'[日月火水木金土]', " ".join(day_line))]
    
    if not dates or not days:
        st.error("日付または曜日ブロックが抽出できませんでした。")
        st.stop()
        
    return {"key": found_key, "last_date": dates[-1], "last_day": days[-1]}

# StreamlitメインUI
st.title("シフト表自動読込プログラム")

uploaded_file = st.file_uploader("PDFシフト表ファイルをアップロード", type="pdf")
if uploaded_file:
    keys = get_valid_keys()
    result = process_pdf_shift(uploaded_file, keys)
    
    if result:
        st.success(f"成功: {result['key']} を検出しました。")
        st.write(f"最終日付: {result['last_date']}, 最終曜日: {result['last_day']}")
