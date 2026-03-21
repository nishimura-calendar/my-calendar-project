import streamlit as st
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換")

def get_gapi_service(service_name, version):
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, time_schedule, final_rows):
    """セルの内容が変化したときだけ行を生成するロジック"""
    # 終日予定を追加
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 0行目（スタッフ名のすぐ下の行）からシフトコードを取得
    shift_code = str(my_daily_shift.iloc[0, col]).strip()
    sched_clean = time_schedule.fillna("").astype(str)
    
    # 時程表から該当するコードの行を特定
    my_time_shift = sched_clean.iloc[1:][sched_clean.iloc[1:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_role = None
        last_row_idx = -1
        
        # 時刻列（2列目以降）をスキャン
        for t_col in range(2, time_schedule.shape[1]):
            current_role = my_time_shift.iloc[0, t_col].strip()
            
            if not current_role:
                prev_role = None # 空白（休憩等）で役割が途切れた
                continue
            
            # 15分刻みに関わらず、「役割が前と同じ」なら終了時間を延ばすだけ
            if current_role == prev_role and last_row_idx != -1:
                next_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else str(time_schedule.iloc[0, t_col]).strip()
                final_rows[last_row_idx][4] = next_t
            else:
                # 役割が新しくなった（または途切れから再開した）ので新規行作成
                start_t = str(time_schedule.iloc[0, t_col]).strip()
                end_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else start_t
                
                final_rows.append([f"【{current_role}】", target_date, start_t, target_date, end_t, "False", "", key])
                last_row_idx = len(final_rows) - 1
                prev_role = current_role

# UI
if st.button("① Google DriveからPDF取得"):
    service = get_gapi_service('drive', 'v3')
    files = service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute().get('files', [])
    st.session_state['pdf_files'] = files
    st.success("取得完了")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("PDF選択", [f['name'] for f in st.session_state['pdf_files']])
    selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

    if st.button("② 解析を実行"):
        service = get_gapi_service('drive', 'v3')
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
            if len(data) < 3: continue
            rows_res = []
            my_s, t_s = data[0], data[2]
            
            for col in range(1, my_s.shape[1]):
                shift_info = str(my_s.iloc[1, col]).strip()
                if not shift_info or shift_info.lower() == "nan": continue
                
                target_date = f"{y}/{m}/{col}"
                # 休日判定
                if any(h in shift_info for h in ["休", "有給", "公休"]):
                    rows_res.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                else:
                    shift_cal(key, target_date, col, shift_info, my_s, t_s, rows_res)
            
            if rows_res:
                st.subheader(f"📍 {key}")
                st.dataframe(pd.DataFrame(rows_res, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
