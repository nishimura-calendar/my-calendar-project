import streamlit as st
import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
# practice_0 から関数を読み込む
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

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
    """通常シフトの詳細計算（終了時間を連動させる）"""
    shift_code = str(my_daily_shift.iloc[0, col]).strip()
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            
            if current_val != prev_val:
                # 前の予定の終了時間を「今の開始時間」で上書き
                if prev_val != "" and final_rows:
                    final_rows[-1][4] = time_schedule.iloc[0, t_col] 

                if current_val != "": 
                    # 交代相手の特定
                    mask_handing = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
                    handing_dept = "(交代)" if mask_handing.any() else ""
                    if prev_val != "":
                        handing_dept = f"({prev_val})"
                        mask_handing = (time_schedule.iloc[:, t_col] == prev_val)
                    
                    mask_taking = (time_schedule.iloc[:, t_col-1] == current_val)
                    
                    search_to = time_schedule.loc[mask_handing, time_schedule.columns[1]]
                    names_to = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_to)].iloc[:, 0].unique()
                    
                    search_from = time_schedule.loc[mask_taking, time_schedule.columns[1]]
                    names_from = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_from)].iloc[:, 0].unique()

                    label_to = f"to {'・'.join(names_to)}" if len(names_to) > 0 else ""
                    label_from = f"【{current_val}】from {'・'.join(names_from)}" if len(names_from) > 0 else f"【{current_val}】"
                    
                    final_rows.append([
                        f"{handing_dept}{label_to}=>{label_from}", target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", key
                    ])
                prev_val = current_val
        
        # 最後の終了時間をセット
        if final_rows and final_rows[-1][4] == "":
             final_rows[-1][4] = time_schedule.iloc[0, t_col]

# --- メイン画面 ---
if st.button("① ファイル確認"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        results = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        items = results.get('files', [])
        if items:
            st.session_state['pdf_files'] = items
            st.success(f"{len(items)}件のPDFが見つかりました。")
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
                
                for key, data_list in integrated.items():
                    if len(data_list) < 3: continue
                    rows_final = []
                    my_shift, other_shift, t_sched = data_list[0], data_list[1], data_list[2]

                    for col in range(1, my_shift.shape[1]):
                        info = str(my_shift.iloc[1, col]).strip()
                        if not info or info.lower() == "nan" or info == "": continue
                        
                        target_date = f"{y}/{m}/{col}"
                        if any(h in info for h in ["休", "公休", "有給", "特休"]):
                            main_info = "有給" if "有給" in info else "休日"
                            rows_final.append([f"{key}_{main_info}", target_date, "", target_date, "", "True", "", key])
                        else:
                            shift_cal(key, target_date, col, info, my_shift, other_shift, t_sched, rows_final)
                    
                    if rows_final:
                        st.subheader(f"📍 {key} の解析結果")
                        df_res = pd.DataFrame(rows_final, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"])
                        st.dataframe(df_res)
                st.success("解析完了！")
            except Exception as e:
                st.error(f"解析エラー: {e}")
