import streamlit as st
import camelot
import os

def main():
    st.title("シフトカレンダー作成システム")
    
    # 【アップロードボタンの表示】
    # この関数でファイル選択ボタンとドラッグ＆ドロップ領域が表示されます
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    # ファイルがアップロードされたら処理を開始
    if uploaded_file is not None:
        st.write(f"ファイル名: {uploaded_file.name}")
        
        # 実行ボタンの配置
        if st.button("実行"):
            # 一時ファイルとして保存
            temp_path = "temp_shift.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # PDFの内容を表示するロジック（整合性確認用）
            try:
                tables = camelot.read_pdf(temp_path, pages='1', flavor='stream')
                if tables:
                    st.success("PDFを読み込みました。")
                    st.dataframe(tables[0].df) # 加工なしで表示
                else:
                    st.warning("テーブルを検出できませんでした。")
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
            
            # 処理後にファイルを削除
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
