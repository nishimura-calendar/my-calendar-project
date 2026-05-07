import streamlit as st
import practice_0 as p0
import fitz

def stop_with_pdf(msg, pdf_path):
    """エラー表示・PDFプレビュー・プログラム停止"""
    st.error(msg)
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    st.image(pix.tobytes("png"), caption="不一致内容の確認")
    st.stop()

st.title("第2関門：勤務地(location)特定工程")

uploaded_file = st.file_uploader("PDFアップロード", type="pdf")

if uploaded_file:
    pdf_path = "temp.pdf"
    with open(pdf_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    # ※本来はファイル名からy, mを取得
    y, m = 2026, 5 

    # 第1・第2関門の解析実行
    res, msg = p0.analyze_pdf_structure(pdf_path, y, m)
    
    if not res:
        stop_with_pdf(msg, pdf_path)
    
    location = res['location']
    
    # 第2関門：時程表(session_state.time_dic)のキーと照合
    if location not in st.session_state.time_dic:
        stop_with_pdf(f"第2関門不通過：【{location}】は時程表に設定されていません。", pdf_path)
    
    st.success(f"第2関門通過：勤務地は「{location}」と判定されました。")
    
    # 次の第3関門へ進む
    st.session_state.current_location = location
    st.session_state.processed_df = res['df']
    st.session_state.staff_list = res['staff_list']
