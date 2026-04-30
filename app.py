import streamlit as st
import pandas as pd
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="シフト解析システム", layout="wide")
st.title("📄 PDFシフト解析と時程照合")

# マスター読み込み
drive_service, sheets_service = p0.get_unified_services()
if sheets_service:
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    time_dic = st.session_state.time_dic

    # 入力フォーム
    col1, col2 = st.columns(2)
    with col1:
        target_name = st.text_input("抽出するスタッフ名を入力してください", value="自分")
    with col2:
        uploaded_file = st.file_uploader("PDFファイルをアップロードしてください", type="pdf")

    if uploaded_file and target_name:
        # 解析実行
        result, error_msg = p0.process_pdf_data(uploaded_file, target_name, time_dic)
        
        if error_msg:
            st.error(error_msg)
            st.stop() # 指示に基づきプログラム停止
        
        if result:
            st.success(f"照合成功：拠点「{result['key']}」のデータを抽出しました。")
            
            # 4. 表形式で表示
            st.header("📊 抽出データ確認")
            
            # 表示用にDataFrameを作成
            display_df = pd.DataFrame([
                result['time_schedule'],
                result['my_daily_shift'],
                result['other_daily_shift']
            ], index=["時程 (time_schedule)", "自分のシフト (my_daily_shift)", "他者のシフト (other_daily_shift)"])
            
            st.dataframe(display_df, use_container_width=True)
            
            st.info(f"拠点「{result['key']}」の辞書登録が完了しました。続けて解析ステップに進めます。")
