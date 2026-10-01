import streamlit as st
import pandas as pd
import io
import pdfplumber
import re
import calendar
import unicodedata
import fitz  # PyMuPDF
import datetime
import time
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
    thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    query = f"mimeType='application/pdf' and createdTime >= '{thirty_days_ago}' and trashed = false"
    
    results = service.files().list(
        q=query,
        orderBy="createdTime desc",
        pageSize=20,
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

# --- GoogleドライブのPDF保存と前々月以前のファイル削除処理 ---
def process_drive_pdf_management(drive_service, file_bytes, y, m, found_key):
    folder_id = "1X9ThkHI4xPeUYa29FW3AmLll9gRz6EFd"
    file_name = f"{y}年{m}月_{found_key}.pdf"
    
    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    existing_files = drive_service.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    for ef in existing_files:
        drive_service.files().delete(fileId=ef['id']).execute()
        
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='application/pdf', resumable=True)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    q_all = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed = false"
    all_files = drive_service.files().list(q=q_all, fields="files(id, name)").execute().get('files', [])
    
    current_total_months = y * 12 + m
    
    for f in all_files:
        fname = f['name']
        match = re.search(r'(\d{4})年\s*(\d{1,2})月', fname)
        if match:
            fy = int(match.group(1))
            fm = int(match.group(2))
            file_total_months = fy * 12 + fm
            if current_total_months - file_total_months >= 2:
                try:
                    drive_service.files().delete(fileId=f['id']).execute()
                except Exception:
                    pass

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

def get_base_value(val):
    if not val or pd.isna(val):
        return ""
    return str(val).split('_')[0].strip()

def get_or_create_calendar(service, calendar_name):
    calendar_list = service.calendarList().list().execute()
    for cal in calendar_list.get('items', []):
        if cal.get('summary') == calendar_name:
            return cal.get('id')
    
    new_cal = {'summary': calendar_name}
    created_cal = service.calendars().insert(body=new_cal).execute()
    return created_cal.get('id')

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

# --- アップロードウィジェット用のキー初期化 ---
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 確実な初期化を行うリセット関数 ---
def reset_to_initial_state():
    current_uploader_key = st.session_state.get('uploader_key', 0) + 1
    for key in list(st.session_state.keys()):
        if key != 'data_dict':
            del st.session_state[key]
    st.session_state.uploader_key = current_uploader_key
 
# --- [2] メイン処理 ---
st.title("シフト表解析システム")

if 'data_dict' not in st.session_state:
    st.session_state.data_dict = load_and_process_data()

st.sidebar.title("システムメニュー")
if st.sidebar.button("🔄 最初からやり直す（リセット）"):
    reset_to_initial_state()
    st.rerun()

st.sidebar.divider()

if 'loaded_pdf_bytes' not in st.session_state:
    st.session_state.loaded_pdf_bytes = None
    st.session_state.loaded_pdf_name = None

if st.session_state.loaded_pdf_bytes is None:
    upload_option = st.radio("PDFの取得方法を選択してください", ["手動アップロード", "Google Driveから選択"], index=0)

    uploaded_file_obj = None

    if upload_option == "手動アップロード":
        uploaded_file_obj = st.file_uploader("PDFシフト表をアップロード", type="pdf", key=f"uploader_{st.session_state.uploader_key}")
        if uploaded_file_obj is not None:
            st.session_state.loaded_pdf_bytes = uploaded_file_obj.getvalue()
            st.session_state.loaded_pdf_name = uploaded_file_obj.name
            st.rerun()
    else:
        try:
            creds_dict = st.secrets["google_oauth_credentials"]
            creds_drive = Credentials.from_authorized_user_info(creds_dict)
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
                    st.session_state.selected_file_id = selected_file['id']
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
    for key in ['use_pdf_choice', 'df_calendar', 'show_conflict_options', 'filename_fallback_confirmed']:
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

# ファイル名に "T2" や "第2ターミナル" が含まれる場合の対応
if "T2" in uploaded_pdf.name or "第2ターミナル" in uploaded_pdf.name:
    if not found_key or found_key not in st.session_state.data_dict:
        found_key = "T2"

uploaded_pdf.seek(0)
with pdfplumber.open(uploaded_pdf) as pdf:
    tables = pdf.pages[0].extract_tables()
    df_pdf = pd.DataFrame(tables[0]) if tables else pd.DataFrame()

if not found_key:
    st.error("勤務地(Key)がPDFから特定できませんでした。")
    display_pdf_as_images(file_bytes)
    st.stop()

# --- 日付・曜日の抽出処理 ---
A_date, A_day = None, None
if not df_pdf.empty:
    for row in range(df_pdf.shape[0] - 1):
        for col in range(df_pdf.shape[1]):
            val_up = str(df_pdf.iloc[row, col])
            val_down = str(df_pdf.iloc[row+1, col])
            if re.match(r'^(0?[1-9]|[12][0-9]|3[01])$', val_up) and val_down in "月火水木金土日":
                A_date, A_day = int(val_up), val_down

filename = uploaded_pdf.name
year_match = re.search(r'(\d{4})', filename)
month_match = re.search(r'(\d{1,2})月', filename)

y, m = None, None
if year_match and month_match:
    y = int(year_match.group(1))
    m = int(month_match.group(1))

# --- 例外処理：ファイル内容から日付・曜日が抽出できない場合 ---
if not A_date or not y or not m:
    if year_match and month_match:
        y = int(year_match.group(1))
        m = int(month_match.group(1))
        
        st.warning("⚠️ ファイル内容から日付・曜日の自動抽出ができませんでしたが、ファイル名から年月を検知しました。")
        display_pdf_as_images(file_bytes)
        
        st.markdown(f"### 〈{y}年{m}月_{found_key}のデータとして読み込みますか？〉")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("はい：そのまま実行"):
                st.session_state.filename_fallback_confirmed = True
                st.rerun()
        with col_no:
            if st.button("いいえ：初期設定を表示する"):
                reset_to_initial_state()
                st.rerun()
                
        if not st.session_state.get('filename_fallback_confirmed', False):
            st.stop()
    else:
        st.error("ファイル内容からもファイル名からも年月・日付が特定できませんでした。")
        display_pdf_as_images(file_bytes)
        st.stop()

_, last_day_num = calendar.monthrange(y, m)
last_day_w = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, last_day_num)]

# 通常の抽出が成功した場合の整合性チェック（例外確認済みならスキップ）
if not st.session_state.get('filename_fallback_confirmed', False):
    if A_date == last_day_num and A_day == last_day_w:
        pass 
    else:
        st.error("整合性不一致: アップロードされたシフト表の年月が期待値と異なります。")
        st.write(f"抽出された最終日: {A_date}日 ({A_day}曜日)")
        st.write(f"カレンダー上の最終日: {last_day_num}日 ({last_day_w}曜日)")
        display_pdf_as_images(file_bytes)
        st.stop()

try:
    creds_dict = st.secrets["google_oauth_credentials"]
    creds_drive = Credentials.from_authorized_user_info(creds_dict)
    drive_mgmt_service = build('drive', 'v3', credentials=creds_drive)
    process_drive_pdf_management(drive_mgmt_service, file_bytes, y, m, found_key)
except Exception as e:
    st.sidebar.warning(f"Googleドライブのファイル整理スキップ: {e}")

st.divider()

# --- スタッフデータの抽出処理（通常＋連続行・詰まったデータ対応の例外処理） ---
staff_data = []

# 1. まず従来の1行飛ばしパターンをチェック
for idx in range(0, df_pdf.shape[0], 2):
    if idx >= df_pdf.shape[0]:
        break
    name_val = str(df_pdf.iloc[idx, 0])
    if name_val in st.session_state.data_dict.keys():
        continue
    
    if name_val != 'None':
        clean_name = name_val.split('\n')[0].strip()
    else:
        clean_name = "該当なし"
    if clean_name and clean_name != 'nan':
        staff_data.append((idx, clean_name))

# 2. あくまで例外処理：スタッフデータが取れない場合や、連続して入力されているレイアウトのフォールバック
if not staff_data or len(staff_data) < 1:
    staff_data = []
    for idx in range(1, df_pdf.shape[0]):
        name_val = str(df_pdf.iloc[idx, 0])
        if not name_val or name_val == 'nan' or name_val == 'None' or name_val in st.session_state.data_dict.keys():
            continue
        
        clean_name = name_val.split('\n')[0].strip()
        # 日付や曜日などの単一文字/数字を除外
        if clean_name and not re.match(r'^(0?[1-9]|[12][0-9]|3[01]|[月火水木金土日])$', clean_name):
            if clean_name not in [s[1] for s in staff_data]:
                staff_data.append((idx, clean_name))

if staff_data:
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
else:
    st.error("スタッフデータが検出できませんでした。")
    st.stop()

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
                final_rows.append([subject, target_date, "", target_date, "", "False", "", found_key, "OTHER"])
                start_time = time_shift.iloc[0, t_col]
            
                event_type = "OTHER"
                if (row_data[3:t_col] == "").all():
                    start = "(出勤)："
                    event_type = "START"  
                    
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
                    if not (row_data[3:t_col] == "").all():
                        event_type = "RESUME"  
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
                final_rows[-1][8] = event_type
               
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
            final_rows.append([f"{found_key}_{base_schedule_val}", target_date, "", end_date_str, "", "True", "", found_key, "ALL_DAY"])
            shift_cal(found_key, target_date, col, schedule_val, my_df, other_df, time_schedule_df, final_rows)
        else:
            start_dt_obj = datetime.datetime.strptime(target_date, "%Y/%m/%d")
            end_dt_obj = start_dt_obj + datetime.timedelta(days=1)
            end_date_str = end_dt_obj.strftime("%Y/%m/%d")
            
            final_rows.append([schedule_val, target_date, "", end_date_str, "", "True", "", schedule_val, "ALL_DAY"])
            
            time_match = re.search(r'(\d+)[^\d]+(\d+)', sub_val)
            if time_match:
                final_rows.append([schedule_val, target_date, f"{time_match.group(1)}:00", target_date, f"{time_match.group(2)}:00", "False", "", found_key, "START"])
                
    if final_rows:
        display_rows = [row[:8] for row in final_rows]
        st.session_state.df_calendar = pd.DataFrame(display_rows, columns=["Subject", "StartDate", "StartTime", "EndDate", "EndTime", "AllDayEvent", "Description", "Location"])
        st.session_state.raw_final_rows = final_rows
        st.success(f"カレンダー登録データの生成が完了しました（計 {len(st.session_state.df_calendar)} 件）")
    else:
        st.warning("生成対象のデータがありませんでした。")

if 'df_calendar' in st.session_state:
    st.dataframe(st.session_state.df_calendar)
    
    csv_cal = st.session_state.df_calendar.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
    st.download_button("カレンダー登録用CSVをダウンロード", csv_cal, "calendar_import.csv", "text/csv")

    st.subheader(f"Googleカレンダー連携 (対象勤務地: {found_key})")
    st.info(f"※マイカレンダーに「{found_key}」という名前のカレンダーがない場合は自動的に新規作成されます。")

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
        
        with st.form(key="calendar_execution_form"):
            st.markdown("### ⏰ アラーム（通知）設定")
            col_notif1, col_notif2, col_notif3 = st.columns(3)
            
            with col_notif1:
                reminder_option_a = st.selectbox(
                    "出勤時（通知_A）",
                    ["通知なし", "0分前（同時）", "5分前", "10分前", "15分前", "20分前", "25分前", "30分前", "35分前", "1時間前", "2時間前", "3時間前"],
                    index=3
                )
            with col_notif2:
                reminder_option_b = st.selectbox(
                    "休憩明け時（通知_B）",
                    ["通知なし", "0分前（同時）", "5分前", "10分前", "15分前", "20分前", "25分前", "30分前", "35分前", "40分前", "45分前", "50分前", "55分前", "1時間前"],
                    index=2
                )
            with col_notif3:
                reminder_option_other = st.selectbox(
                    "その他の予定（終日等）",
                    ["通知なし", "0分前（同時）", "10分前", "15分前", "30分前", "60分前"],
                    index=0
                )

            st.divider()

            conflict_action = st.radio(
                "処理方法の選択",
                [
                    "1. パッチ処理（全データ削除して新たに登録し直す）",
                    "2. 差分処理 / スマート更新（変更のない日はそのまま維持し、必要な分だけ追加・削除する）",
                    "3. 重複処理（既存データを消さずに、そのまま新しく上乗せして登録する）"
                ],
                key="conflict_action_radio"
            )
            
            submitted = st.form_submit_button("実行する")
        
        if submitted:
            try:
                def label_to_minutes(label):
                    if label == "通知なし": return None
                    if label == "0分前（同時）": return 0
                    if "分前" in label: return int(label.replace("分前", ""))
                    if "1時間前" in label: return 60
                    if "2時間前" in label: return 120
                    if "3時間前" in label: return 180
                    return None

                selected_minutes_a = label_to_minutes(reminder_option_a)
                selected_minutes_b = label_to_minutes(reminder_option_b)
                selected_minutes_other = label_to_minutes(reminder_option_other)

                SCOPES = ['https://www.googleapis.com/auth/calendar']
                creds_dict = st.secrets["google_oauth_credentials"]
                creds = Credentials.from_authorized_user_info(creds_dict, scopes=SCOPES)
                service = build('calendar', 'v3', credentials=creds)
                target_cal_id = get_or_create_calendar(service, found_key)
                
                _, last_day = calendar.monthrange(y, m)
                min_date = f"{y}-{m:02d}-01T00:00:00+09:00"
                max_date = f"{y}-{m:02d}-{last_day}T23:59:59+09:00"
                deleted_count, added_count, skipped_count = 0, 0, 0

                time_schedule_df_check = st.session_state.data_dict.get(found_key, pd.DataFrame())
                time_shift_check_reg = time_schedule_df_check.fillna("").astype(str)
                raw_rows_to_process = st.session_state.get('raw_final_rows', [])

                progress_text = "Googleカレンダーと通信中です。しばらくお待ちください..."
                my_bar = st.progress(0, text=progress_text)
                start_time_exec = datetime.datetime.now()

                def make_reminder_body(mins):
                    if mins is None: return {'useDefault': True}
                    else: return {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': mins}]}

                reminder_setting_a = make_reminder_body(selected_minutes_a)
                reminder_setting_b = make_reminder_body(selected_minutes_b)
                reminder_setting_other = make_reminder_body(selected_minutes_other)

                def get_reminder_by_type(ev_type):
                    if ev_type == "START": return reminder_setting_a
                    elif ev_type == "RESUME": return reminder_setting_b
                    else: return reminder_setting_other

                # --- モード1：パッチ処理 ---
                if "1. パッチ処理" in conflict_action:
                    existing_items = []
                    page_token = None
                    while True:
                        events_result = service.events().list(
                            calendarId=target_cal_id, timeMin=min_date, timeMax=max_date, 
                            singleEvents=True, pageToken=page_token, maxResults=250
                        ).execute()
                        for ev in events_result.get('items', []):
                            start_val = ev['start'].get('date') or ev['start'].get('dateTime', '')[:10]
                            if start_val.startswith(f"{y}-{m:02d}"):
                                existing_items.append(ev)
                        page_token = events_result.get('nextPageToken')
                        if not page_token: break

                    total_steps = len(existing_items) + len(raw_rows_to_process)
                    current_step = 0

                    for event in existing_items:
                        service.events().delete(calendarId=target_cal_id, eventId=event['id']).execute()
                        deleted_count += 1
                        current_step += 1
                        my_bar.progress(min(current_step / total_steps, 1.0), text=f"既存データ削除中... ({deleted_count}/{len(existing_items)})")

                    for row in raw_rows_to_process:
                        subject, start_date_str, start_time_str, end_date_str, end_time_str, all_day_str, desc, loc, ev_type = row
                        is_all_day = (str(all_day_str) == "True")
                        start_date, end_date = str(start_date_str).replace('/', '-'), str(end_date_str).replace('/', '-')
                        c_id = get_color_id(subject, time_shift_check_reg, found_key)
                        current_reminder = get_reminder_by_type(ev_type)
                        
                        if is_all_day:
                            event_body = {'summary': subject, 'location': loc, 'start': {'date': start_date}, 'end': {'date': end_date}, 'colorId': c_id, 'reminders': current_reminder}
                        else:
                            st_time, ed_time = str(start_time_str).zfill(5), str(end_time_str).zfill(5)
                            event_body = {'summary': subject, 'location': loc, 'start': {'dateTime': f"{start_date}T{st_time}:00", 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': f"{end_date}T{ed_time}:00", 'timeZone': 'Asia/Tokyo'}, 'colorId': c_id, 'reminders': current_reminder}
                        
                        service.events().insert(calendarId=target_cal_id, body=event_body).execute()
                        added_count += 1
                        current_step += 1
                        my_bar.progress(min(current_step / total_steps, 1.0), text=f"新規登録中... ({added_count}/{len(raw_rows_to_process)})")

                    my_bar.empty()
                    elapsed_sec = (datetime.datetime.now() - start_time_exec).seconds
                    st.success(f"【パッチ処理完了】(所要時間: 約 {elapsed_sec}秒)\nカレンダーを刷新しました（削除: {deleted_count}件 / 新規登録: {added_count}件）")

                # --- モード2：差分処理 ---
                elif "2. 差分処理" in conflict_action:
                    existing_events = []
                    page_token = None
                    while True:
                        events_result = service.events().list(
                            calendarId=target_cal_id, timeMin=min_date, timeMax=max_date, 
                            singleEvents=True, pageToken=page_token, maxResults=250
                        ).execute()
                        for ev in events_result.get('items', []):
                            start_val = ev['start'].get('date') or ev['start'].get('dateTime', '')[:10]
                            if start_val.startswith(f"{y}-{m:02d}"):
                                existing_events.append(ev)
                        page_token = events_result.get('nextPageToken')
                        if not page_token: break
                    
                    existing_dict = {}
                    for ev in existing_events:
                        start_val = ev['start'].get('date') or ev['start'].get('dateTime', '')[:10]
                        existing_dict[(ev.get('summary', ''), start_val)] = ev['id']

                    total_steps = len(raw_rows_to_process)
                    current_step = 0

                    for row in raw_rows_to_process:
                        current_step += 1
                        my_bar.progress(min(current_step / total_steps, 1.0), text=f"差分チェック中... ({current_step}/{total_steps})")

                        subject, start_date_str, start_time_str, end_date_str, end_time_str, all_day_str, desc, loc, ev_type = row
                        is_all_day = (str(all_day_str) == "True")
                        start_date, end_date = str(start_date_str).replace('/', '-'), str(end_date_str).replace('/', '-')
                        
                        signature = (subject, start_date)
                        if signature in existing_dict:
                            del existing_dict[signature]
                            skipped_count += 1
                            continue

                        c_id = get_color_id(subject, time_shift_check_reg, found_key)
                        current_reminder = get_reminder_by_type(ev_type)
                        
                        if is_all_day:
                            event_body = {'summary': subject, 'location': loc, 'start': {'date': start_date}, 'end': {'date': end_date}, 'colorId': c_id, 'reminders': current_reminder}
                        else:
                            st_time, ed_time = str(start_time_str).zfill(5), str(end_time_str).zfill(5)
                            event_body = {'summary': subject, 'location': loc, 'start': {'dateTime': f"{start_date}T{st_time}:00", 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': f"{end_date}T{ed_time}:00", 'timeZone': 'Asia/Tokyo'}, 'colorId': c_id, 'reminders': current_reminder}
                        
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
                    total_steps = len(raw_rows_to_process)
                    current_step = 0

                    for row in raw_rows_to_process:
                        current_step += 1
                        my_bar.progress(min(current_step / total_steps, 1.0), text=f"重複登録中... ({current_step}/{total_steps})")

                        subject, start_date_str, start_time_str, end_date_str, end_time_str, all_day_str, desc, loc, ev_type = row
                        is_all_day = (str(all_day_str) == "True")
                        start_date, end_date = str(start_date_str).replace('/', '-'), str(end_date_str).replace('/', '-')
                        c_id = get_color_id(subject, time_shift_check_reg, found_key)
                        current_reminder = get_reminder_by_type(ev_type)
                        
                        if is_all_day:
                            event_body = {'summary': subject, 'location': loc, 'start': {'date': start_date}, 'end': {'date': end_date}, 'colorId': c_id, 'reminders': current_reminder}
                        else:
                            st_time, ed_time = str(start_time_str).zfill(5), str(end_time_str).zfill(5)
                            event_body = {'summary': subject, 'location': loc, 'start': {'dateTime': f"{start_date}T{st_time}:00", 'timeZone': 'Asia/Tokyo'}, 'end': {'dateTime': f"{end_date}T{ed_time}:00", 'timeZone': 'Asia/Tokyo'}, 'colorId': c_id, 'reminders': current_reminder}
                        
                        service.events().insert(calendarId=target_cal_id, body=event_body).execute()
                        added_count += 1

                    my_bar.empty()
                    elapsed_sec = (datetime.datetime.now() - start_time_exec).seconds
                    st.success(f"【重複登録完了】(所要時間: 約 {elapsed_sec}秒)\n既存データを残したまま、新規に {added_count}件 のデータを追加しました。")

                st.success("🎉 カレンダー登録が終了しました。")
                
                if 'selected_file_id' in st.session_state and st.session_state.selected_file_id:
                    try:
                        creds_dict_d = st.secrets["google_oauth_credentials"]
                        creds_d = Credentials.from_authorized_user_info(creds_dict_d)
                        drive_del_service = build('drive', 'v3', credentials=creds_d)
                        drive_del_service.files().delete(fileId=st.session_state.selected_file_id).execute()
                        st.success("🗑 Googleドライブ上の元のPDFファイルを削除しました。")
                    except Exception as e:
                        st.warning(f"元ファイルの削除に失敗しました: {e}")

                st.balloons()
                time.sleep(10)
                
                reset_to_initial_state()
                st.rerun()
                
            except Exception as e:
                st.error(f"登録実行エラー: {e}")
