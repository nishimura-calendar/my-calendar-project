import streamlit as st
import camelot
import os

# [2] PDFシフト表ファイル読込
def process_pdf_shift_camelot(uploaded_pdf):
    # ファイルを一時的に保存 (Camelotはファイルパスを必要とするため)
    with open("temp_shift.pdf", "wb") as f:
        f.write(uploaded_pdf.getbuffer())
    
    # (1) Camelotを使用して読込
    # flavor='lattice'は罫線がある表に適しています
    try:
        tables = camelot.read_pdf("temp_shift.pdf", flavor='lattice', pages='all')
        
        # 読み込んだテーブルデータを確認
        if len(tables) > 0:
            st.success(f"{len(tables)} 個のテーブルを検出しました。")
            # 最初のテーブルをDataFrameとして表示
            df = tables[0].df
            st.write(df)
            return tables
        else:
            st.error("テーブルが検出されませんでした。")
            return None
            
    except Exception as e:
        st.error(f"Camelotでの読み込みエラー: {e}")
        return None
    finally:
        if os.path.exists("temp_shift.pdf"):
            os.remove("temp_shift.pdf")

# Streamlit UI
st.title("シフト表自動読込プログラム")
uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type=["pdf"])

if uploaded_pdf:
    tables = process_pdf_shift_camelot(uploaded_pdf)
    # この後、[2]〈1〉(2) 第1関門へ続く
