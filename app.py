import streamlit as st
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

# 固定設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換 (3/20リセット版)")

def get_gapi_service():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("Secretsに 'gcp_service_account' が設定されていません。")
            return None
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

def shift_cal(key, target_date, col, shift_info, my_daily_shift, time_schedule, final_rows):
    """セルの値が変わった時に時間の変化を入力するロジック"""
    # その日のシフト名を終日予定として登録
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    shift_code = str(my_daily_shift.iloc[0, col]).strip()
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean.iloc[1:][sched_clean.iloc[1:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_val = None
        last_row_idx = -1
        
        # 時程表の列をスキャン
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col].strip()
            
            # 値が空（休憩等）の場合、イベントを終了させる
            if not current_val:
                prev_val = None
                continue
            
            # 前のセルと同じ値なら、終了時間だけを更新して「予定を伸ばす」
            if current_val == prev_val and last_row_idx != -1:
                # 終了時間は、次の列の時刻ラベル、もしくは現在の列の時刻（最後の場合）
                if t_col + 1 < time_schedule.shape[1]:
                    next_time = str(time_schedule.iloc[0, t_col + 1]).strip()
                else:
                    next_time = str(time_schedule.iloc[0, t_col]).strip()
                final_rows[last_row_idx][4] = next_time
            else:
                # 値が変わった（または空白明け）ので、新規行を作成
                start_time = str(time_schedule.iloc[0, t_col]).strip()
                if t_col + 1 < time_schedule.shape[1]:
                    end_time = str(time_schedule.iloc[0, t_col + 1]).strip()
                else:
                    end_time = start_time
                
                final_rows.append([f"【{current_val}】", target_date, start_time, target_date, end_time, "False", "", key])
                last_row_idx = len(final_rows) - 1
                prev_val = current_val

# --- メインロジック ---
service = get_gapi_service()
if service:
    if st.button("① Google DriveからPDFを取得"):
        results = service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        st.session_state['pdf_files'] = results.get('files', [])
        st.success(f"{len(st.session_state['pdf_files'])}件のPDFを取得")

    if 'pdf_files' in st.session_state and st.session_state['pdf_files']:
        selected_name = st.selectbox("PDF選択", [f['name'] for f in st.session_state['pdf_files']])
        selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

        if st.button("② 解析を実行"):
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
                my_s, t_s = data[0], data[2] # PDFの自分データと時程表
                
                for col in range(1, my_s.shape[1]):
                    shift_info = str(my_s.iloc[1, col]).strip()
                    if not shift_info or shift_info.lower() == "nan": continue
                    
                    target_date = f"{y}/{m}/{col}"
                    if any(h in shift_info for h in ["休", "有給", "公休"]):
                        rows_res.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                    else:
                        shift_cal(key, target_date, col, shift_info, my_s, t_s, rows_res)
                
                if rows_res:
                    st.subheader(f"📍 {key}")
                    st.dataframe(pd.DataFrame(rows_res, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
