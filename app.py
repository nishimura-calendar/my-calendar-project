import streamlit as st
import practice_0 as p0
import io
import pandas as pd

def main():
    st.set_page_config(page_title="シフト・時程表 統合システム", layout="wide")
    st.title("📅 シフト・時程表 勤務地紐付けシステム")

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
        if st.button("データ解析・紐付け開始"):
            with st.spinner("解析および紐付け中..."):
                # 1. Excel（時程表）の読み込み
                time_dic = p0.read_excel_schedule(excel_file)
                
                # 2. PDFの読み込み
                pdf_stream = io.BytesIO(pdf_file.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                if not pdf_dic:
                    st.error(f"PDF内に「{target_staff}」のデータが見つかりませんでした。")
                    return

                # 3. データの統合 (紐付け処理)
                final_data = p0.data_integration(pdf_dic, time_dic)
                
                if not final_data:
                    st.error("❌ PDFとExcelの勤務地名が一致しませんでした。")
                    st.write("PDFから見つかった場所名:", list(pdf_dic.keys()))
                    st.write("Excelから見つかった場所名:", list(time_dic.keys()) if time_dic else "なし")
                    return

                # 4. 結果表示
                st.success("✅ 勤務地による紐付けに成功しました")
                
                for loc, data_list in final_data.items():
                    my_df = data_list[0]
                    other_df = data_list[1]
                    time_df = data_list[2]
                    
                    with st.expander(f"📍 勤務地: {loc} の統合データ", expanded=True):
                        st.subheader(f"【{loc}】シフト・記号情報 (PDF)")
                        
                        # ダウンロード用関数 (BOM付きUTF-8)
                        def convert_df(df):
                            return df.to_csv(index=False, header=False).encode('utf_8_sig')

                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write("👤 自分のシフト・休日")
                            st.dataframe(my_df)
                            st.download_button(
                                label=f"自分のシフト({loc})をCSV保存",
                                data=convert_df(my_df),
                                file_name=f"my_shift_{loc}.csv",
                                mime='text/csv',
                            )
                        with col_b:
                            st.write("👥 同僚のシフト・休日")
                            st.dataframe(other_df)
                            st.download_button(
                                label=f"同僚のシフト({loc})をCSV保存",
                                data=convert_df(other_df),
                                file_name=f"others_shift_{loc}.csv",
                                mime='text/csv',
                            )
                        
                        st.divider()
                        
                        st.subheader(f"【{loc}】対応時程表 (Excelデータ)")
                        st.dataframe(time_df)
                        st.download_button(
                            label=f"時程表({loc})をCSV保存",
                            data=convert_df(time_df),
                            file_name=f"timetable_{loc}.csv",
                            mime='text/csv',
                        )

if __name__ == "__main__":
    main()
