import streamlit as st
import pandas as pd
import io
import practice_0 as p0

def main():
    st.set_page_config(page_title="カレンダー作成ツール", layout="centered")
    
    # セッション状態で年月と名前を保持（リロード対策）
    if 'pdf_year' not in st.session_state: st.session_state.pdf_year = 2024
    if 'pdf_month' not in st.session_state: st.session_state.pdf_month = 4
    if 'staff_name' not in st.session_state: st.session_state.staff_name = "西村 文宏"

    st.title("📅 勤務スケジュール抽出システム")
    st.markdown("PDFのシフト表から自分専用のカレンダー（Googleカレンダー用CSV）を生成します。")

    # --- メインエリアでの設定入力 ---
    st.subheader("1. 基本設定")
    col_name, col_sheet = st.columns([1, 1])
    with col_name:
        target_staff = st.text_input("あなたの名前", value=st.session_state.staff_name)
        st.session_state.staff_name = target_staff
    with col_sheet:
        # デフォルトの時程表IDをセット
        sheet_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    # --- PDFアップロード ---
    st.subheader("2. ファイルのアップロード")
    pdf_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf")

    if pdf_file:
        # PDFを読み込み年月抽出を試みる
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        extracted_y, extracted_m = p0.extract_year_month_from_pdf(pdf_stream)
        
        # PDFから新しい年月が検出された場合の自動更新
        if extracted_y and (extracted_y != st.session_state.pdf_year or extracted_m != st.session_state.pdf_month):
            st.session_state.pdf_year = extracted_y
            st.session_state.pdf_month = extracted_m
            st.success(f"PDFから対象年月を自動判定しました: **{extracted_y}年{extracted_m}月**")
            st.rerun()

        # 現在設定されている年月を表示（修正も可能）
        st.info(f"現在の対象設定: **{st.session_state.pdf_year}年 {st.session_state.pdf_month}月** （PDFから自動取得済み）")
        
        # 手動で微調整したい場合の入力欄
        with st.expander("年月を調整する（自動判定が間違っている場合）"):
            col_y, col_m = st.columns(2)
            st.session_state.pdf_year = col_y.number_input("年", min_value=2024, value=st.session_state.pdf_year)
            st.session_state.pdf_month = col_m.number_input("月", min_value=1, max_value=12, value=st.session_state.pdf_month)

        if st.button("🚀 実行してカレンダーを生成", use_container_width=True, type="primary"):
            try:
                service = p0.get_gdrive_service(st.secrets)
                
                # 1. 時程表の取得
                with st.spinner("Google Driveから時程表データを読み込んでいます..."):
                    time_dic = p0.time_schedule_from_drive(service, sheet_id)
                
                # 2. PDF解析（名前による抽出）
                with st.spinner(f"PDFから {target_staff} さんの勤務を解析中..."):
                    pdf_stream.seek(0)
                    pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                
                if not pdf_dic:
                    st.error(f"PDF内に『{target_staff}』という名前が見つかりませんでした。名前の表記（空白など）を確認してください。")
                    return

                # 3. データの紐付け（勤務地マッチング）
                integrated_dic, logs = p0.data_integration(pdf_dic, time_dic)
                
                # 紐付け結果の簡易表示
                with st.expander("勤務地マッチングのログを表示"):
                    st.table(pd.DataFrame(logs))

                # 4. カレンダー行の生成
                with st.spinner("詳細な時間スケジュールを計算しています..."):
                    final_rows = p0.process_full_month(
                        integrated_dic, 
                        int(st.session_state.pdf_year), 
                        int(st.session_state.pdf_month)
                    )

                if final_rows:
                    st.subheader("3. 生成結果の確認")
                    df_res = pd.DataFrame(final_rows, columns=[
                        "Subject", "Start Date", "Start Time", "End Date", "End Time", 
                        "All Day Event", "Description", "Location"
                    ])
                    
                    st.dataframe(df_res, use_container_width=True)

                    # CSVダウンロード
                    csv_buffer = io.StringIO()
                    df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                    
                    st.download_button(
                        label="📥 Googleカレンダー用CSVをダウンロード",
                        data=csv_buffer.getvalue(),
                        file_name=f"schedule_{st.session_state.pdf_year}{st.session_state.pdf_month:02d}_{target_staff}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.warning("スケジュールが1件も生成されませんでした。PDFのシフト記号が時程表に存在するか確認してください。")
            
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                st.exception(e)

if __name__ == "__main__":
    main()
