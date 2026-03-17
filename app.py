import streamlit as st
import pandas as pd
import io
import os
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials

# practice_0.pyからロジックを読み込み
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration, working_hours

# --- 設定 ---
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

# カレンダーの色設定 (Google API Color ID)
COLOR_MAP = {
    "shift": "10",   # 緑 (Basil)
    "event": "9",    # 青 (Blueberry)
    "holiday": "11"  # 赤 (Tomato)
}

st.set_page_config(page_title="シフト管理システム", layout="centered")
st.title("📅 シフトカレンダー一括登録")

# --- 認証処理 (Streamlit Secretsを利用) ---
def get_gapi_service(service_name, version):
    from google.oauth2 import service_account
    
    info = dict(st.secrets["gcp_service_account"])
    
    scopes = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=scopes
    )
    return build(service_name, version, credentials=creds) 
    
# --- シフト詳細計算ロジック ---
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    if (time_schedule.iloc[:, 1] == shift_info).any():
        final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", ""])
        
    shift_code = my_daily_shift.iloc[0, col]
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "": 
                    handing_over_department = ""
                    mask_handing_over = pd.Series([False] * len(time_schedule))
                    
                    if prev_val == "": 
                        mask_handing_over = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
                        handing_over_department = "(交代)" if mask_handing_over.any() else ""
                    else:
                        handing_over_department = f"({prev_val})" 
                        mask_handing_over = (time_schedule.iloc[:, t_col] == prev_val)
                        if final_rows: final_rows[-1][4] = time_schedule.iloc[0, t_col]
                    
                    mask_taking_over = (time_schedule.iloc[:, t_col-1] == current_val)   
                    handing_over, taking_over = "", ""

                    for i in range(0, 2):
                        mask = mask_handing_over if i == 0 else mask_taking_over
                        search_keys = time_schedule.loc[mask, time_schedule.columns[1]]
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys)]
                        names_series = target_rows.iloc[:, 0]
                        
                        if i == 0:
                            staff_names = f"to {'・'.join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            handing_over = f"{handing_over_department}{staff_names}"
                        else:
                            staff_names = f"from {'・'.join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            taking_over = f"【{current_val}】{staff_names}"    
                    
                    final_rows.append([f"{handing_over}=>{taking_over}", target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", ""])
                else:
                    if final_rows: final_rows[-1][4] = time_schedule.iloc[0, t_col]    
            prev_val = current_val

# --- メイン UI 処理 ---

if st.button("① メール検索 & ファイル確認"):
    with st.spinner("ドライブを確認中..."):
        try:
            drive_service = get_gapi_service('drive', 'v3')
            results = drive_service.files().list(
                q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'",
                pageSize=5, fields="files(id, name)"
            ).execute()
            items = results.get('files', [])
            if not items:
                st.warning("PDFファイルが見つかりません。")
            else:
                st.session_state['pdf_files'] = items
                st.success(f"{len(items)} 件のPDFが見つかりました。")
        except Exception as e:
            st.error(f"接続エラー: {e}")

if 'pdf_files' in st.session_state:
    selected_pdf_name = st.selectbox("処理するPDFを選択", options=[f['name'] for f in st.session_state['pdf_files']])
    selected_pdf_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_pdf_name)

    if st.button("② 実行（解析 ＆ カレンダー登録）"):
        with st.spinner("解析中..."):
            try:
                drive_service = get_gapi_service('drive', 'v3')
                
                # 1. Driveから時程表を取得
                time_sched_dic = time_schedule_from_drive(drive_service, TIME_TABLE_ID)
                
                # 2. 選択されたPDFをダウンロード
                pdf_request = drive_service.files().get_media(fileId=selected_pdf_id)
                pdf_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(pdf_stream, pdf_request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                
                # PDF解析
                pdf_stream.seek(0)
                pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
                
                # 年月抽出
                pdf_stream.seek(0)
                y, m = extract_year_month(pdf_stream)
                year_month = f"{y}年{m}月"
                
                # 3. データの統合
                shift_dic = data_integration(pdf_dic, time_sched_dic)
                
                # 4. 振り分けと表示
                holiday_keywords = ["休", "公休", "有給", "特休"]
                special_location = "本町"

                for key, data_list in shift_dic.items():
                    rows_shift = []
                    my_daily_shift, other_daily_shift, time_sched_df = data_list 

                    for col in range(1, my_daily_shift.shape[1]):
                        shift_info = str(my_daily_shift.iloc[0, col]).strip()
                        if not shift_info or shift_info.lower() == "nan" or shift_info == "": continue

                        target_date = f"{y}/{m}/{col}"

                        if any(h in shift_info for h in holiday_keywords):
                            st.write(f"📅 {target_date}: 休日 ({shift_info})")
                        elif special_location in shift_info:
                            st.write(f"📅 {target_date}: イベント ({shift_info})")
                        else:
                            shift_cal(key, target_date, col, shift_info, my_daily_shift, other_daily_shift, time_sched_df, rows_shift)
                    
                    if rows_shift:
                        st.write(f"✅ {key} のシフトを解析しました。")
                        df_result = pd.DataFrame(rows_shift, columns=["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day", "Desc", "Loc"])
                        st.dataframe(df_result)

                st.success("全ての解析が完了しました！")
                st.balloons()
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
