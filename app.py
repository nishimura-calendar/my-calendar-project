import streamlit as st
import practice_0 as p0
import io

def main():
    st.set_page_config(page_title="シフト・時程表 確認ツール", layout="wide")
    st.title("📅 シフト・時程表 独立出力システム")

    # サイドバー：設定
    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("検索する氏名を入力", value="田坂 友愛")
    
    # ファイルアップロード
    col1, col2 = st.columns(2)
    with col1:
        pdf_file = st.file_uploader("勤務表PDFをアップロード", type="pdf")
    with col2:
        excel_file = st.file_uploader("時程表Excelをアップロード", type=["xlsx", "xls"])

    if pdf_file or excel_file:
        if st.button("データ解析開始"):
            # --- 1. PDFデータの解析と表示 ---
            if pdf_file and target_staff:
                st.header("📋 PDF勤務表からの抽出結果")
                with st.spinner("PDFを解析中..."):
                    pdf_stream = io.BytesIO(pdf_file.read())
                    pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                    
                    if not pdf_dic:
                        st.warning(f"PDF内に「{target_staff}」のデータが見つかりませんでした。")
                    else:
                        for loc, data_list in pdf_dic.items():
                            with st.expander(f"📍 PDF場所名: {loc}", expanded=True):
                                st.subheader("自分のシフト")
                                st.dataframe(data_list[0])
                                st.subheader("同僚のシフト")
                                st.dataframe(data_list[1])
            
            st.divider()

            # --- 2. Excelデータの解析と表示 ---
            if excel_file:
                st.header("⏱️ Excel時程表からの抽出結果")
                with st.spinner("Excelを解析中..."):
                    # streamをリセット（念のため）
                    excel_file.seek(0)
                    time_dic = p0.read_excel_schedule(excel_file)
                    
                    if not time_dic:
                        st.warning("Excelから時程表データを抽出できませんでした。")
                    else:
                        for loc, df_table in time_dic.items():
                            with st.expander(f"⏰ Excel場所名: {loc}", expanded=False):
                                st.dataframe(df_table)

if __name__ == "__main__":
    main()
