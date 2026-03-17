import streamlit as st
import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- インポートのデバッグ ---
try:
    from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration
except Exception as e:
    st.error(f"❌ 内部ファイルの読み込みに失敗しました。原因: {e}")
    st.stop()

# --- 基本設定 ---
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

def shift_cal(key, target_date, col, shift_name, shift_code, other_staff_shift, time_schedule, final_rows):
    """詳細スケジュール計算。まず概要行(T2_C等)を追加し、次に詳細時間を追加"""
    # 1. 概要行（例：T2_C）を終日予定として追加
    final_rows.append([f"{key}_{shift_name}", target_date, "", target_date, "", "True", "", key])
    
    # 2. 詳細スケジュール（時程表）
    sched_clean = time_schedule.fillna("").astype(str)
    # ExcelのB列(1番目の列)にあるコードと一致する行を探す
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if prev_val != "" and final_rows:
                    final_rows[-1][4] = time_schedule.iloc[0, t_col] 

                if current_val != "": 
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
                    final_rows.append([f"{handing_dept}{label_to}=>{label_from}", target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", key])
                prev_val = current_val
        if final_rows and final_rows[-1][4] == "":
             final_rows[-1][4] = time_schedule.iloc[0, t_col]

# --- メイン処理 ---
if st.button("① ファイル確認"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        results = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        items = results.get('files', [])
        if items:
            st.session_state['pdf_files'] = items
            st.success(f"{len(items)}件のPDFが見つかりました。")
    except Exception as e: st.error(f"エラー: {e}")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("PDFを選択", [f['name'] for f in st.session_state['pdf_files']])
    selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

    if st.button("② 実行（解析開始）"):
        with st.spinner("解析中..."):
            try:
                drive_service = get_gapi_service('drive', 'v3')
                time_sched_dic = time_schedule_from_drive(drive_service, TIME_TABLE_ID)
                st.write(f"📊 Excel(時程表)の場所名: {list(time_sched_dic.keys())}")
                
                pdf_req = drive_service.files().get_media(fileId=selected_id)
                pdf_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(pdf_stream, pdf_req)
                done = False
                while not done: _, done = downloader.next_chunk()
                
                pdf_stream.seek(0)
                pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
                st.write(f"📄 PDFから取得した場所名: {list(pdf_dic.keys())}")
                
                pdf_stream.seek(0)
                y, m = extract_year_month(pdf_stream)
                integrated = data_integration(pdf_dic, time_sched_dic)
                
                if not integrated:
                    st.error("場所名が一致しません。")
                
                for key, data_list in integrated.items():
                    rows_final = []
                    my_shift, other_shift, t_sched = data_list[0], data_list[1], data_list[2]

                    for col in range(1, my_shift.shape[1]):
                        # 1. 名前の行(0行目)からシフト名(C, 休など)を取得
                        shift_name = str(my_shift.iloc[0, col]).strip()
                        if not shift_name or shift_name.lower() == "nan": continue
                        
                        # 2. その下の行(1行目)から数値コードを取得(あれば)
                        shift_code = str(my_shift.iloc[1, col]).strip() if my_shift.shape[0] > 1 else shift_name
                        
                        target_date = f"{y}/{m}/{col}"
                        
                        # 休日判定
                        if any(h in shift_name for h in ["休", "公休", "有給", "特休"]):
                            main_info = "有給" if "有給" in shift_name else "休日"
                            rows_final.append([f"{key}_{main_info}", target_date, "", target_date, "", "True", "", key])
                        else:
                            # 通常勤務
                            shift_cal(key, target_date, col, shift_name, shift_code, other_shift, t_sched, rows_final)
                    
                    if rows_final:
                        st.subheader(f"📍 {key} の解析結果")
                        st.dataframe(pd.DataFrame(rows_final, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
                st.success("解析完了！")
            except Exception as e: st.error(f"解析エラー: {e}")
