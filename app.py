import streamlit as st
import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration, working_hours

# --- 設定 ---
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト管理システム", layout="wide")
st.title("📅 シフトカレンダー一括登録")

def get_gapi_service(service_name, version):
    from google.oauth2 import service_account
    info = dict(st.secrets["gcp_service_account"])
    scopes = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/drive.readonly']
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    shift_code = my_daily_shift.iloc[0, col]
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str) == str(shift_code)]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "": 
                    mask_handing = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
                    mask_taking = (time_schedule.iloc[:, t_col-1] == current_val)
                    
                    search_keys_to = time_schedule.loc[mask_handing, time_schedule.columns[1]]
                    names_to = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys_to)].iloc[:, 0].unique()
                    
                    search_keys_from = time_schedule.loc[mask_taking, time_schedule.columns[1]]
                    names_from = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys_from)].iloc[:, 0].unique()

                    label = f"to {'・'.join(names_to)}" if names_to.any() else ""
                    taking = f"【{current_val}】from {'・'.join(names_from)}" if names_from.any() else f"【{current_val}】"
                    
                    final_rows.append([f"{label}=>{taking}", target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", key])
                else:
                    if final_rows: final_rows[-1][4] = time_schedule.iloc[0, t_col]
            prev_val = current_val

# --- メイン処理 ---
if st.button("① ファイル確認"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        results = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        items = results.get('files', [])
        if items:
            st.session_state['pdf_files'] = items
            st.success(f"{len(items)}件のPDFが見つかりました。")
        else:
            st.warning("PDFが見つかりません。")
    except Exception as e:
        st.error(f"エラー: {e}")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("PDFを選択", [f['name'] for f in st.session_state['pdf_files']])
    selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

    if st.button("② 実行（解析開始）"):
        with st.spinner("解析中..."):
            try:
                drive_service = get_gapi_service('drive', 'v3')
                time_sched_dic = time_schedule_from_drive(drive_service, TIME_TABLE_ID)
                
                # --- デバッグ用表示 (Excel側) ---
                st.write("🔍 Excel(時程表)から見つけた場所名:", list(time_sched_dic.keys()))
                
                pdf_req = drive_service.files().get_media(fileId=selected_id)
                pdf_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(pdf_stream, pdf_req)
                done = False
                while not done: _, done = downloader.next_chunk()
                
                pdf_stream.seek(0)
                pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
                
                # --- デバッグ用表示 (PDF側) ---
                st.write("🔍 PDFから見つけた場所名:", list(pdf_dic.keys()))
                
                pdf_stream.seek(0)
                y, m = extract_year_month(pdf_stream)
                
                integrated = data_integration(pdf_dic, time_sched_dic)
                
                if not integrated:
                    st.error("❌ PDFとExcelの場所名が一致しなかったため、統合できませんでした。")
                    st.info("上の『🔍』で表示された名前が完全に一致しているか確認してください。")

                for key, data_list in integrated.items():
                    rows_shift = []
                    my_shift, other_shift, t_sched = data_list[0], data_list[1], data_list[2]

                    for col in range(1, my_shift.shape[1]):
                        info = str(my_shift.iloc[0, col]).strip()
                        if not info or info.lower() == "nan": continue
                        
                        target_date = f"{y}/{m}/{col}"
                        if any(h in info for h in ["休", "公休", "有給"]):
                            st.write(f"📅 {target_date}: お休み ({info})")
                        else:
                            shift_cal(key, target_date, col, info, my_shift, other_shift, t_sched, rows_shift)
                    
                    if rows_shift:
                        st.subheader(f"📍 {key} の解析結果")
                        st.dataframe(pd.DataFrame(rows_shift, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))

                st.success("解析完了！")
            except Exception as e:
                st.error(f"エラー: {e}")
