import streamlit as st  
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

# 設定値
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト管理", layout="wide")
st.title("📅 シフトカレンダー一括変換")

def get_gapi_service(service_name, version):
    """Google API認証（scopes引数の修正済み）"""
    info = dict(st.secrets["gcp_service_account"])
    scopes = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/drive.readonly']
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """役割が連続する15分単位のセルを1つの大きな予定に結合する"""
    # 終日の勤務コード予定
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    shift_code = str(my_daily_shift.iloc[1, col]).strip()
    sched_clean = time_schedule.fillna("").astype(str)
    # コードが一致する役割行を取得
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_label = None
        for t_col in range(2, time_schedule.shape[1]):
            current_role = my_time_shift.iloc[0, t_col].strip()
            if not current_role:
                prev_label = None
                continue
            
            # 引き継ぎ相手の特定
            mask_handing = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
            handing_text = "(交代)" if mask_handing.any() else ""
            other_codes = other_staff_shift.iloc[:, col].astype(str).str.replace(r'[\s　]', '', regex=True)
            names_to = other_staff_shift[other_codes.isin(time_schedule.loc[mask_handing, 1])].iloc[:, 0].unique()
            label_to = f"to {'・'.join(names_to)}" if len(names_to) > 0 else ""
            
            # 結合判定用のラベル（時間は含めない）
            full_label = f"{handing_text}{label_to}=>【{current_role}】"
            
            if full_label == prev_label and final_rows:
                # 役割が同じなら、終了時刻のみ更新して結合
                next_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else str(time_schedule.iloc[0, t_col]).strip()
                final_rows[-1][4] = next_t
            else:
                # 違う役割なら新規作成
                start_t = str(time_schedule.iloc[0, t_col]).strip()
                end_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else start_t
                final_rows.append([full_label, target_date, start_t, target_date, end_t, "False", "", key])
                prev_label = full_label

# UIフロー
if st.button("① Google DriveからPDFを取得"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        files = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute().get('files', [])
        st.session_state['pdf_files'] = files
        st.success(f"{len(files)}件見つかりました。")
    except Exception as e:
        st.error(f"接続失敗: {e}")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("PDFを選択", [f['name'] for f in st.session_state['pdf_files']])
    selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

    if st.button("② シフト解析開始"):
        with st.spinner("処理中..."):
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
            
            integrated = data_integration(pdf_dic, time_sched_dic)
            
            for key, data in integrated.items():
                rows_final = []
                my_s, other_s, t_s = data[0], data[1], data[2]
                for col in range(1, my_s.shape[1]):
                    shift_info = str(my_s.iloc[0, col]).strip()
                    if not shift_info or shift_info.lower() == "nan": continue
                    target_date = f"{y}/{m}/{col}"
                    if any(h in shift_info for h in ["休", "有給", "公休"]):
                        rows_final.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                    else:
                        shift_cal(key, target_date, col, shift_info, my_s, other_s, t_s, rows_final)
                
                if rows_final:
                    st.subheader(f"📍 {key}")
                    st.dataframe(pd.DataFrame(rows_final, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
