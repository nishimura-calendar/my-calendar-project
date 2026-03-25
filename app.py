import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule, data_integration

# 各種ID設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換（最終統合版）")

def get_gapi_service():
    try:
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    # 記号の正規化
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    
    # 時程表の準備
    t_s = time_schedule.copy()
    t_s.iloc[:, 1] = t_s.iloc[:, 1].astype(str).apply(lambda x: unicodedata.normalize('NFKC', x).strip())
    
    # 自分のシフト行を特定
    my_time_shift = t_s[t_s.iloc[:, 1] == clean_info]
                    
    if not my_time_shift.empty:
        # 終日予定を追加（現在表示されている行）
        final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
        
        prev_val = ""
        # 3列目(index 2)から右端まで、15分刻みの場所をループ
        for t_col in range(2, t_s.shape[1]):
            # 現在の場所名を取得
            raw_val = my_time_shift.iloc[0, t_col]
            # nan や空文字を厳格にチェック
            current_val = str(raw_val).strip() if pd.notna(raw_val) and str(raw_val).lower() != "nan" and str(raw_val).strip() != "" else ""
            
            # 担当場所が変化したタイミングを検知
            if current_val != prev_val:
                if current_val != "": 
                    # --- 引き継ぎ情報の特定 ---
                    handing_over_dep = "" 
                    mask_h = pd.Series([False] * len(t_s)) 
                    
                    if prev_val == "": 
                        # 勤務開始時
                        mask_h = (t_s.iloc[:, t_col].astype(str).replace('nan','') == "") & \
                                 (t_s.iloc[:, t_col-1].astype(str).replace('nan','') != "")
                        if mask_h.any(): handing_over_dep = "(交代)"
                    else:
                        # 部署移動時
                        handing_over_dep = f"({prev_val})" 
                        mask_h = (t_s.iloc[:, t_col].astype(str).str.strip() == prev_val)
                        
                        # 直前の予定に「終了時刻」をセット
                        if len(final_rows) > 0 and final_rows[-1][5] == "False":
                            final_rows[-1][4] = str(t_s.iloc[0, t_col]).strip()
                    
                    mask_t = (t_s.iloc[:, t_col-1].astype(str).str.strip() == current_val)   
                    
                    handing_over = ""; taking_over = ""
                    for i in range(0, 2):
                        mask = mask_h if i == 0 else mask_t
                        search_keys = t_s.loc[mask, t_s.columns[1]].unique()
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.strip().isin(search_keys)]
                        names = target_rows.iloc[:, 0].unique().astype(str)
                        
                        if i == 0:
                            staff = f"to {'・'.join(names)}" if len(names) > 0 else ""
                            handing_over = f"{handing_over_dep}{staff}"
                        else:
                            staff = f"from {'・'.join(names)}" if len(names) > 0 else ""
                            taking_over = f"【{current_val}】{staff}"    
                    
                    # --- ここが詳細行 ---
                    final_rows.append([
                        f"{handing_over}=>{taking_over}", 
                        target_date, 
                        str(t_s.iloc[0, t_col]).strip(), # 開始時刻
                        target_date, 
                        "", # 終了時刻
                        "False", 
                        "", 
                        key
                    ])
                else:
                    # 勤務終了時
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = str(t_s.iloc[0, t_col]).strip()
            
            prev_val = current_val
            
service = get_gapi_service()
if service:
    if st.button("① PDFリスト取得"):
        res = service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        st.session_state['pdf_files'] = res.get('files', [])

    if 'pdf_files' in st.session_state and st.session_state['pdf_files']:
        selected_name = st.selectbox("PDF選択", [f['name'] for f in st.session_state['pdf_files']])
        selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

        if st.button("② 解析実行"):
            with st.spinner("処理中..."):
                time_sched_dic = time_schedule(service, TIME_TABLE_ID)
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
                        shift_code = str(my_s.iloc[0, col]).strip()
                        lower_val = str(my_s.iloc[1, col]).strip() if my_s.shape[0] > 1 else ""
                        if not shift_code or shift_code.lower() == "nan": continue
                        target_date = f"{y}/{m}/{col}"
                        
                        if any(h in shift_code for h in ["休", "有給", "公休"]):
                            rows_res.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                        elif "@" in lower_val:
                            parts = lower_val.split("@")
                            s_t = f"{re.search(r'\d+', parts[0]).group().zfill(2)}:00" if len(parts)>0 else ""
                            e_t = f"{re.search(r'\d+', parts[1]).group().zfill(2)}:00" if len(parts)>1 else ""
                            rows_res.append([f"{key}_{shift_code}", target_date, s_t, target_date, e_t, "False", "PDF時間指定", key])
                        else:
                            shift_cal(key, target_date, col, shift_code, my_s, other_s, t_s, rows_res)
                    
                    if rows_res:
                        st.subheader(f"📍 {key}")
                        st.dataframe(pd.DataFrame(rows_res, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"]))
