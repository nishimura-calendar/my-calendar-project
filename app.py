import streamlit as st
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

# 設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト管理", layout="wide")
st.title("📅 シフト一括登録システム")

def get_gapi_service(service_name, version):
    info = dict(st.secrets["gcp_service_account"])
    scopes = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/drive.readonly']
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """値が変化したタイミングで時間を切り出すロジック"""
    # 終日予定を追加
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 修正：iloc[0, col] からシフトコードを取得
    shift_code = str(my_daily_shift.iloc[0, col]).strip()
    
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean.iloc[1:][sched_clean.iloc[1:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_role = None
        for t_col in range(2, time_schedule.shape[1]):
            current_role = my_time_shift.iloc[0, t_col].strip()
            
            # 空白セル（休憩など）はスキップし、役割をリセット
            if not current_role:
                prev_role = None
                continue
            
            # 15分にこだわらず、役割（セルの値）が変わったか判定
            if current_role == prev_role and final_rows:
                # 同じ役割が続くなら、最後の行の「終了時間」を更新（結合）
                next_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else str(time_schedule.iloc[0, t_col]).strip()
                final_rows[-1][4] = next_t
            else:
                # 役割が変わった（または開始した）ので新しい行を作成
                start_t = str(time_schedule.iloc[0, t_col]).strip()
                # 次のセルの時間を終了時間として仮置き
                end_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else start_t
                
                final_rows.append([f"【{current_role}】", target_date, start_t, target_date, end_t, "False", "", key])
                prev_role = current_role

# UIメイン
if st.button("① Google DriveからPDF取得"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        files = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute().get('files', [])
        st.session_state['pdf_files'] = files
        st.success("取得しました。")
    except Exception as e:
        st.error(f"接続エラー: {e}")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("PDF選択", [f['name'] for f in st.session_state['pdf_files']])
    selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

    if st.button("② 解析実行"):
        drive_service = get_gapi_service('drive', 'v3')
        time_sched_dic = time_schedule_from_drive(drive_service, TIME_TABLE_ID)
        
        pdf_req = drive_service.files().get_media(fileId=selected_id)
        pdf_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(pdf_stream, pdf_req)
        done = False
        while not done: _, done = downloader.next_chunk()
        
        pdf_stream.seek(0)
        pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
        pdf_stream.seek(0)
        y, m = extract_year_month(pdf_stream)
        
        shift_dic = data_integration(pdf_dic, time_sched_dic)
        
        for key, value in shift_dic.items():
            if len(value) < 3: continue
            rows_res = []
            my_s, other_s, t_s = value[0], value[1], value[2]
            
            for col in range(1, my_s.shape[1]):
                # 勤務記号(C, 12等)は1行目
                shift_info = str(my_s.iloc[1, col]).strip()
                if not shift_info or shift_info.lower() == "nan": continue
                
                target_date = f"{y}/{m}/{col}"
                if any(h in shift_info for h in ["休", "有給", "公休"]):
                    rows_res.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                else:
                    shift_cal(key, target_date, col, shift_info, my_s, other_s, t_s, rows_res)
            
            if rows_res:
                st.subheader(f"📍 {key}")
                st.dataframe(pd.DataFrame(rows_res, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
