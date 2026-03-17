import streamlit as st
import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# 自作モジュールのインポート
try:
    from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration
except Exception as e:
    st.error(f"❌ モジュール読み込みエラー: {e}")
    st.stop()

# 基本設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト管理システム", layout="wide")
st.title("📅 シフトカレンダー一括登録")

def get_gapi_service(service_name, version):
    """Google APIサービスを取得（認証エラー修正済み）"""
    info = dict(st.secrets["gcp_service_account"])
    scopes = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/drive.readonly']
    # scopesはキーワード引数として渡す
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build(service_name, version, credentials=creds)

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """役割が連続するセルを結合して1つの予定を作成する"""
    # 終日予定を追加
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 自分のシフトコード（12等）に対応する時間割を取得
    shift_code = str(my_daily_shift.iloc[1, col]).strip()
    sched_clean = time_schedule.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_code]
    
    if not my_time_shift.empty:
        prev_label = None
        for t_col in range(2, time_schedule.shape[1]):
            # 15分ごとの役割（前・後・横など）
            current_role = my_time_shift.iloc[0, t_col].strip()
            if not current_role:
                prev_label = None
                continue
            
            # --- 引き継ぎ相手の特定（デスクトップ版のロジック） ---
            mask_handing = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
            handing_text = "(交代)" if mask_handing.any() else ""
            
            other_codes = other_staff_shift.iloc[:, col].astype(str).str.replace(r'[\s　]', '', regex=True)
            names_to = other_staff_shift[other_codes.isin(time_schedule.loc[mask_handing, 1])].iloc[:, 0].unique()
            label_to = f"to {'・'.join(names_to)}" if len(names_to) > 0 else ""
            
            # ラベル内容を構築（ここから時間を排除することで結合を可能にする）
            full_label = f"{handing_text}{label_to}=>【{current_role}】"
            
            # --- 連続判定と結合ロジック ---
            if full_label == prev_label and final_rows:
                # 前の15分と同じ役割なら、予定の「終了時間」を更新するだけ
                next_time_label = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else str(time_schedule.iloc[0, t_col]).strip()
                final_rows[-1][4] = next_time_label
            else:
                # 違う役割になったら新規行を作成
                start_t = str(time_schedule.iloc[0, t_col]).strip()
                end_t = str(time_schedule.iloc[0, t_col+1]).strip() if t_col+1 < time_schedule.shape[1] else start_t
                final_rows.append([full_label, target_date, start_t, target_date, end_t, "False", "", key])
                prev_label = full_label

# --- UI操作フロー ---
if st.button("① Google DriveからPDFを確認"):
    try:
        drive_service = get_gapi_service('drive', 'v3')
        items = drive_service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute().get('files', [])
        if items:
            st.session_state['pdf_files'] = items
            st.success(f"{len(items)}件のPDFファイルが見つかりました。")
        else:
            st.warning("指定されたフォルダにPDFがありません。")
    except Exception as e:
        st.error(f"接続エラー: {e}")

if 'pdf_files' in st.session_state:
    selected_name = st.selectbox("解析するPDFを選択してください", [f['name'] for f in st.session_state['pdf_files']])
    selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

    if st.button("② 解析実行"):
        with st.spinner("PDFと時間割を照合中..."):
            try:
                drive_service = get_gapi_service('drive', 'v3')
                # 時間割データの取得
                time_sched_dic = time_schedule_from_drive(drive_service, TIME_TABLE_ID)
                
                # PDFデータの取得
                pdf_req = drive_service.files().get_media(fileId=selected_id)
                pdf_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(pdf_stream, pdf_req)
                done = False
                while not done: _, done = downloader.next_chunk()
                
                pdf_stream.seek(0)
                pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
                pdf_stream.seek(0)
                y, m = extract_year_month(pdf_stream)
                
                # データの統合
                integrated = data_integration(pdf_dic, time_sched_dic)
                
                if not integrated:
                    st.warning("PDFの勤務地と時間割のシート名が一致しませんでした。")
                
                for key, data_list in integrated.items():
                    rows_final = []
                    my_shift, other_shift, t_sched = data_list[0], data_list[1], data_list[2]
                    
                    for col in range(1, my_shift.shape[1]):
                        shift_info = str(my_shift.iloc[0, col]).strip()
                        if not shift_info or shift_info.lower() == "nan":
                            continue
                        
                        target_date = f"{y}/{m}/{col}"
                        # 休日判定
                        if any(h in shift_info for h in ["休", "有給", "公休", "特休"]):
                            rows_final.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                        else:
                            # 通常シフトの解析・結合
                            shift_cal(key, target_date, col, shift_info, my_shift, other_shift, t_sched, rows_final)
                    
                    if rows_final:
                        st.subheader(f"📍 {key} ターミナルの解析結果")
                        df_res = pd.DataFrame(rows_final, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"])
                        st.dataframe(df_res, use_container_width=True)
                
                st.success("解析が完了しました。上の表で内容を確認してください。")
            except Exception as e:
                st.error(f"解析中にエラーが発生しました: {e}")
