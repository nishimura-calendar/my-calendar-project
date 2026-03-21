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

st.set_page_config(page_title="シフト管理システム", layout="wide")
st.title("📅 シフトカレンダー一括変換")

def get_gapi_service(service_name, version):
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, time_schedule, final_rows):
    # 終日予定
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 0行目からシフトコード(C, B, 12等)を取得
    shift_code = str(my_daily_shift.iloc[0, col]).strip()
    sched_clean = time_schedule.fillna("").astype(str)
    
    # 時程表のB列（インデックス1）とコードを照合
    my_time_shift = sched_clean.iloc[1:][sched_clean.iloc[1:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_role = None
        last_added_idx = -1
        for t_col in range(2, time_schedule.shape[1]):
            current_role = my_time_shift.iloc[0, t_col].strip()
            if not current_role:
                prev_role = None
                continue
            
            if current_role == prev_role and last_added_idx != -1:
                # 役割が同じなら終了時間のみ更新
                next_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else str(time_schedule.iloc[0, t_col]).strip()
                final_rows[last_added_idx][4] = next_t
            else:
                # 役割が変わったら新規追加
                start_t = str(time_schedule.iloc[0, t_col]).strip()
                end_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else start_t
                final_rows.append([f"【{current_role}】", target_date, start_t, target_date, end_t, "False", "", key])
                last_added_idx = len(final_rows) - 1
                prev_role = current_role

# UI
if st.button("① Google DriveからPDFを取得"):
    drive_service = get_gapi_service('drive', 'v3')
    files = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute().get('files', [])
    st.session_state['pdf_files'] = files
    st.success(f"{len(files)}件取得")

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
        
        # --- デバッグ表示 ---
        if not integrated:
            st.error("データの統合に失敗しました。PDFと時程表の勤務地名（T2など）が一致しているか確認してください。")
        
        for key, data in integrated.items():
            st.info(f"📍 {key} のデータを処理中...")
            if len(data) < 3:
                st.warning(f"  -> {key} に対応する時程表データが見つかりません。")
                continue
            
            rows_res = []
            my_s, t_s = data[0], data[2]
            
            for col in range(1, my_s.shape[1]):
                shift_info = str(my_s.iloc[1, col]).strip()
                if not shift_info or shift_info.lower() == "nan": continue
                
                target_date = f"{y}/{m}/{col}"
                if any(h in shift_info for h in ["休", "有給", "公休"]):
                    rows_res.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                else:
                    shift_cal(key, target_date, col, shift_info, my_s, t_s, rows_res)
            
            if rows_res:
                st.subheader(f"📍 勤務地: {key}")
                st.dataframe(pd.DataFrame(rows_res, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
            else:
                st.warning(f"  -> {key} の解析結果が0件です。シフト記号の読み取りに失敗している可能性があります。")
