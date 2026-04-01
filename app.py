import streamlit as st
import practice_0 as p0
import io

def main():
    st.set_page_config(page_title="シフト管理システム", layout="wide")
    st.title("📅 シフト・カレンダー統合システム")

    # サイドバー：設定
    st.sidebar.header("設定")
    target_staff = st.sidebar.text_input("検索する氏名を入力", value="田坂 友愛")
    
    # ファイルアップロード
    col1, col2 = st.columns(2)
    with col1:
        pdf_file = st.file_uploader("勤務表PDFをアップロード", type="pdf")
    with col2:
        excel_file = st.file_uploader("時程表Excelをアップロード", type=["xlsx", "xls"])

    if pdf_file and excel_file and target_staff:
        if st.button("データ解析開始"):
            with st.spinner("解析中..."):
                # Excel読み込み
                time_dic = p0.read_excel_schedule(excel_file)
                
                # PDF読み込み
                pdf_stream = io.BytesIO(pdf_file.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                if not pdf_dic:
                    st.error(f"指定された氏名「{target_staff}」がPDF内に見つかりませんでした。")
                    return

                # 統合
                final_data = p0.data_integration(pdf_dic, time_dic)
                
                if not final_data:
                    st.warning("PDFとExcelの勤務地名（T1, T2など）が一致しませんでした。")
                    return

                # 結果表示
                st.success("解析完了！")
                for loc, data_list in final_data.items():
                    st.subheader(f"📍 勤務地: {loc}")
                    st.write("### 自分のシフト")
                    st.dataframe(data_list[0])
                    st.write("### 同僚のシフト（他人のデータ）")
                    st.dataframe(data_list[1])
                    st.write("### 対応する時程表")
                    st.dataframe(data_list[2])

if __name__ == "__main__":
    main()
