import streamlit as st
import pandas as pd
import io
import os
import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.credentials import Credentials
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
    # 本番運用時は st.secrets から認証情報を取得する設定が必要
    # 今回は簡略化のため、既存のtoken.json等がある前提
    creds = Credentials.from_authorized_user_info(st.secrets["gcp_service_account"])
    return build(service_name, version, credentials=creds)

# --- シフト詳細計算ロジック (ご提示のロジック) ---
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

# 手順1・2: Gmail検索ボタン
if st.button("① メールを検索"):
    st.info("Gmailから『細谷一男』様、過去30日以内のPDFメールを検索中...")
    # Gmail API呼び出し (service.users().messages().list)
    # 検索結果を st.session_state.mails に格納
    st.session_state['mails'] = [
        {"name": "免税店シフト表_1月.pdf", "id": "msg_123", "date": "2026/03/01"}
    ]

# 手順3: 該当メール表示
if 'mails' in st.session_state:
    mail_options = {f"{m['name']} ({m['date']})": m['id'] for m in st.session_state['mails']}
    selected_mail_id = st.selectbox("処理するファイルを選択", options=list(mail_options.keys()))

    # 手順4: 実行ボタン
    if st.button("② 実行（Drive保存 ＆ カレンダー登録）"):
        with st.spinner("データ解析中..."):
            # 1. Driveから時程表を取得
            # time_sched_dic = time_schedule_from_drive(drive_service, TIME_TABLE_ID)
            
            # 2. PDF解析ロジックの実行
            # (ここでは中略。practice_0の各関数を呼び出し)
            
            # 3. カレンダー登録 (色指定付き)
            for key, data_list in shift_dic.items():
                my_daily_shift, other_daily_shift, time_sched_df = data_list 
                
                rows_holiday, rows_event, rows_shift = [], [], []

                for col in range(1, my_daily_shift.shape[1]):
                    # ... (ここにutils_0.pyの振り分けロジックを記述) ...

                    # カレンダー登録時に色を指定
                    # 休日なら COLOR_MAP["holiday"] (赤)
                    # イベントなら COLOR_MAP["event"] (青)
                    # 通常シフトなら COLOR_MAP["shift"] (緑)
            
                    st.success("完了しました！カレンダーをご確認ください。")
                    
