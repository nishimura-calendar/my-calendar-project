import streamlit as st
import pandas as pd
import io
import os
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.credentials import Credentials

# practice_0.pyからロジックを読み込み
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration, working_hours

# --- 設定 ---
TIME_TABLE_ID = "1g6REpegOHEXsY30edTCqie-h873FOKAF"
CSV_FOLDER_ID = "19GBObKKJQylZXLaxfApt3iSgA1893TKa"
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
    # Secretsからサービスアカウント情報を取得して認証
    creds = Credentials.from_authorized_user_info(st.secrets["gcp_service_account"])
    return build(service_name, version, credentials=creds)

# --- シフト詳細計算ロジック (utils_0.pyから移植) ---
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

if st.button("① メールを検索"):
    st.info("Gmailから最新のシフトPDFメールを検索中...")
    # ※ここではデモ用にリストを作成していますが、実際はGmail APIで取得します
    st.session_state['mails'] = [{"name": "免税店シフト表_3月.pdf", "id": "file_id_example", "date": "2026/03/01"}]

if 'mails' in st.session_state:
    selected_mail = st.selectbox("処理するファイルを選択", options=[m['name'] for m in st.session_state['mails']])

    if st.button("② 実行（Drive保存 ＆ カレンダー登録）"):
        with st.spinner("処理中..."):
            try:
                # サービス開始
                drive_service = get_gapi_service('drive', 'v3')
                
                # 1. Driveから時程表を取得
                time_sched_dic = time_schedule_from_drive(drive_service, TIME_TABLE_ID)
                
                # 2. PDFの読み込み (実際はDriveからダウンロードしたストリーム)
                # ここではpdf_readerに渡すためのダミー処理（実際はselected_mailから取得）
                pdf_stream = io.BytesIO() # ここにDriveからのデータをダウンロード
                pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
                year_month = "2026年3月" # extract_year_month(pdf_stream)
                
                # 3. データの統合
                shift_dic = data_integration(pdf_dic, time_sched_dic)
                
                # 4. 三要素（休日・イベント・シフト）の振り分けロジック
                holiday_keywords = ["休", "公休", "有給", "特休"]
                special_location = "本町"
                columns = ["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]

                for key, data_list in shift_dic.items():
                    rows_holiday, rows_event, rows_shift = [], [], []
                    my_daily_shift, other_daily_shift, time_sched_df = data_list 

                    for col in range(1, my_daily_shift.shape[1]):
                        shift_info = str(my_daily_shift.iloc[0, col]).strip()
                        if not shift_info or shift_info.lower() == "nan": continue

                        # 日付作成 (YYYY/MM/DD)
                        d_match = re.search(r'(\d+)年(\d+)月', year_month)
                        y, m = (d_match.group(1), d_match.group(2)) if d_match else ("2026", "3")
                        target_date = f"{y}/{m}/{col}"

                        if any(h in shift_info for h in holiday_keywords):
                            rows_holiday.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", ""])
                        elif special_location in shift_info:
                            rows_event.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", ""])
                            if my_daily_shift.iloc[1, col] != "":
                                s, e = working_hours(my_daily_shift.iloc[1, col])
                                rows_event.append([f"{shift_info}", target_date, s, target_date, e, "False", "", ""])
                        else:
                            shift_cal(key, target_date, col, shift_info, my_daily_shift, other_daily_shift, time_sched_df, rows_shift)
                    
                    # --- カレンダー登録 & Drive保存 (擬似コード) ---
                    # ここでCOLOR_MAPを利用してGoogle Calendar APIへ送信
                    # 例: insert_calendar(rows_shift, color=COLOR_MAP["shift"])
                
                st.success("全ての処理が完了しました！カレンダーをご確認ください。")
                st.balloons()
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
