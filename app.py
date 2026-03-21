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

st.set_page_config(page_title="シフト管理システム", layout="wide")
st.title("📅 シフトカレンダー一括変換")

def get_gapi_service(service_name, version):
    info = dict(st.secrets["gcp_service_account"])
    scopes = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/drive.readonly']
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """時程表の役割を解析し、連続するセルを結合して格納する"""
    # 終日の予定を追加
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 【修正】ご指摘通り、スタッフ名行(0行目)からコードを取得
    shift_code = str(my_daily_shift.iloc[0, col]).strip()
    
    sched_clean = time_schedule.fillna("").astype(str)
    # コードが一致する行を時程表から抽出（1行目以降がデータ）
    my_time_shift = sched_clean.iloc[1:][sched_clean.iloc[1:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_label = None
        for t_col in range(2, time_schedule.shape[1]):
            current_role = my_time_shift.iloc[0, t_col].strip()
            if not current_role:
                prev_label = None
                continue
            
            # --- 参考資料に基づく引き継ぎ判定 (Pattern 1-4) ---
            # 自分が直前のコマで空（休憩等）だった場合、誰から引き継ぐか(from)を特定
            is_start = (my_time_shift.iloc[0, t_col-1].strip() == "") if t_col > 2 else True
            
            # 引き継ぎ相手の特定ロジック
            other_codes = other_staff_shift.iloc[:, col].astype(str).str.replace(r'[\s　]', '', regex=True)
            # 時程表でこのコマが空のコードを持つスタッフを探す
            blank_mask = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
            names_involved = other_staff_shift[other_codes.isin(time_schedule.loc[blank_mask, 1])].iloc[:, 0].unique()
            
            handover_tag = "(交代)" if is_start and len(names_involved) > 0 else ""
            involve_label = f"to/from {'・'.join(names_involved)}" if len(names_involved) > 0 else ""
            
            # 結合用のユニークラベル（時間は含まない）
            full_label = f"{handover_tag}{involve_label}=>【{current_role}】"
            
            if full_label == prev_label and final_rows:
                # 前の15分と同じ役割なら終了時刻のみ更新（結合処理）
                next_t = str(time_schedule.iloc[0, t_col + 1]).strip() if t_col + 1 < time_schedule.shape[1] else str(time_schedule.iloc[0, t_col]).strip()
                if next_t:
                    final_rows[-1][4] = next_t
            else:
                # 新しい役割の開始
                start_t = str(time_schedule.iloc[0, t_col]).strip()
                end_t = str(time_schedule.iloc[0, t_col + 1]).strip() if t_col + 1 < time_schedule.shape[1] else start_t
                final_rows.append([full_label, target_date, start_t, target_date, end_t, "False", "", key])
                prev_label = full_label

# UI処理
if st.button("① Google DriveからPDFを取得"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        files = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute().get('files', [])
        st.session_state['pdf_files'] = files
        st.success(f"{len(files)}件のPDFを取得しました。")
    except Exception as e:
        st.error(f"接続エラー: {e}")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("処理するPDFを選択してください", [f['name'] for f in st.session_state['pdf_files']])
    selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

    if st.button("② シフト解析を実行"):
        with st.spinner("データを解析中..."):
            drive_service = get_gapi_service('drive', 'v3')
            time_sched_dic = time_schedule_from_drive(drive_service, TIME_TABLE_ID)
            
            pdf_req = drive_service.files().get_media(fileId=selected_id)
            pdf_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(pdf_stream, pdf_req)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            pdf_stream.seek(0)
            pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
            pdf_stream.seek(0)
            y, m = extract_year_month(pdf_stream)
            
            integrated = data_integration(pdf_dic, time_sched_dic)
            
            for key, data in integrated.items():
                if len(data) < 3: continue
                rows_final = []
                my_s, other_s, t_s = data[0], data[1], data[2]
                
                for col in range(1, my_s.shape[1]):
                    shift_info = str(my_s.iloc[1, col]).strip() # コードではなく勤務記号(Cなど)は1行目
                    if not shift_info or shift_info.lower() == "nan": continue
                    
                    target_date = f"{y}/{m}/{col}"
                    if any(h in shift_info for h in ["休", "有給", "公休"]):
                        rows_final.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                    else:
                        shift_cal(key, target_date, col, shift_info, my_s, other_s, t_s, rows_final)
                
                if rows_final:
                    st.subheader(f"📍 勤務地: {key}")
                    st.dataframe(pd.DataFrame(rows_final, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
