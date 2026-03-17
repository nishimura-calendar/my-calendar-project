import streamlit as st
import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

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

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """現場シフト用の詳細解析"""
    shift_code = str(shift_info).strip()
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == shift_code]
                    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "": 
                    # 交代相手の特定(簡易版)
                    final_rows.append([f"【{current_val}】勤務", target_date, time_schedule.iloc[0, t_col], target_date, "", "False", f"シフトコード:{shift_code}", key])
                else:
                    if final_rows: final_rows[-1][4] = time_schedule.iloc[0, t_col]
            prev_val = current_val

# --- メイン UI ---
if st.button("① Googleドライブ接続・ファイル確認"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        results = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        items = results.get('files', [])
        if items:
            st.session_state['pdf_files'] = items
            st.success(f"{len(items)}件のPDFが見つかりました。")
        else: st.warning("PDFが見つかりません。")
    except Exception as e: st.error(f"接続エラー: {e}")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("処理するPDFを選択してください", [f['name'] for f in st.session_state['pdf_files']])
    selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

    if st.button("② 解析実行"):
        with st.spinner("PDFを解析中..."):
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
                
                if not integrated:
                    st.error("❌ 場所名が一致しません。")
                    st.write("PDFから検出:", list(pdf_dic.keys()))
                    st.write("Excelから検出:", list(time_sched_dic.keys()))
                else:
                    for key, data_list in integrated.items():
                        rows_shift = []
                        my_shift, other_shift, t_sched = data_list[0], data_list[1], data_list[2]

                        for col in range(1, my_shift.shape[1]):
                            info_top = str(my_shift.iloc[0, col]).strip()
                            info_bottom = str(my_shift.iloc[1, col]).strip() if len(my_shift) > 1 else ""
                            target_date = f"{y}/{m}/{col}"
                            
                            # 1. 事務所ルール (2行目に＠)
                            if "@" in info_bottom or "＠" in info_bottom:
                                rows_shift.append([f"【{info_top}】勤務", target_date, "", target_date, "", "True", f"時間: {info_bottom}", info_top])
                                st.write(f"🏢 {target_date}: {info_top} (事務所: {info_bottom})")
                                continue

                            # 2. 現場ルール (シフトコード)
                            if not info_top or info_top.lower() == "nan" or info_top == "": continue
                            
                            if any(h in info_top for h in ["休", "公休", "有給"]):
                                st.write(f"📅 {target_date}: お休み ({info_top})")
                            else:
                                shift_cal(key, target_date, col, info_top, my_shift, other_shift, t_sched, rows_shift)
                        
                        if rows_shift:
                            st.subheader(f"📍 {key} の解析結果")
                            df_res = pd.DataFrame(rows_shift, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"])
                            st.dataframe(df_res)
                            st.session_state['final_df'] = df_res

                st.success("解析が完了しました！")
            except Exception as e:
                st.error(f"解析エラー: {e}")

# --- カレンダー登録機能の準備 ---
if 'final_df' in st.session_state:
    if st.button("③ Googleカレンダーに登録する"):
        st.info("カレンダー登録機能を実行します...（API書き込み処理へ）")
        # ここにカレンダー登録のAPI実行コードを追記可能です
