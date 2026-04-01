import streamlit as st
import practice_0 as p0
import io
import pandas as pd

def main():
    st.set_page_config(page_title="シフト・時程 統合システム", layout="wide")
    
    st.title("📅 シフト・時程表 統合表示 (Excel版)")
    st.info("PDF(勤務表)とExcel(時程表)の両方をアップロードしてください。API設定は不要です。")

    # サイドバー設定
    st.sidebar.header("検索設定")
    target_staff = st.sidebar.text_input("検索する氏名", value="田坂 友愛")
    
    col1, col2 = st.columns(2)
    with col1:
        pdf_file = st.file_uploader("1. 勤務表PDFをアップロード", type="pdf")
    with col2:
        excel_file = st.file_uploader("2. 時程表Excelをアップロード", type=["xlsx", "xls"])

    if pdf_file and excel_file and target_staff:
        if st.button("解析と紐付けを実行"):
            with st.spinner("データを解析中..."):
                # 1. Excelから時程表データを取得
                time_dic = p0.extract_time_schedule_from_excel(excel_file)
                
                # 2. PDFから個人シフトを抽出
                pdf_stream = io.BytesIO(pdf_file.read())
                pdf_dic = p0.pdf_reader(pdf_stream, target_staff)

                # 解析状況の表示
                st.subheader("🔍 解析状況の確認")
                c_pdf, c_xls = st.columns(2)
                with c_pdf:
                    st.write("**PDFの勤務地:**")
                    if pdf_dic:
                        for k in pdf_dic.keys(): st.success(f"✅ {k}")
                    else: st.error("氏名が見つかりません")
                with c_xls:
                    st.write("**Excelの勤務地:**")
                    if time_dic:
                        for k in time_dic.keys(): st.success(f"✅ {k}")
                    else: st.error("勤務地(T1,T2等)が見つかりません")

                # 3. 紐付け処理
                final_data = p0.data_integration(pdf_dic, time_dic)
                
                if final_data:
                    for loc_key, content in final_data.items():
                        st.divider()
                        st.header(f"📍 拠点: {loc_key}")
                        
                        tab1, tab2 = st.tabs(["📋 あなたの予定", "⏱ 全体時程"])
                        with tab1:
                            st.subheader("本日のシフト")
                            st.dataframe(content[0], use_container_width=True)
                            st.subheader("同じ拠点のメンバー")
                            st.dataframe(content[1], use_container_width=True)
                        with tab2:
                            st.subheader("拠点のタイムスケジュール")
                            st.dataframe(content[2], use_container_width=True)
                else:
                    if pdf_dic and time_dic:
                        st.warning("勤務地名が一致しないため紐付けできませんでした。")

    else:
        st.info("左側のサイドバーで氏名を確認し、2つのファイルをアップロードしてください。")

if __name__ == "__main__":
    main()
