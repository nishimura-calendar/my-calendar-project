import pandas as pd
import io
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

# 固定設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換 (2段構造＆境界判定版)")

# --- Google API認証 ---
def get_gapi_service():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("Secretsに認証情報がありません。")
            return None
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

# --- コアロジック: 時程表から詳細スケジュールをひろう ---
def shift_cal(key, target_date, col, shift_code, my_s, other_s, t_s, rows_res):
    # 終日予定を追加
    rows_res.append([f"{key}_{shift_code}", target_date, "", target_date, "", "True", "", key])
    
    # 時程表（t_s）から一致するシフト行を探す
    sched_clean = t_s.fillna("").astype(str)
    my_time_shift = sched_clean[sched_clean.iloc[:, 1].str.strip() == shift_code]
    
    if my_time_shift.empty:
        return

    prev_val = ""
    last_row_idx = -1
    
    # 時程表の時刻列をスキャン
    for t_col in range(2, t_s.shape[1]):
        current_val = my_time_shift.iloc[0, t_col].strip()
        next_t = str(t_s.iloc[0, t_col + 1]).strip() if t_col + 1 < t_s.shape[1] else str(t_s.iloc[0, t_col]).strip()

        if not current_val:
            if prev_val != "" and last_row_idx != -1:
                rows_res[last_row_idx][4] = str(t_s.iloc[0, t_col]).strip()
            prev_val = ""
            continue
        
        if current_val == prev_val and last_row_idx != -1:
            rows_res[last_row_idx][4] = next_t
            continue

        if last_row_idx != -1:
            rows_res[last_row_idx][4] = str(t_s.iloc[0, t_col]).strip()

        # 引き継ぎ相手の特定 (to / from)
        handing_over = "" 
        if prev_val != "":
            mask_to = (t_s.iloc[:, t_col] == prev_val)
            keys_to = t_s.loc[mask_to, t_s.columns[1]]
            names_to = other_s[other_s.iloc[:, col].isin(keys_to)].iloc[:, 0].unique()
            staff_to = f"to {'・'.join(names_to)}" if len(names_to) > 0 else ""
            handing_over = f"({prev_val}){staff_to}"

        mask_from = (t_s.iloc[:, t_col-1] == current_val)
        keys_from = t_s.loc[mask_from, t_s.columns[1]]
        names_from = other_s[other_s.iloc[:, col].isin(keys_from)].iloc[:, 0].unique()
        staff_from = f"from {'・'.join(names_from)}" if len(names_from) > 0 else ""
        taking_over = f"【{current_val}】{staff_from}"

        rows_res.append([f"{handing_over}=>{taking_over}", target_date, str(t_s.iloc[0, t_col]).strip(), target_date, next_t, "False", "", key])
        last_row_idx = len(rows_res) - 1
        prev_val = current_val

# --- メイン処理 ---
service = get_gapi_service()
if service:
    if st.button("① Google DriveからPDFを取得"):
        results = service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        st.session_state['pdf_files'] = results.get('files', [])
        st.success("PDFを取得しました")

    if 'pdf_files' in st.session_state and st.session_state['pdf_files']:
        selected_name = st.selectbox("PDFを選択", [f['name'] for f in st.session_state['pdf_files']])
        selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

        if st.button("② 解析を実行"):
            with st.spinner("解析中..."):
                time_sched_dic = time_schedule_from_drive(service, TIME_TABLE_ID)
                
                pdf_req = service.files().get_media(fileId=selected_id)
                pdf_stream = io.BytesIO()
                downloader = MediaIoBaseDownload(pdf_stream, pdf_req)
                done = False
                while not done: _, done = downloader.next_chunk()
                
                pdf_stream.seek(0)
                pdf_dic = pdf_reader(pdf_stream, TARGET_STAFF)
                pdf_stream.seek(0)
                y, m = extract_year_month(pdf_stream)
                
                integrated = data_integration(pdf_dic, time_sched_dic)
                
                for key, data in integrated.items():
                    rows_res = []
                    my_s, other_s, t_s = data[0], data[1], data[2]
                    
                    for col in range(1, my_s.shape[1]):
                        shift_code = str(my_s.iloc[0, col]).replace('\n', '').strip()
                        lower_val = str(my_s.iloc[1, col]).replace('\n', '').strip() if my_s.shape[0] > 1 else ""
                        
                        if not shift_code or shift_code.lower() == "nan": continue
                        target_date = f"{y}/{m}/{col}"
                        
                        # A. 休日
                        if any(h in shift_code for h in ["休", "有給", "公休"]):
                            rows_res.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                        
                        # B. 下段に「@」がある（本町など）
                        elif "@" in lower_val:
                            parts = lower_val.split("@")
                            s_t, e_t = "", ""
                            if len(parts) >= 2:
                                s_m = re.search(r'\d+', parts[0])
                                e_m = re.search(r'\d+', parts[1])
                                if s_m: s_t = f"{s_m.group().zfill(2)}:00"
                                if e_m: e_t = f"{e_m.group().zfill(2)}:00"
                            rows_res.append([f"{key}_{shift_code}", target_date, s_t, target_date, e_t, "False", "PDF直接指定", key])
                        
                        # C. 通常シフト
                        else:
                            shift_cal(key, target_date, col, shift_code, my_s, other_s, t_s, rows_res)
                    
                    if rows_res:
                        st.subheader(f"📍 勤務地: {key}")
                        st.dataframe(pd.DataFrame(rows_res, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]), use_container_width=True)
