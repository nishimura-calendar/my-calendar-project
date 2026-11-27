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

# --- ファイル名の年月抽出と暦・PDF内容の整合性判定 ---
def extract_year_month_from_filename(filename, fallback_year=2026):
    name_norm = unicodedata.normalize("NFKC", filename or "")
    y_match = re.search(r"(\d{4})\s*年", name_norm) or re.search(r"(\d{4})", name_norm)
    m_match = re.search(r"(\d{1,2})\s*月", name_norm)
    year = int(y_match.group(1)) if y_match else fallback_year
    month = int(m_match.group(1)) if m_match else None
    return year, month

def evaluate_month_end_consistency(df, year, month, pdf_full_text=""):
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    weekdays_set = set(weekdays_jp)

    _, cal_last_day = calendar.monthrange(year, month)
    cal_last_weekday = weekdays_jp[calendar.weekday(year, month, cal_last_day)]

    found_weekdays = []
    max_rows = min(df.shape[0], 3) if df is not None and not df.empty else 0

    for r in range(max_rows):
        for c in range(df.shape[1]):
            raw = df.iloc[r, c]
            if raw is None:
                continue
            s = unicodedata.normalize("NFKC", str(raw)).strip()
            if not s or s.lower() in ("nan", "none"):
                continue
            for ch in s:
                if ch in weekdays_set:
                    found_weekdays.append(ch)

    pdf_day_count = len(found_weekdays) if len(found_weekdays) > 0 else None
    pdf_last_weekday = found_weekdays[-1] if len(found_weekdays) > 0 else None

    pdf_ym_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", pdf_full_text or "")
    pdf_ym_label = (
        f"{int(pdf_ym_match.group(1))}年{int(pdf_ym_match.group(2))}月"
        if pdf_ym_match
        else "不明"
    )

    is_consistent = (
        pdf_day_count == cal_last_day
        and pdf_last_weekday == cal_last_weekday
    )

    reason_parts = [
        f"ファイル名からは {year}年{month}月（暦の末日：{cal_last_day}日・{cal_last_weekday}曜日）と判定されましたが、"
        f"PDF抽出結果は {pdf_day_count if pdf_day_count is not None else '不明'}日・"
        f"{pdf_last_weekday if pdf_last_weekday is not None else '不明'}曜日でした。"
    ]
    if pdf_ym_match and (int(pdf_ym_match.group(1)) != year or int(pdf_ym_match.group(2)) != month):
        reason_parts.append(f"（PDF本文内の年月表記：{pdf_ym_label}）")

    reason = "".join(reason_parts) + "ファイルを確認して下さい。"

    return {
        "is_consistent": is_consistent,
        "year": year,
        "month": month,
        "cal_last_day": cal_last_day,
        "cal_last_weekday": cal_last_weekday,
        "pdf_day_count": pdf_day_count,
        "pdf_last_weekday": pdf_last_weekday,
        "reason": reason,
    }

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

# --- 通知オプション生成用ヘルパー関数（何時間何分前の形式） ---
def get_start_reminder_options():
    mins_list = list(range(0, 61, 5)) + list(range(90, 241, 30))
    options = {"通知なし": None}
    for m in mins_list:
        if m == 0:
            options["時間丁度 (0分前)"] = 0
        elif m < 60:
            options[f"{m}分前"] = m
        elif m == 60:
            options["1時間前"] = 60
        else:
            hours = m // 60
            rem = m % 60
            if rem == 0:
                options[f"{hours}時間前"] = m
            else:
                options[f"{hours}時間{rem}分前"] = m
    return options

def get_resume_reminder_options():
    mins_list = list(range(0, 61, 5))
    options = {"通知なし": None}
    for m in mins_list:
        if m == 0:
            options["時間丁度 (0分前)"] = 0
        elif m < 60:
            options[f"{m}分前"] = m
        elif m == 60:
            options["1時間前"] = 60
    return options

def make_reminder_body(mins):
    if mins is None:
        return {
            'useDefault': False,
            'overrides': []
        }
    else:
        return {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': mins},
            ]
        }

# --- アップロードウィジェット用のキー初期化 ---
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- リセット関数 ---
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
                    st.session_state
