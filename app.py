import streamlit as st
import pandas as pd
import io
import practice_0 as p0

def main():
    st.set_page_config(page_title="シフト抽出ツール", layout="wide")
    
    # セッション状態の初期化
    if 'pdf_year' not in st.session_state: st.session_state.pdf_year = 2026
    if 'pdf_month' not in st.session_state: st.session_state.pdf_month = 4
    if 'staff_name' not in st.session_state: st.session_state.staff_name = "田坂 友愛"

    st.title("🛡️ 関空免税店シフト抽出システム")
    st.markdown("PDFのシフト表からGoogleカレンダー用CSVを生成します。")
    
    # --- サイドバー設定 ---
    with st.sidebar:
        st.header("⚙️ 設定")
        target_staff = st.text_input("抽出する名前", value=st.session_state.staff_name)
        st.session_state.staff_name = target_staff
        
        sheet_id = st.text_input("時程表シートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")
        
        st.divider()
        st.subheader("📅 対象年月の手動設定")
        # 打ち合わせ通り、ここでユーザーが年月を確定させます
        sel_year = st.number_input("年", value=st.session_state.pdf_year, min_value=2024, max_value=2030)
        sel_month = st.number_input("月", value=st.session_state.pdf_month, min_value=1, max_value=12)
        
        st.session_state.pdf_year = sel_year
        st.session_state.pdf_month = sel_month

    # --- メインコンテンツ ---
    st.subheader("1. ファイルのアップロード")
    pdf_file = st.file_uploader("シフト表（PDF）を選択してください", type="pdf")

    if pdf_file:
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)

        # 内部的に年月の自動抽出は行うが、表示はせず初期値の参考程度に留める（打ち合わせ通り）
        p0.extract_year_month_from_pdf(pdf_stream)
        
        st.info(f"📁 ファイル名: {pdf_file.name} を受理しました。\n設定された年月（{st.session_state.pdf_year}年{st.session_state.pdf_month}月）で処理します。")

        if st.button("CSVを作成する", type="primary", use_container_width=True):
            try:
                with st.spinner("データの照合中..."):
                    # Google Drive 認証
                    try:
                        service = p0.get_gdrive_service(st.secrets)
                    except Exception:
                        st.error("Google Driveへの認証に失敗しました。Secretsの設定を確認してください。")
                        return

                    # 1. PDF読み込み (2行セットのmy_dailyとothersを抽出)
                    pdf_dic = p0.pdf_reader(pdf_stream, target_staff)
                    if not pdf_dic:
                        st.warning(f"「{target_staff}」さんのシフトがPDF内に見つかりませんでした。名前の表記が正しいか確認してください。")
                        return
                    
                    # 2. 時程表取得
                    time_schedule_dic = p0.time_schedule_from_drive(service, sheet_id)
                    if not time_schedule_dic:
                        st.warning("スプレッドシートから時程データが取得できませんでした。")
                        return
                    
                    # 3. データ統合 (勤務地名で紐付け)
                    integrated_dic, logs = p0.data_integration(pdf_dic, time_schedule_dic)
                    
                    # 4. 月間処理 (サイドバーで指定された年月を確実に使用)
                    final_rows = p0.process_full_month(
                        integrated_dic, 
                        int(st.session_state.pdf_year), 
                        int(st.session_state.pdf_month)
                    )

                    if final_rows:
                        st.subheader("2. 抽出結果プレビュー")
                        df_res = pd.DataFrame(final_rows, columns=[
                            "Subject", "Start Date", "Start Time", "End Date", "End Time", 
                            "All Day Event", "Description", "Location"
                        ])
                        
                        st.dataframe(df_res, use_container_width=True)

                        # CSV生成
                        csv_buffer = io.StringIO()
                        df_res.to_csv(csv_buffer, index=False, encoding="utf_8_sig")
                        
                        st.download_button(
                            label="📥 Googleカレンダー用CSVをダウンロード",
                            data=csv_buffer.getvalue(),
                            file_name=f"shift_{st.session_state.pdf_year}_{st.session_state.pdf_month:02d}_{target_staff}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                        
                        # 紐付けログ（デバッグ用）
                        with st.expander("詳細ログを表示"):
                            st.table(pd.DataFrame(logs))
                    else:
                        st.warning(f"{st.session_state.pdf_month}月の期間内に有効な勤務シフト（休以外）が見つかりませんでした。日付列が正しく認識されているか確認してください。")
            
            except Exception as e:
                # ユーザーには分かりやすく表示し、技術的詳細は隠す
                st.error(f"解析中に問題が発生しました。ファイル形式やシートの設定を確認してください。")
                with st.expander("デバッグ用エラー詳細"):
                    st.exception(e)

if __name__ == "__main__":
    main()
