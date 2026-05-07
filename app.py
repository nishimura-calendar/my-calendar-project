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

st.set_page_config(layout="wide")
st.title("シフト解析・カレンダー生成")

# 時程表読込
if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

uploaded_file = st.file_uploader("PDFを選択", type="pdf")

if uploaded_file:
    with open("temp.pdf", "wb") as f: f.write(uploaded_file.getvalue())
    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y and m:
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        if res:
            location = res['location']
            target_staff = st.selectbox("スタッフ選択", options=["該当なし"] + res['staff_list'])
            
            if target_staff != "該当なし":
                shift_data = p0.extract_target_data(res['df'], target_staff, location)
                if shift_data:
                    # 辞書登録（工程通り）
                    st.session_state.final_result = {
                        location: {
                            "time_schedule": st.session_state.time_dic[location],
                            "my_daily_shift": shift_data['my_daily_shift'],
                            "other_daily_shift": shift_data['other_daily_shift']
                        }
                    }

                    # メイン工程開始ボタン
                    if st.button("カレンダーCSVを生成する"):
                        data = st.session_state.final_result[location]
                        my_shift = data["my_daily_shift"]
                        other_shift = data["other_daily_shift"]
                        t_schedule = data["time_schedule"]
                        
                        final_rows = []
                        # メイン工程 1 & 2: 日付（列）を巡回
                        for col_idx in range(1, my_shift.shape[1]):
                            target_date = f"{y}/{m:02d}/{col_idx:02d}"
                            s_info = str(my_shift.iloc[0, col_idx]).strip().replace('\n', '')
                            d_info = str(my_shift.iloc[1, col_idx]).strip().replace('\n', '')
                            
                            if s_info and s_info != "なし":
                                # 工程3〜6を内包する shift_cal 実行
                                p0.shift_cal(target_staff, target_date, col_idx, s_info, d_info, 
                                             other_shift, t_schedule, final_rows)
                        
                        # 完了後の表示とDL
                        if final_rows:
                            cal_df = pd.DataFrame(final_rows, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"])
                            st.write("### 生成結果プレビュー")
                            st.dataframe(cal_df, use_container_width=True, hide_index=True)
                            
                            csv = cal_df.to_csv(index=False, encoding='utf_8_sig')
                            st.download_button("CSVを保存", csv, f"{target_staff}_calendar.csv", "text/csv")
