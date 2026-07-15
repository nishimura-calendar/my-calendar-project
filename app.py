import streamlit as st
import pandas as pd
import io
import re
import camelot
import unicodedata

# (前述の get_service, format_time, load_time_schedule_data は省略せずそのまま使用してください)

st.title("シフトカレンダー管理システム")

# [1] 時程表読み込み
time_schedules = load_time_schedule_data()

# [2] PDFアップロード
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_file is not None:
    # PDF保存と読み込み
    with open("temp.pdf", "wb") as f: f.write(uploaded_file.getbuffer())
    tables = camelot.read_pdf("temp.pdf", pages='1')
    
    # [第1関門] 年月チェック (省略) ...
    
    # [第2関門] keyの存在確認
    found_key = False
    # PDFの0列目を正規化して検索対象にする
    pdf_col = [unicodedata.normalize('NFKC', str(val)).replace(" ", "") for val in tables[0].df.iloc[:, 0]]
    
    for key in time_schedules.keys():
        n_key = unicodedata.normalize('NFKC', str(key)).replace(" ", "")
        if any(n_key in cell for cell in pdf_col):
            found_key = True
            break
            
    if not found_key:
        st.error("シフト表ではないようです。確認して下さい。")
        st.pdf(uploaded_file)
        st.stop()
    else:
        st.success("有効なシフト表として確認されました。")
