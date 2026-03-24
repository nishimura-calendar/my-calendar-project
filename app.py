import streamlit as st
import pandas as pd
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive, data_integration

# 固定設定
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
SHIFT_PDF_FOLDER_ID = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換 (引き継ぎ＆結合ロジック搭載版)")

# --- Google API認証 ---
def get_gapi_service():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("Secretsに 'gcp_service_account' が設定されていません。")
            return None
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

# --- コアロジック: 引き継ぎ相手の特定と予定の結合 ---
def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """通常シフトの詳細（時間別引き継ぎ）を計算し、final_rowsに格納する"""
    # 終日イベントの追加（シフトコードそのものの予定）
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
                    # prev_val(渡す部署〈何でもok〉)・current_val
                    handing_over_department = "" # 渡す部署（私の部署）=""、初期化
                    # 渡す人=（false*行）で、初期化
                    mask_handing_over = pd.Series([False] * len(time_schedule)) # 渡すの人（初期化）
                    
                    if prev_val == "": 
                        mask_handing_over = (time_schedule.iloc[:, t_col] == "") & (time_schedule.iloc[:, t_col-1] != "")
                        
                        # 条件に合う行が1つでもあれば "(交代)" をセット
                        if mask_handing_over.any():
                            handing_over_department = "(交代)"
                        else:
                            handing_over_department = ""
                    else:
                        # prev_val(空白以外)・current_val
                        handing_over_department = f"({prev_val})" 
                        mask_handing_over = (time_schedule.iloc[:, t_col] == prev_val)
                        final_rows[-1][4] = time_schedule.iloc[0, t_col] # 前の予定の終了時間をセット
                    
                    mask_taking_over =pd.Series([False] * len(time_schedule))
                    mask_taking_over = (time_schedule.iloc[:, t_col-1] == current_val)   
                    
                    handing_over = ""
                    taking_over = ""

                    for i in range(0, 2): # 0～1で2は循環範囲に入らない

                        mask = mask_handing_over if i == 0 else mask_taking_over
                        search_keys = time_schedule.loc[mask, time_schedule.columns[1]] # time_scheduleの１列目を検索してmaskのかかったシフトコードを抽出
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys)] # other_staff_shiftのcol列目の行を検索してsearch_keysのある行を抽出
                        names_series = target_rows.iloc[:, 0] # other_staff_shiftのtarget_rowsの０列目のstaff名を抽出
                        
                        if i == 0:
                            staff_names =f"to {"・".join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            handing_over = f"{handing_over_department}{staff_names}"
                        else:
                            staff_names =f"from {"・".join(names_series.unique().astype(str))}" if not names_series.empty else ""
                            taking_over = f"【{current_val}】{staff_names}"    
                    
                    final_rows.append([
                        f"{handing_over}=>{taking_over}", 
                        target_date, 
                        time_schedule.iloc[0, t_col], 
                        target_date, 
                        "", 
                        "False", 
                        "", 
                        ""
                    ])
                else:
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]    
            prev_val = current_val

# --- メイン画面 ---
service = get_gapi_service()

if service:
    # PDFリスト取得
    if st.button("① Google DriveからPDFを取得"):
        results = service.files().list(q=f"'{SHIFT_PDF_FOLDER_ID}' in parents and mimeType='application/pdf'").execute()
        st.session_state['pdf_files'] = results.get('files', [])
        st.success(f"{len(st.session_state['pdf_files'])}件のPDFを取得しました")

    # 解析実行
    if 'pdf_files' in st.session_state and st.session_state['pdf_files']:
        selected_name = st.selectbox("PDFを選択", [f['name'] for f in st.session_state['pdf_files']])
        selected_id = next(f['id'] for f in st.session_state['pdf_files'] if f['name'] == selected_name)

        if st.button("② 解析を実行"):
            with st.spinner("解析中..."):
                # データの読み込み
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
                
                # 統合データの作成
                shift_dic = data_integration(pdf_dic, time_sched_dic)
                
                for key, data_list in shift_dic.items():
                    if len(data_list) < 3: continue
                    
                    rows_res = []
                    my_s = data_list[0]     # 自分のシフト
                    other_s = data_list[1]  # 自分以外のスタッフのシフト
                    t_s = data_list[2]      # 時程表
                    
                    for col in range(1, my_s.shape[1]):
                        shift_info = str(my_s.iloc[1, col]).strip()
                        if not shift_info or shift_info.lower() == "nan": continue
                        
                        target_date = f"{y}/{m}/{col}"
                        # 休日/休暇の判定
                        if any(h in shift_info for h in ["休", "有給", "公休", "有休"]):
                            rows_res.append([f"{key}_休日", target_date, "", target_date, "", "True", "", key])
                        else:
                            # 通常勤務時の詳細スケジュール作成（引き継ぎ相手も特定）
                            shift_cal(key, target_date, col, shift_info, my_s, other_s, t_s, rows_res)
                    
                    if rows_res:
                        st.subheader(f"📍 勤務地: {key}")
                        df_final = pd.DataFrame(rows_res, columns=["内容", "開始日", "開始時間", "終了日", "終了時間", "終日", "詳細", "場所"])
                        st.dataframe(df_final)
