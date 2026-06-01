import streamlit as st
import practice_0 as p0
import fitz  # PyMuPDF
import os

def display_pdf_as_image(pdf_path):
    """PDFを画像に変換して画面に表示する（既存の仕様通り）"""
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        st.image(img_bytes, caption="アップロードされたPDFの確認", use_container_width=True)
        doc.close()
    except Exception as e:
        st.warning(f"PDFプレビューの生成に失敗しました: {e}")

st.title("シフトカレンダー作成システム")
st.subheader("[2]．pdfシフト表ファイル読込 〈1〉")

# 1. pdfシフト表ファイルをアップロード
uploaded_file = st.file_uploader("pdfシフト表ファイルをアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    # 一時ファイルとして保存してパスを取得
    temp_path = os.path.join("temp_" + uploaded_file.name)
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    st.success(f"ファイル「{uploaded_file.name}」がアップロードされました。")
    
    # 事前にPDFを表示（仕様：「このファイルを使用しますか？ファイルの年月を入力してください。」）
    display_pdf_as_image(temp_path)
    
    st.write("---")
    st.write("### 第１関門チェック")
    
    # ユーザー入力フォーム（ファイル名から自動取得できない場合、または確認用）
    st.write("※ファイル名から年月が正しく認識されない場合は、以下に直接入力してください。")
    col1, col2 = st.columns(2)
    with col1:
        manual_year = st.number_input("対象の年（西暦）", min_value=2020, max_value=2030, value=2026)
    with col2:
        manual_month = st.number_input("対象の月", min_value=1, max_value=12, value=1)
        
    # チェックボタン
    if st.button("第1関門をチェックする"):
        res, msg = p0.check_first_gate(temp_path, manual_year, manual_month)
        
        if msg == "通過":
            st.success(f"【第1関門通過】 {res['year']}年{res['month']}度のチェックに成功しました。そのまま通過します。")
            # セッション状態に保存して次のステップ（〈2〉）へ引き継げる状態にする
            st.session_state.first_gate_passed = True
            st.session_state.target_year = res['year']
            st.session_state.target_month = res['month']
            st.session_state.pdf_df = res['df']
        else:
            # A≠Bなら理由を表示してプログラム停止（警告表示）
            st.error(f"【プログラム停止】 第1関門を通過できませんでした。")
            st.info(f"理由: {msg}")
            
    # 一時ファイルの削除クリーンアップ（必要に応じて）
    if os.path.exists(temp_path):
        os.remove(temp_path)
