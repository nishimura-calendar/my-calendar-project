import streamlit as st
import pandas as pd
import io
import practice_0 as p0

def main():
    st.set_page_config(page_title="勤務地基準解析システム", layout="wide")
    
    # セッション管理
    if 'staff_name' not in st.session_state:
        st.session_state.staff_name = "西村 文宏"

    st.title("📋 勤務地基準・シフト解析 (Camelot実装)")
    st.info("PDFの『勤務地(T1/T2)』を構造のアンカーとして解析します。")

    with st.sidebar:
        st.header("基本設定")
        target_name = st.text_input("スタッフ名", value=st.session_state.staff_name)
        st.session_state.staff_name = target_name
        # デフォルトの時程表SS ID
        ss_id = st.text_input("時程表スプレッドシートID", value="1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE")

    uploaded_pdf = st.file_uploader("シフト表PDFをアップロード", type="pdf")

    if uploaded_pdf and target_name:
        pdf_stream = io.BytesIO(uploaded_pdf.read())
        
        try:
            with st.spinner("Camelotエンジンで勤務地・シフトを抽出中..."):
                # 1. PDF解析 (practice_0.py)
                pdf_results, year, month = p0.pdf_reader(pdf_stream, target_name)
            
            if not pdf_results:
                st.error("勤務地またはスタッフ名が特定できませんでした。")
                return

            st.success(f"解析完了: {year}年{month}月度")

            # 2. 時程表取得 (Google Sheets)
            try:
                service = p0.get_sheets_service(st.secrets)
                time_schedule_map = p0.fetch_time_schedule(service, ss_id)
            except:
                st.warning("時程表の取得に失敗しました。シフト名のみで生成します。")
                time_schedule_map = {}

            # 3. データの統合 (PDFシフト + 時程表)
            integrated = {}
            for loc, data in pdf_results.items():
                # 時程表側は T1, T2 等で登録されている想定
                integrated[loc] = {
                    "pdf": data,
                    "times": time_schedule_map.get(loc.upper(), [])
                }

            # 4. カレンダー形式への変換
            rows = p0.build_calendar_df(integrated, year, month)

            if rows:
                df_final = pd.DataFrame(rows, columns=[
                    "Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"
                ])
                
                st.subheader("抽出結果プレビュー")
                st.dataframe(df_final, use_container_width=True)
                
                csv_buffer = df_final.to_csv(index=False, encoding="utf_8_sig")
                st.download_button(
                    label="📥 Googleカレンダー用CSVをダウンロード",
                    data=csv_buffer,
                    file_name=f"shift_{year}_{month}_{target_name}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    type="primary"
                )
            else:
                st.warning("有効なシフト行が生成されませんでした。")

        except Exception as e:
            st.error(f"実行エラー: {e}")
            st.exception(e)

if __name__ == "__main__":
    main()
