import streamlit as st
import pandas as pd
import re
import camelot
import os
import practice_0 as p0  # 既存の認証等の関数を利用

def debug_key_search(pdf_file, time_dic):
    temp_path = "debug_temp.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_file.read())
    
    try:
        # flavor='stream' で0列目を重視して読み込み
        tables = camelot.read_pdf(temp_path, pages='1', flavor='stream')
        if not tables:
            st.error("表を検出できませんでした。")
            return
        
        df = tables[0].df
        debug_data = []
        matched_key = None

        # 0列目を1行ずつスキャン
        for i in range(len(df)):
            raw_cell = str(df.iloc[i, 0])
            
            # --- クレンジング処理（決めごとベース） ---
            # 1. 改行をスペースに置換
            text = raw_cell.replace('\n', ' ')
            # 2. 中線（ハイフン等）を空文字に置換（決めごと）
            text = re.sub(r'[-ー―－]', '', text)
            # 3. 日付・曜日・時刻を掃除
            text = re.sub(r'\d{1,2}/\d{1,2}', '', text)
            text = re.sub(r'[月火水木金土日]', '', text)
            text = re.sub(r'\d{1,2}:\d{2}', '', text)
            # 4. 前後の空白を掃除
            clean_text = text.strip()

            # Key判定
            current_found = None
            for k in time_dic.keys():
                if k in clean_text:
                    current_found = k
                    if not matched_key:
                        matched_key = k
                    break
            
            debug_data.append({
                "行番号": i,
                "生データ ([i, 0])": raw_cell,
                "クレンジング後": clean_text,
                "ヒットしたKey": current_found if current_found else "---"
            })

        return pd.DataFrame(debug_data), matched_key

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# --- Streamlit 表示部分 ---
st.title("🔍 0列目 Key検索テスト")

drive_service, sheets_service = p0.get_unified_services()
if sheets_service:
    SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    if 'time_dic' not in st.session_state:
        st.session_state.time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    
    uploaded_file = st.file_uploader("確認したいPDFをアップロード", type="pdf")

    if uploaded_file:
        df_result, final_key = debug_key_search(uploaded_file, st.session_state.time_dic)
        
        if final_key:
            st.success(f"✅ 最終的に特定された拠点Key: **{final_key}**")
        else:
            st.warning("⚠️ Keyが特定できませんでした。")

        st.subheader("📋 0列目のスキャン結果")
        st.table(df_result)
