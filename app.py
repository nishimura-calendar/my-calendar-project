import streamlit as st
import practice_0 as p0

def main():
    st.title("シフトカレンダー管理システム")
    
    # 1. ファイルアップロード
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        # データ読み込み処理
        pdf_df, status = p0.load_and_validate_pdf(uploaded_file, 2026, 6)
        
        if status == "通過":
            # 2. データ確認（[2]終了時の表示）
            st.success("PDF読み込みおよび検証完了")
            
            # 各データの表示
            st.write("### time_schedule (時程表)")
            st.dataframe(st.session_state.time_dic)
            
            # ここでtarget_staffを選択させて抽出結果を表示
            # （app (4).pyのロジックと同様）
            
        else:
            st.error(status)
            # 必要に応じてPDFプレビュー表示関数を呼び出し

if __name__ == "__main__":
    main()
