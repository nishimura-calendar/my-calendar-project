import streamlit as st
import practice_0 as p0
import fitz
import re
from googleapiclient.discovery import build
from google.oauth2 import service_account

st.set_page_config(layout="wide")
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

def get_service():
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build('sheets', 'v4', credentials=creds)

if 'time_dic' not in st.session_state:
    try:
        service = get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

st.title("シフト解析・カレンダー生成")
uploaded_file = st.file_uploader("PDFを選択して下さい", type="pdf")

if uploaded_file:
    with open("temp.pdf", "wb") as f: f.write(uploaded_file.getvalue())
    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y and m:
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        if res:
            location = res['location']
            if location not in st.session_state.time_dic:
                st.error(f"「{location}」は時程表の勤務地に登録されていません。確認が必要です。")
                st.image(fitz.open("temp.pdf").load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png"))
                st.stop()
            
            st.success(f"勤務地「{location}」を特定しました")
            target_staff = st.selectbox("スタッフを選択して下さい", options=["未選択"] + res['staff_list'])
            df = res['df']
            
            if target_staff != "未選択":
                st.divider()
                idx = df[df[0] == target_staff].index[0]
                # データ表示
                st.subheader("my_daily_shift")
                st.dataframe(df.iloc[idx:idx+2, :], hide_index=True)
                st.subheader("other_daily_shift")
                other_df = df.drop([idx, idx+1]).iloc[2:, :][df[0] != location]
                st.dataframe(other_df, hide_index=True)
                st.subheader("time_schedule")
                st.dataframe(st.session_state.time_dic[location], hide_index=True)
                
                if st.button("CSVカレンダーを生成"):
                    cal_df = p0.generate_calendar_data(target_staff, location, df, st.session_state.time_dic, y, m)
                    if cal_df is not None:
                        st.dataframe(cal_df, use_container_width=True, hide_index=True)
                        csv = cal_df.to_csv(index=False, encoding='utf_8_sig')
                        st.download_button("CSVダウンロード", data=csv, file_name=f"{target_staff}.csv", mime="text/csv")
        else:
            st.error(msg)
            st.image(fitz.open("temp.pdf").load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png"))
