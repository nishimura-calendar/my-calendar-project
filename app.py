import streamlit as st
import pandas as pd
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト解析システム", layout="wide")
st.title("📄 PDFシフト解析と時程照合")

# マスターデータの準備
drive_service, sheets_service = p0.get_unified_services()
if sheets_service:
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    time_dic = st.session_state.time_dic

    # 入力
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        target_name = st.text_input("抽出するスタッフ名を入力してください", value="自分")
    with col_in2:
        uploaded_file = st.file_uploader("PDFファイルをアップロードしてください", type="pdf")

    if uploaded_file and target_name:
        # 解析実行
        raw_val, new_location, result = p0.process_pdf_with_cleaning(uploaded_file, target_name, time_dic)
        
        # クレンジングプロセスの確認
        st.subheader("🔍 ステップ1: [0,0]セルの解析確認")
        c1, c2 = st.columns(2)
        with c1:
            st.info(f"**クレンジング前 (生データ):**\n\n`{raw_val}`")
        with c2:
            st.success(f"**クレンジング後 (new_location):**\n\n`{new_location}`")

        # 結果判定
        if isinstance(result, str): # エラーメッセージが返ってきた場合
            st.error(result)
            st.stop()
        
        if result:
            st.success(f"照合成功：拠点「{result['key']}」のデータを抽出しました。")
            
            # 4. 表で表示
            st.header("📊 抽出データ（辞書登録内容）")
            
            # 表データの構成
            final_df = pd.DataFrame([
                result['time_schedule'],
                result['my_daily_shift'],
                result['other_daily_shift']
            ], index=["時程表 (time_schedule)", "自分のシフト (my_daily_shift)", "他者のシフト (other_daily_shift)"])
            
            st.dataframe(final_df, use_container_width=True)
