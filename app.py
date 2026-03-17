import streamlit as st
import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

try:
    from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration
except Exception as e:
    st.error(f"❌ インポートエラー: {e}")
    st.stop()

TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト管理システム", layout="wide")
st.title("📅 シフトカレンダー一括登録")

def get_gapi_service(service_name, version):
    from google.oauth2 import service_account
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/drive.readonly'])
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_name, shift_code, other_staff_shift, time_schedule, final_rows):
    """詳細スケジュールの計算ロジック"""
    final_rows.append([f"{key}_{shift_name}", target_date, "", target_date, "", "True", "", key])
    
    sched_clean = time_schedule.fillna("").astype(str)
    # ExcelのB列（インデックス1）にシフトコード(12等)がある行を探す
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == str(shift_code)]
    
    if not my_time_shift.empty:
        prev_val = ""
        # 2列目以降が時系列の担当データ
        for t_col in range(2, time_schedule.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                # 終了時間のセット（1つ前の行を更新）
                if prev_val != "" and final_rows:
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]

                if current_val != "":
                    # 交代相手の抽出
                    mask_handing = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
                    handing_dept = "(交代)" if mask_handing.any() else ""
                    if prev_val != "":
                        handing_dept = f"({prev_val})"
                    
                    mask_taking = (time_schedule.iloc[:, t_col-1] == current_val)
                    
                    # 他人の名前一致（空白除去して判定）
                    other_codes = other_staff_shift.iloc[:, col].astype(str).str.replace(r'[\s　]', '', regex=True)
                    names_to = other_staff_shift[other_codes.isin(time_schedule.loc[mask_handing, 1])].iloc[:, 0].unique()
                    names_from = other_staff_shift[other_codes.isin(time_schedule.loc[mask_taking, 1])].iloc[:, 0].unique()

                    label_to = f"to {'・'.join(names_to)}" if len(names_to) > 0 else ""
                    # current_valが「前」などの記号になるように
                    label_from = f"【{current_val}】from {'・'.join(names_from)}" if len(names_from) > 0 else f"【{current_val}】"
                    
                    final_rows.append([f"{handing_dept}{label_to}=>{label_from}", target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", key])
                prev_val = current_val
        if final_rows and final_rows[-1][4] == "":
             final_rows[-1][4] = time_schedule.iloc[0, t_col]

# --- UI部分 ---
if st.button("① ファイル確認"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        items = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute().get('files', [])
        if items:
            st.session_state['pdf_files'] = items
            st.success(f"{len(items)}件見つかりました。")
    except Exception as e: st.error(f"エラー: {e}")

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
                MediaIoBaseDownload(pdf_stream, pdf_req).next_chunk()
                
                pdf_stream.seek(0)
                pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
                pdf_stream.seek(0)
                y, m = extract_year_month(pdf_stream)
                
                integrated = data_integration(pdf_dic, time_sched_dic)
                
                for key, data_list in integrated.items():
                    rows_final = []
                    my_shift, other_shift, t_sched = data_list[0], data_list[1], data_list[2]

                    for col in range(1, my_shift.shape[1]):
                        shift_name = str(my_shift.iloc[0, col]).strip()
                        if not shift_name or shift_name.lower() == "nan": continue
                        
                        shift_code = str(my_shift.iloc[1, col]).strip() if my_shift.shape[0] > 1 else shift_name
                        target_date = f"{y}/{m}/{col}"
                        
                        if any(h in shift_name for h in ["休", "公休", "有給", "特休"]):
                            main_info = "有給" if "有給" in shift_name else "休日"
                            rows_final.append([f"{key}_{main_info}", target_date, "", target_date, "", "True", "", key])
                        else:
                            shift_cal(key, target_date, col, shift_name, shift_code, other_shift, t_sched, rows_final)
                    
                    if rows_final:
                        st.subheader(f"📍 {key} の解析結果")
                        st.dataframe(pd.DataFrame(rows_final, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
                st.success("解析完了！")
            except Exception as e: st.error(f"解析エラー: {e}")
