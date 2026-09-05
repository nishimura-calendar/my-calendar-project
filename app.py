import streamlit as st
import pandas as pd
import io
import pdfplumber
import re
import calendar
import unicodedata
import fitz  # PyMuPDF
import datetime
import time  # タイムラグを設けるために利用します
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.auth.transport.requests import Request

# --- PDFを画面に画像として表示する補助関数 ---
def display_pdf_as_images(file_bytes):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            st.image(img_bytes, caption=f"PDF プレビュー (ページ {page_num + 1})", use_container_width=True)
    except Exception as e:
        st.error(f"PDFのプレビュー表示に失敗しました: {e}")

# --- Google Driveから過去30日のPDFをリスト化する補助関数 ---
def get_recent_pdfs_from_drive(service):
    thirty_days_ago = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).isoformat() + 'Z'
    query = f"mimeType='application/pdf' and createdTime >= '{thirty_days_ago}'"
    
    results = service.files().list(
        q=query,
        orderBy="createdTime desc",
        pageSize=10,
        fields="files(id, name, createdTime)"
    ).execute()
    return results.get('files', [])

def download_pdf_from_drive(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# --- [1] 時程表読み込み ---
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

def process_data(df):
    location_data = {}
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else df.index[-1] + 1
        schedule = df.iloc[start_idx:end_idx].copy()
        for col_idx in range(3, schedule.shape[1]):
            val = schedule.iloc[0, col_idx]
            try:
                f_val = float(val)
                schedule.iloc[0, col_idx] = format_time(f_val)
            except (ValueError, TypeError):
                schedule = schedule.iloc[:, :col_idx]
                break
        location_data[key] = schedule
    return location_data

@st.cache_data(ttl=3600)
def load_and_process_data():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    service = build('drive', 'v3', credentials=creds)
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    while not downloader.next_chunk()[1]: pass
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

# --- 補助関数：ベース値取得（"値_i" から "値" 部分を取り出す） ---
def get_base_value(val):
    if not val or pd.isna(val):
        return ""
    return str(val).split('_')[0].strip()

# --- 補助関数：カレンダーの自動取得・作成 ---
def get_or_create_calendar(service, calendar_name):
    calendar_list = service.calendarList().list().execute()
    for cal in calendar_list.get('items', []):
        if cal.get('summary') == calendar_name:
            return cal.get('id')
    
    new_cal = {'summary': calendar_name}
    created_cal = service.calendars().insert(body=new_cal).execute()
    return created_cal.get('id')

# --- 補助関数：Keyやシフトコードに応じた青系カラーIDの自動変化 ---
def get_color_id(shift_code, time_shift_check=None, found_key=None):
    shift_code_str = str(shift_code)
    base_shift_code = get_base_value(shift_code_str)
    
    if any(holiday in base_shift_code for holiday in ["休", "休日", "公休", "有休", "有給"]):
        return "11"
    
    blue_palette = ["7", "9", "1"]
    assigned_blue = "7"
    if found_key:
        hash_val = sum(ord(c) for c in str(found_key))
        assigned_blue = blue_palette[hash_val % len(blue_palette)]

    if found_key and (found_key in base_shift_code or found_key == base_shift_code):
        return assigned_blue
        
    if time_shift_check is not None and not time_shift_check.empty:
        check_bases = time_shift_check.iloc[:, 1].apply(get_base_value)
        if (check_bases == base_shift_code).any():
            return assigned_blue
            
    return assigned_blue

# --- アプリケーションを初期状態に戻すためのヘルパー関数 ---
def reset_to_initial_state():
    for key in list(st.session_state.keys()):
        if key != 'data_dict':
            del st.session_state[key]
 
# --- [2] メイン処理 ---
st.title("シフト表解析システム")

if 'data_dict' not in st.session_state:
    st.session_state.data_dict = load_and_process_data()

# =========================================================
# 【リセットボタン】サイドバーに常設
# =========================================================
st.sidebar.title("システムメニュー")
if st.sidebar.button("🔄 最初からやり直す（リセット）"):
    reset_to_initial_state()
    st.success("システムをリセットしました。初期画面に戻ります。")
    st.rerun()

st.sidebar.divider()

if 'loaded_pdf_bytes' not in st.session_state:
    st.session_state.loaded_pdf_bytes = None
    st.session_state.loaded_pdf_name = None

if st.session_state.loaded_pdf_bytes is None:
    upload_option = st.radio("PDFの取得方法を選択してください", ["手動アップロード", "Google Driveから選択"], index=0)

    uploaded_file_obj = None

    if upload_option == "手動アップロード":
        uploaded_file_obj = st.file_uploader("PDFシフト表をアップロード", type="pdf")
        if uploaded_file_obj is not None:
            st.session_state.loaded_pdf_bytes = uploaded_file_obj.getvalue()
            st.session_state.loaded_pdf_name = uploaded_file_obj.name
            st.rerun()
    else:
        try:
            creds_dict = st.secrets["google_oauth_credentials"]
            creds_drive = Credentials.from_authorized_user_info(
                creds_dict, 
                scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
            )
            drive_service = build('drive', 'v3', credentials=creds_drive)
            
            files = get_recent_pdfs_from_drive(drive_service)
            
            if files:
                selected_file = st.selectbox(
                    "解析したいファイルを選択してください (過去30日以内)", 
                    files, 
                    format_func=lambda x: f"{x['name']} (作成日: {x['createdTime'][:10]})"
                )
                if st.button("選択したPDFを読み込む"):
                    fh = download_pdf_from_drive(drive_service, selected_file['id'])
                    st.session_state.loaded_pdf_bytes = fh.getvalue()
                    st.session_state.loaded_pdf_name = selected_file['name']
                    st.success(f"「{selected_file['name']}」を読み込みました。")
                    st.rerun()
            else:
                st.warning("最近30日以内に保存されたPDFは見つかりませんでした。")
        except Exception as e:
            st.error(f"Google Driveからのファイル取得に失敗しました: {e}")
            
    st.stop()

uploaded_pdf = io.BytesIO(st.session_state.loaded_pdf_bytes)
uploaded_pdf.name = st.session_state.loaded_pdf_name

uploaded_pdf.seek(0)
file_bytes = uploaded_pdf.getvalue()

if 'last_file_bytes' not in st.session_state or st.session_state.last_file_bytes != file_bytes:
    st.session_state.last_file_bytes = file_bytes
    st.session_state.ym_confirmed = False
    for key in ['use_pdf_choice', 'df_calendar', 'show_conflict_options']:
        if key in st.session_state:
            del st.session_state[key]

uploaded_pdf.seek(0)
with pdfplumber.open(uploaded_pdf) as pdf:
    pdf_full_text = unicodedata.normalize('NFKC', pdf.pages[0].extract_text())
    
    matched_keys = []
    for key in st.session_state.data_dict.keys():
        pos = pdf_full_text.find(str(key))
        if pos != -1:
            matched_keys.append((key, pos))
    
    if matched_keys:
        matched_keys.sort(key=lambda x: x[1])
        found_key = matched_keys[0][0]
    else:
        found_key = None

uploaded_pdf.seek(0)
with pdfplumber.open(uploaded_pdf) as pdf:
    tables = pdf.pages[0].extract_tables()
    df_pdf = pd.DataFrame(tables[0]) if tables else pd.DataFrame()

if not found_key:
    st.error("勤務地(Key)がPDFから特定できませんでした。")
    display_pdf_as_images(file_bytes)
    st.stop()

A_date, A_day = None, None
for row in range(df_pdf.shape[0] - 1):
    for col in range(df_pdf.shape[1]):
        val_up = str(df_pdf.iloc[row, col])
        val_down = str(df_pdf.iloc[row+1, col])
        if re.match(r'^(0?[1-9]|[12][0-9]|3[01])$', val_up) and val_down in "月火水木金土日":
            A_date, A_day = int(val_up), val_down

if not A_date:
    st.error("日付と曜日が抽出できませんでした。")
    display_pdf_as_images(file_bytes)
    st.stop()

filename = uploaded_pdf.name
year_match = re.search(r'(\d{4})', filename)
month_match = re.search(r'(\d{1,2})月', filename)

if year_match and month_match:
    y, m = int(year_match.group(1)), int(month_match.group(1))
else:
    st.warning("ファイル名から年月が取得できませんでした。プレビューを確認してください。")
    display_pdf_as_images(file_bytes)
    
    choice = st.radio(
        "このファイルを使用しますか？", 
        ["選択してください", "はい", "いいえ"], 
        index=0, 
        key="use_pdf_choice"
    )
    
    if choice == "選択してください":
        st.info("👆 上記のプレビューを確認し、「はい」または「いいえ」を選択してください。")
        st.stop()
    elif choice == "いいえ":
        st.warning("このファイルの利用がキャンセルされました。サイドバーのリセットボタンまたは別の操作を行ってください。")
        st.stop()
    else:
        year_text_match = re.search(r'(\d{4})\s*年', pdf_full_text)
        y = int(year_text_match.group(1)) if year_text_match else 2026
        month_text_match = re.search(r'(\d{1,2})\s*月', pdf_full_text)
        m = int(month_text_match.group(1)) if month_text_match else 2

_, last_day_num = calendar.monthrange(y, m)
last_day_w = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, last_day_num)]

if A_date == last_day_num and A_day == last_day_w:
    pass 
else:
    st.error("整合性不一致: アップロードされたシフト表の年月が期待値と異なります。")
    st.write(f"抽出された最終日: {A_date}日 ({A_day}曜日)")
    st.write(f"カレンダー上の最終日: {last_day_num}日 ({last_day_w}曜日)")
    display_pdf_as_images(file_bytes)
    st.stop()

st.divider()

staff_data = []
for idx in range(0, df_pdf.shape[0], 2):
    name_val = str(df_pdf.iloc[idx, 0])
    if name_val in st.session_state.data_dict.keys():
        continue
    
    if name_val != 'None':
        clean_name = name_val.split('\n')[0].strip()
    else:
        clean_name = "該当なし"
    staff_data.append((idx, clean_name))
    
target_name = st.selectbox("スタッフを選択してください", [s[1] for s in staff_data])
target_idx = [s[0] for s in staff_data if s[1] == target_name][0]

my_df = df_pdf.iloc[target_idx : target_idx + 2, :].copy()
my_df.iloc[0, 0] = target_name
my_df.iloc[1, 0] = "" 

other_rows = []
for idx, name in staff_data:
    if name != target_name:
        row = df_pdf.iloc[idx : idx+1].copy()
        row.iloc[0, 0] = name
        other_rows.append(row)

other_df = pd.concat(other_rows) if other_rows else pd.DataFrame()

st.divider()

def get_staff_names(codes, other_staff_shift, col):
    if other_staff_shift.empty:
        return []
    base_codes = [get_base_value(c) for c in codes]
    col_bases = other_staff_shift.iloc[:, col].apply(get_base_value)
    mask = col_bases.isin(base_codes)
    return other_staff_shift.loc[mask, other_staff_shift.columns[0]].tolist()

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    time_shift = time_schedule.fillna("").astype(str)
    base_shift_info = get_base_value(shift_info)
    
    time_shift_bases = time_shift.iloc[:, 1].apply(get_base_value)
    if not (time_shift_bases == base_shift_info).any():
        return
       
    my_time_shift = time_shift[time_shift_bases == base_shift_info]
    if my_time_shift.empty:
        return

    prev_val_base = ""
    row_data = my_time_shift.iloc[0]

    for t_col in range(3, my_time_shift.shape[1]):
        raw_current_val = row_data[t_col]
        current_val_base = get_base_value(raw_current_val)
        subject, start, change, takeover, break_change, end = "", "", "", "", "", ""                    
      
        if current_val_base != prev_val_base:
            if current_val_base != "":
                final_rows.append([subject, target_date, "", target_date, "", "False", "", found_key])
                start_time = time_shift.iloc[0, t_col]
            
                if (row_data[3:t_col] == "").all():
                    start = "(出勤)："
                    
                prev_raw_val = row_data[t_col - 1]
                if get_base_value(prev_raw_val) == "":              
                    mask_change = (time_shift.iloc[:, t_col - 1].apply(get_base_value) != "") & (time_shift.iloc[:, t_col].apply(get_base_value) == "")
                    paired_staff = []
                    for idx in time_shift.index[mask_change]:
                        places = time_shift.loc[idx, time_shift.columns[t_col - 1]]
                        codes = time_shift.loc[idx, time_shift.columns[1]]
                        staff = get_staff_names([codes], other_staff_shift, col)
                        for name in staff:
                            paired_staff.append(f"{name}({places})")       
                    
                    change_formatted = ",".join(paired_staff)
                    change = f"{change_formatted}▷" if change_formatted else ""
                else:
                    final_rows[-2][4] = time_shift.iloc[0, t_col]                             
                    handover_codes = time_shift.loc[time_shift.iloc[:, t_col].apply(get_base_value) == prev_val_base, time_shift.columns[1]]
                    handover_staff = get_staff_names(handover_codes, other_staff_shift, col)
                    handover = f"to {','.join(handover_staff)}"
                    final_rows[-2][0] += handover
                
                takeover_codes = time_shift.loc[time_shift.iloc[:, t_col - 1].apply(get_base_value) == current_val_base, time_shift.columns[1]]
                takeover_staff = get_staff_names(takeover_codes, other_staff_shift, col)
                takeover = f"from {','.join(takeover_staff)}【{current_val_base}】" if takeover_staff else f"from 【{current_val_base}】"

                subject = start + change + takeover
                final_rows[-1][0] = subject
                final_rows[-1][2] = start_time
               
            else:
                mask_break = (time_shift.iloc[:, t_col - 1].apply(get_base_value) == "") & (time_shift.iloc[:, t_col].apply(get_base_value) != "")
                paired_staff = []
                for idx in time_shift.index[mask_break]:
                    places = time_shift.loc[idx, time_shift.columns[t_col]]
                    codes = time_shift.loc[idx, time_shift.columns[1]]
                    staff = get_staff_names([codes], other_staff_shift, col)
                    for name in staff:
                        paired_staff.append(f"{name}({places})")

                break_formatted = ",".join(paired_staff)
                break_change = f"▷{break_formatted}" if break_formatted else ""
                                        
                if (row_data[t_col:] == "").all():
                    end = "：(退勤)"
                end_time = time_shift.iloc[0, t_col]
                
                handover_codes = time_shift.loc[time_shift.iloc[:, t_col].apply(get_base_value) == prev_val_base, time_shift.columns[1]]
                handover_staff = get_staff_names(handover_codes, other_staff_shift, col)
                handover = f"to {','.join(handover_staff)}"                   

                final_rows[-1][0] += handover + break_change + end   
                final_rows[-1][4] = end_time                            
            
        prev_val_base = current_val_base

if st.button("カレンダー登録用データを生成"):
    final_rows = []
    time_schedule_df = st.session_state.data_dict[found_key]
    time_shift_check = time_schedule_df.fillna("").astype(str)
    _, last_day_num = calendar.monthrange(y, m)

    for col in range(1, min(my_df.shape[1], last_day_num + 1)):
        day_num = col
        target_date = f"{y}/{m:02d}/{day_num:02d}"
        schedule_val = str(my_df.iloc[0, col]).strip()
        sub_val = str(my_df.iloc[1, col]).strip() if my_df.shape[0] > 1 else ""

        if not schedule_val or schedule_val == "nan": continue

        base_schedule_val = get_base_value(schedule_val)
        time_shift_bases = time_shift_check.iloc[:, 1].apply(get_base_value)

        if (time_shift_bases == base_schedule_val).any():
            start_dt_obj = datetime.datetime.strptime(target_date, "%Y/%m/%d")
            end_dt_obj = start_dt_obj + datetime.timedelta(days=1)
            end_date_str = end_dt_obj.strftime("%Y/%m/%d")
            final_rows.append([f"{found_key}_{base_schedule_val}", target_date, "", end_date_str, "", "True", "", found_key])
            shift_cal(found_key, target_date, col, schedule_val, my_df, other_df, time_schedule_df, final_rows)
        else:
            start_dt_obj = datetime.datetime.strptime(target_date, "%Y/%m/%d")
            end_dt_obj = start_dt_obj + datetime.timedelta(days=1)
            end_date_str = end_dt_obj.strftime("%Y/%m/%d")
            
            final_rows.append([schedule_val, target_date, "", end_date_str, "", "True", "", schedule_val])
            
            time_match = re.search(r'(\d+)[^\d]+(\d+)', sub_val)
            if time_match:
                final_rows.append([schedule_val, target_date, f"{time_match.group(1)}:00", target_date, f"{time_match.group(2)}:00", "False", "", found_key])
    if final_rows:
        st.session_state.df_calendar = pd.DataFrame(final_rows, columns=["Subject", "StartDate", "StartTime", "EndDate", "EndTime", "AllDayEvent", "Description", "Location"])
        st.success(f"カレンダー登録データの生成が完了しました（計 {len(st.session_state.df_calendar)} 件）")
    else:
        st.warning("生成対象のデータがありませんでした。")

if 'df_calendar' in st.session_state:
    st.dataframe(st.session_state.df_calendar)
    
    csv_cal = st.session_state.df_calendar.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
    st.download_button("カレンダー登録用CSVをダウンロード", csv_cal, "calendar_import.csv", "text/csv")

    st.subheader(f"Googleカレンダー連携 (対象勤務地: {found_key})")
    st.info(f"※マイカレンダーに「{found_key}」という名前のカレンダーがない場合は自動的に新規作成されます。")

    # ▼ 2パターンのアラーム時間を設定するUI
    st.markdown("### ⏰ アラーム（通知）設定")
    col_a, col_b = st.columns(2)
    with col_a:
        reminder_first_work = st.number_input("1. 朝の最初の勤務の通知 (分前)", min_value=0, max_value=1440, value=60, step=5)
    with col_b:
        reminder_reopen_work = st.number_input("2. 休憩後最初の勤務の通知 (分前)", min_value=0, max_value=1440, value=30, step=5)
    st.markdown("---")

    target_total_count = len(st.session_state.df_calendar)

    if st.button(f"🚀 {found_key} カレンダーへ新規登録する", key="unique_register_key_button"):
        try:
            SCOPES = ['https://www.googleapis.com/auth/calendar']
            creds_dict = st.secrets["google_oauth_credentials"]
            creds = Credentials.from_authorized_user_info(creds_dict, scopes=SCOPES)
            service = build('calendar', 'v3', credentials=creds)
            
            target_cal_id = get_or_create_calendar(service, found_key)
            
            last_day = calendar.monthrange(y, m)[1]
            min_date = f"{y}-{m:02d}-01T00:00:00+09:00"
            max_date = f"{y}-{m:02d}-{last_day}T23:59:59+09:00"
            
            events_result = service.events().list(
                calendarId=target_cal_id, 
                timeMin=min_date, 
                timeMax=max_date,
                singleEvents=True
            ).execute()
            
            existing_items = events_result.get('items', [])
            st.session_state.existing_count = len(existing_items)
            st.session_state.show_conflict_options = True
        except Exception as e:
            st.error(f"事前確認エラー: {e}")

    if st.session_state.get('show_conflict_options', False):
        existing_count = st.session_state.get('existing_count', 0)
        
        st.warning(f"⚠️ Googleカレンダー側には現在 **{existing_count}件** 登録されています。（今回登録予定のデータ：**{target_total_count}件**）")
        
        conflict_action = st.radio(
            "処理方法の選択",
            [
                "1. パッチ処理（全データ削除して新たに登録し直す）",
                "2. 差分処理 / スマート更新（変更のない日はそのまま維持し、必要な分だけ追加・削除する）",
                "3. 重複処理（既存データを消さずに、そのまま新しく上乗せして登録する）"
            ],
            key="conflict_action_radio"
        )
        
        if st.button("実行する", key="execute_conflict_action_btn"):
            try:
                SCOPES = ['https://www.googleapis.com/auth/calendar']
                creds_dict = st.secrets["google_oauth_credentials"]
                creds = Credentials.from_authorized_user_info(creds_dict, scopes=SCOPES)
                service = build('calendar', 'v3', credentials=creds)
                target_cal_id = get_or_create_calendar(service, found_key)
                
                _, last_day = calendar.monthrange(y, m)
                min_date = f"{y}-{m:02d}-01T00:00:00+09:00"
                max_date = f"{y}-{m:02d}-{last_day}T23:59:59+09:00"
                deleted_count = 0
                added_count = 0
                skipped_count = 0

                time_schedule_df_check = st.session_state.data_dict.get(found_key, pd.DataFrame())
                time_shift_check_reg = time_schedule_df_check.fillna("").astype(str)
                df_cal_to_process = st.session_state.df_calendar

                progress_text = "Googleカレンダーと通信中です。しばらくお待ちください..."
                my_bar = st.progress(0, text=progress_text)
                start_time_exec = datetime.datetime.now()

                # --- 共通の通知設定を判別して生成する内部関数 ---
                def get_reminders_setting(subject_str):
                    is_first_work = "(出勤)" in subject_str
                    is_reopen_work = "▷" in subject_str

                    if is_first_work:
                        chosen_minutes = reminder_first_work
                    elif is_reopen_work:
                        chosen_minutes = reminder_reopen_work
                    else:
                        chosen_minutes = 0

                    if chosen_minutes > 0:
                        return {
                            'useDefault': False,
                            'overrides': [{'method': 'popup', 'minutes': chosen_minutes}],
                        }
                    else:
                        return {'useDefault': True}

                # --- モード1：パッチ処理 ---
                if "1. パッチ処理" in conflict_action:
                    existing_items = []
                    page_token = None
                    while True:
                        events_result = service.events().list(
                            calendarId=target_cal_id, 
                            timeMin=min_date, 
                            timeMax=max_date, 
                            singleEvents=True, 
                            pageToken=page_token,
                            maxResults=250
                        ).execute()
                        
                        for ev in events_result.get('items', []):
                            start_val = ev['start'].get('date') or ev['start'].get('dateTime', '')[:10]
                            if start_val.startswith(f"{y}-{m:02d}"):
                                existing_items.append(ev)
                                
                        page_token = events_result.get('nextPageToken')
                        if not page_token:
                            break

                    total_steps = len(existing_items) + len(df_cal_to_process)
                    current_step = 0

                    for event in existing_items:
                        service.events().delete(calendarId=target_cal_id, eventId=event['id']).execute()
                        deleted_count += 1
                        current_step += 1
                        if total_steps > 0:
                            my_bar.progress(min(current_step / total_steps, 1.0), text=f"既存データ削除中... ({deleted_count}/{len(existing_items)})")

                    for _, row in df_cal_to_process.iterrows():
                        is_all_day = (str(row['AllDayEvent']) == "True")
                        start_date = str(row['StartDate']).replace('/', '-')
                        end_date = str(row['EndDate']).replace('/', '-')
                        c_id = get_color_id(row['Subject'], time_shift_check_reg, found_key)
                        reminders_setting = get_reminders_setting(str(row['Subject']))
                        
                        if is_all_day:
                            event_body = {'summary': row['Subject'], 'location': row['Location'], 'start': {'date': start_date}, 'end': {'date': end_date}, 'colorId': c_id, 'reminders': reminders_setting}
                        else:
                            st_time = str(row['StartTime']).zfill(5) if ':' in str(row['StartTime']) else str(row['StartTime'])
                            ed_time = str(row['EndTime']).zfill(5) if ':' in str(row['EndTime']) else str(row['EndTime'])
                            event_body = {'summary': row['Subject'], 'location': row['Location'], 'start': {'dateTime': f"{start_date}T{st_time}:00", 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': f"{end_date}T{ed_time}:00", 'timeZone': 'Asia/Tokyo'}, 'colorId': c_id, 'reminders': reminders_setting}
                        
                        service.events().insert(calendarId=target_cal_id, body=event_body).execute()
                        added_count += 1
                        current_step += 1
                        if total_steps > 0:
                            my_bar.progress(min(current_step / total_steps, 1.0), text=f"新規登録中... ({added_count}/{len(df_cal_to_process)})")

                    my_bar.empty()
                    elapsed_sec = (datetime.datetime.now() - start_time_exec).seconds
                    st.success(f"【パッチ処理完了】(所要時間: 約 {elapsed_sec}秒)\nカレンダーを刷新しました（削除: {deleted_count}件 / 新規登録: {added_count}件）")

                # --- モード2：差分処理 ---
                elif "2. 差分処理" in conflict_action:
                    existing_events = []
                    page_token = None
                    while True:
                        events_result = service.events().list(
                            calendarId=target_cal_id, 
                            timeMin=min_date, 
                            timeMax=max_date, 
                            singleEvents=True, 
                            pageToken=page_token,
                            maxResults=250
                        ).execute()
                        
                        for ev in events_result.get('items', []):
                            start_val = ev['start'].get('date') or ev['start'].get('dateTime', '')[:10]
                            if start_val.startswith(f"{y}-{m:02d}"):
                                existing_events.append(ev)
                                
                        page_token = events_result.get('nextPageToken')
                        if not page_token:
                            break
                    
                    existing_dict = {}
                    for ev in existing_events:
                        start_val = ev['start'].get('date') or ev['start'].get('dateTime', '')[:10]
                        key_signature = (ev.get('summary', ''), start_val)
                        existing_dict[key_signature] = ev['id']

                    total_steps = len(df_cal_to_process)
                    current_step = 0

                    for _, row in df_cal_to_process.iterrows():
                        current_step += 1
                        my_bar.progress(min(current_step / total_steps, 1.0), text=f"差分チェック中... ({current_step}/{total_steps})")

                        is_all_day = (str(row['AllDayEvent']) == "True")
                        start_date = str(row['StartDate']).replace('/', '-')
                        end_date = str(row['EndDate']).replace('/', '-')
                        subject = row['Subject']
                        
                        signature = (subject, start_date)
                        if signature in existing_dict:
                            del existing_dict[signature]
                            skipped_count += 1
                            continue

                        c_id = get_color_id(subject, time_shift_check_reg, found_key)
                        reminders_setting = get_reminders_setting(str(subject))
                        
                        if is_all_day:
                            event_body = {'summary': subject, 'location': row['Location'], 'start': {'date': start_date}, 'end': {'date': end_date}, 'colorId': c_id, 'reminders': reminders_setting}
                        else:
                            st_time = str(row['StartTime']).zfill(5) if ':' in str(row['StartTime']) else str(row['StartTime'])
                            ed_time = str(row['EndTime']).zfill(5) if ':' in str(row['EndTime']) else str(row['EndTime'])
                            event_body = {'summary': subject, 'location': row['Location'], 'start': {'dateTime': f"{start_date}T{st_time}:00", 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': f"{end_date}T{ed_time}:00", 'timeZone': 'Asia/Tokyo'}, 'colorId': c_id, 'reminders': reminders_setting}
                        
                        service.events().insert(calendarId=target_cal_id, body=event_body).execute()
                        added_count += 1
                    
                    for signature, ev_id in existing_dict.items():
                        service.events().delete(calendarId=target_cal_id, eventId=ev_id).execute()
                        deleted_count += 1

                    my_bar.empty()
                    elapsed_sec = (datetime.datetime.now() - start_time_exec).seconds
                    st.success(f"【差分更新完了】(所要時間: 約 {elapsed_sec}秒)\n同期しました（新規追加: {added_count}件 / 変更なし維持: {skipped_count}件 / 不要分削除: {deleted_count}件）")

                # --- モード3：重複処理 ---
                else:
                    total_steps = len(df_cal_to_process)
                    current_step = 0

                    for _, row in df_cal_to_process.iterrows():
                        current_step += 1
                        my_bar.progress(min(current_step / total_steps, 1.0), text=f"重複登録中... ({current_step}/{total_steps})")

                        is_all_day = (str(row['AllDayEvent']) == "True")
                        start_date = str(row['StartDate']).replace('/', '-')
                        end_date = str(row['EndDate']).replace('/', '-')
                        c_id = get_color_id(row['Subject'], time_shift_check_reg, found_key)
                        reminders_setting = get_reminders_setting(str(row['Subject']))
                        
                        if is_all_day:
                            event_body = {'summary': row['Subject'], 'location': row['Location'], 'start': {'date': start_date}, 'end': {'date': end_date}, 'colorId': c_id, 'reminders': reminders_setting}
                        else:
                            st_time = str(row['StartTime']).zfill(5) if ':' in str(row['StartTime']) else str(row['StartTime'])
                            ed_time = str(row['EndTime']).zfill(5) if ':' in str(row['EndTime']) else str(row['EndTime'])
                            event_body = {'summary': row['Subject'], 'location': row['Location'], 'start': {'dateTime': f"{start_date}T{st_time}:00", 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': f"{end_date}T{ed_time}:00", 'timeZone': 'Asia/Tokyo'}, 'colorId': c_id, 'reminders': reminders_setting}
                        
                        service.events().insert(calendarId=target_cal_id, body=event_body).execute()
                        added_count += 1

                    my_bar.empty()
                    elapsed_sec = (datetime.datetime.now() - start_time_exec).seconds
                    st.success(f"【重複登録完了】(所要時間: 約 {elapsed_sec}秒)\n既存データを残したまま、新規に {added_count}件 のデータを追加しました。")
                    
        # 🚀 【共通】カレンダー登録完了後・終了前の西村文宏さん向けドライブ処理
        # ==========================================================
        normalized_target = target_name.replace(" ", "").replace(" ", "")
        
        if normalized_target == "西村文宏":
            st.write("1")
            try:
                SCOPES_DRIVE = [
                    'https://www.googleapis.com/auth/drive',
                    'https://www.googleapis.com/auth/calendar',
                    'https://www.googleapis.com/auth/gmail.readonly',
                    'https://www.googleapis.com/auth/spreadsheets.readonly'
                ]
                creds_dict_drive = st.secrets["google_oauth_credentials"]
                creds_d = Credentials.from_authorized_user_info(creds_dict_drive, scopes=SCOPES_DRIVE)
                drive_service = build('drive', 'v3', credentials=creds_d)
                
                st.write("2")
                def get_or_create_folder(service, folder_name, parent_id=None):
                    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                    if parent_id:
                        query += f" and '{parent_id}' in parents"
                    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
                    files = results.get('files', [])
                    if files:
                        return files[0]['id']
                    else:
                        file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
                        if parent_id:
                            file_metadata['parents'] = [parent_id]
                        folder = service.files().create(body=file_metadata, fields='id').execute()
                        return folder.get('id')
               
                st.write("3")
                calendar_folder_id = get_or_create_folder(drive_service, "カレンダー")
                shift_folder_id = get_or_create_folder(drive_service, "シフト", calendar_folder_id)

                file_name = f"{y}年{m}月_{found_key}.pdf"

                existing_q = f"name='{file_name}' and '{shift_folder_id}' in parents and trashed=false"
                existing_files = drive_service.files().list(q=existing_q, fields='files(id)').execute().get('files', [])
                for ef in existing_files:
                    drive_service.files().delete(fileId=ef['id']).execute()

                media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='application/pdf', resumable=True)
                file_metadata = {'name': file_name, 'parents': [shift_folder_id]}
                drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

                target_month_val = m - 2
                target_year_val = y
                if target_month_val <= 0:
                    target_month_val += 12
                    target_year_val -= 1
                limit_date = datetime.datetime(target_year_val, target_month_val, 1)

                shift_files = drive_service.files().list(q=f"'{shift_folder_id}' in parents and trashed=false", fields='files(id, name)').execute().get('files', [])
                
                for sf in shift_files:
                    sf_name = sf['name']
                    if found_key in sf_name:
                        match = re.search(r'(\d{4})年(\d{1,2})月', sf_name)
                        if match:
                            f_y, f_m = int(match.group(1)), int(match.group(2))
                            f_date = datetime.datetime(f_y, f_m, 1)
                            if f_date <= limit_date:
                                drive_service.files().delete(fileId=sf['id']).execute()

                st.success("📁 Googleドライブ「カレンダー > シフト」フォルダへのPDF保存および古いファイルの整理が完了しました。")
                
            except Exception as e:
                st.error(f"ドライブ自動保存・削除エラー: {e}")
