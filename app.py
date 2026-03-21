import streamlit as st
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

# 各種設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト管理", layout="wide")
st.title("📅 シフトカレンダー一括登録")

def get_gapi_service(service_name, version):
    info = dict(st.secrets["gcp_service_account"])
    scopes = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/drive.readonly']
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """役割が連続するセルを1つにまとめて格納する"""
    # 終日の勤務予定
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 修正済み：iloc[0, col] からシフトコードを取得
    shift_code = str(my_daily_shift.iloc[0, col]).strip()
    
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean.iloc[1:][sched_clean.iloc[1:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_label = None
        for t_col in range(2, time_schedule.shape[1]):
            current_role = my_time_shift.iloc[0, t_col].strip()
            if not current_role:
                prev_label = None
                continue
            
            # 引き継ぎ情報の簡易取得
            mask_handing = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
            other_codes = other_staff_shift.iloc[:, col].astype(str).str.replace(r'[\s　]', '', regex=True)
            names_to = other_staff_shift[other_codes.isin(time_schedule.loc[mask_handing, 1])].iloc[:, 0].unique()
            label_to = f"to {'・'.join(names_to)}" if len(names_to) > 0 else ""
            
            full_label = f"{label_to}=>【{current_role}】"
            
            # 前の15分と同じ役割なら、終了時間だけを更新して結合する
            if full_label == prev_label and final_rows:
                next_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else str(time_schedule.iloc[0, t_col]).strip()
                final_rows[-1][4] = next_t
            else:
                # 新しい役割の開始
                start_t = str(time_schedule.iloc[0, t_col]).strip()
                end_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else start_t
                final_rows.append([full_label, target_date, start_t, target_date, end_t, "False", "", key])
                prev_label = full_label

# UI
if st.button("① PDFリスト取得"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        results = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute().get('files', [])
        st.session_state['pdf_files'] = results
        st.success("取得成功")
    except Exception as e:
        st.error(f"エラー: {e}")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("PDFを選択", [f['name'] for f in st.session_state['pdf_files']])
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
                # 勤務記号(C, 12等)は2行目（インデックス1）
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
