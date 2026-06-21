import streamlit as st
from practice_0 import process_pdf_shift, generate_calendar_csv

st.title("シフトカレンダー作成システム")

# 1. PDFアップロード
uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    # PDFを一時保存してパスを生成
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    st.write("ファイルを確認しました。処理を開始します。")
    
    # 2. ボタン操作で処理開始
    if st.button("CSV生成とGoogleドライブ保存"):
        # ロジック呼び出し
        result = process_pdf_shift("temp.pdf", "山田太郎")
        
        # CSV生成
        csv_file = generate_calendar_csv("T1", "山田太郎", result, {})
        
        # 3. Googleドライブ連携
        # drive_service = get_service() # 認証済みサービス
        # save_to_drive(csv_file, ...)
        
        st.success("完了しました！")
