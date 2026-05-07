import streamlit as st
import pandas as pd
import practice_0 as p0
import fitz
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build('sheets', 'v4', credentials=creds)

st.set_page_config(layout="wide", page_title="Shift Converter")
st.title("シフト解析・カレンダー生成システム")

if 'time_dic' not in st.session_state:
    try:
        st.session_state.time_dic = p0.load_master_from_sheets(get_service(), SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

uploaded_file = st.file_uploader("PDFをアップロード", type="pdf")

if uploaded_file:
    with open("temp.pdf", "wb") as f: f.write(uploaded_file.getvalue())
    fname = uploaded_file.name
    my = re.search(r'(\d{4})', fname)
    mm = re.search(r'(\d{1,2})', fname)
    y, m = (int(my.group(1)), int(mm.group(1))) if (my and mm) else (None, None)
    
    if y and m:
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        if res:
            location = res['location']
            target_staff = st.selectbox("スタッフ選択", options=["該当なし"] + res['staff_list'])
            
            if target_staff != "該当なし":
                shift_data = p0.extract_target_data(res['df'], target_staff, location)
                if shift_data:
                    # 辞書登録
                    st.session_state.final_result = {
                        location: {
                            "time_schedule": st.session_state.time_dic[location],
                            "my_daily_shift": shift_data['my_daily_shift'],
                            "other_daily_shift": shift_data['other_daily_shift']
                        }
                    }
                    
                    # --- ここからメイン工程実行 ---
                    if st.button("カレンダーCSVを生成する"):
                        final_df = p0.run_main_process(y, m, st.session_state.final_result)
                        
                        st.write("### 生成結果プレビュー")
                        
                        # スタイル適用（緑・赤・青）
                        def color_type(val):
                            if val == 'key': return 'background-color: #d1e7dd'
                            if val == '休日': return 'background-color: #f8d7da'
                            return 'background-color: #cfe2ff'
                        
                        st.dataframe(final_df.style.applymap(color_type, subset=['Type']), hide_index=True)
                        
                        # CSV出力
                        csv_data = final_df.drop(columns=['Type']).to_csv(index=False, encoding='utf_8_sig')
                        st.download_button(
                            label="CSVファイルを保存",
                            data=csv_data,
                            file_name=f"{y}{m:02d}_{target_staff}.csv",
                            mime="text/csv"
                        )
        else:
            st.error(msg)
