import streamlit as st
import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

# 各種ID設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換（最終統合版）")

def get_gapi_service():
    try:
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """ご提示のロジックに基づく詳細引き継ぎ計算"""
    if (time_schedule.iloc[:, 1] == shift_info).any():
        final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
        
    shift_code = my_daily_shift.iloc[0, col]
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col].strip()
            if current_val != prev_val:
                if current_val != "": 
                    handing_over_department = "" 
                    mask_handing_over = pd.Series([False] * len(time_schedule)) 
                    
                    if prev_val == "": 
                        mask_handing_over = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
                        if mask_handing_over.any(): handing_over_department = "(交代)"
                    else:
                        handing_over_department = f"({prev_val})" 
                        mask_handing_over = (time_schedule.iloc[:, t_col] == prev_val)
                        if len(final_rows) > 0:
                            final_rows[-1][4] = str(time_schedule.iloc[0, t_col]).strip()
                    
                    mask_taking_over = (time_schedule.iloc[:, t_col-1] == current_val)   
                    handing_over = ""; taking_over = ""

                    for i in range(0, 2):
                        mask = mask_handing_over if i == 0 else mask_taking_over
                        search_keys = time_schedule.loc[mask, time_schedule.columns[1]] 
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys)] 
                        names = target_rows.iloc[:, 0].unique().astype(str)
                        
                        if i == 0:
                            staff = f"to {'・'.join(names)}" if len(names) > 0 else ""
                            handing_over = f"{handing_over_department}{staff}"
                        else:
                            staff = f"from {'・'.join(names)}" if len(names) > 0 else ""
                            taking_over = f"【{current_val}】{staff}"    
                    
                    final_rows.append([f"{handing_over}=>{taking_over}", target_date, str(time_schedule.iloc[0, t_col]).strip(), target_date, "", "False", "", key])
                else:
                    if len(final_rows) > 0:
                        final_rows[-1][4] = str(time_schedule.iloc[0, t_col]).strip()
            prev_val = current_val

service = get_gapi_service()
if service:
    if st.button("① PDFリスト取得"):
        res = service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        st.session_state['pdf_files'] = res.get('files', [])

    if 'pdf_files' in st.session_state and st.session_state['pdf_files']:
        selected_name = st.selectbox("PDF選択", [f['name'] for f in st.session_state['pdf_files']])
        selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

        if st.button("② 解析実行"):
            with st.spinner("処理中..."):
                time_sched_dic = time_schedule_from_drive(service, TIME_TABLE_ID)
                pdf_req = service.files().get_media(fileId=selected_id)
                pdf_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(pdf_stream, pdf_req)
                done = False
                while not done: _, done = downloader.next_chunk()
                
                pdf_stream.seek(0)
                pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
                pdf_stream.seek(0)
                y, m = extract_year_month(pdf_stream)
                integrated = data_integration(pdf_dic, time_sched_dic)
                
                for key, data in integrated.items():
                    rows_res = []
                    my_s, other_s, t_s = data[0], data[1], data[2]
                    for col in range(1, my_s.shape[1]):
                        shift_code = str(my_s.iloc[0, col]).strip()
                        lower_val = str(my_s.iloc[1, col]).strip() if my_s.shape[0] > 1 else ""
                        if not shift_code or shift_code.lower() == "nan": continue
                        target_date = f"{y}/{m}/{col}"
                        
                        if any(h in shift_code for h in ["休", "有給", "有休", "公休"]):
                            rows_res.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                        elif "@" in lower_val:
                            parts = lower_val.split("@")
                            s_t = f"{re.search(r'\d+', parts[0]).group().zfill(2)}:00" if len(parts)>0 else ""
                            e_t = f"{re.search(r'\d+', parts[1]).group().zfill(2)}:00" if len(parts)>1 else ""
                            rows_res.append([f"{key}_{shift_code}", target_date, s_t, target_date, e_t, "False", "PDF時間指定", key])
                        else:
                            shift_cal(key, target_date, col, shift_code, my_s, other_s, t_s, rows_res)
                    
                    if rows_res:
                        st.subheader(f"📍 {key}")
                        st.dataframe(pd.DataFrame(rows_res, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
