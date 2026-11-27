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


# --- Google認証ヘルパー関数 ---
def get_google_creds(scopes=None):
    creds_dict = dict(st.secrets["google_oauth_credentials"])
    if scopes:
        creds = Credentials.from_authorized_user_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_authorized_user_info(creds_dict)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


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
    creds = get_google_creds(scopes=['https://www.googleapis.com/auth/drive'])
    service = build('drive', 'v3', credentials=creds)
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    while not downloader.next_chunk()[1]:
        pass
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
            creds_drive = get_google_creds(scopes=['https://www.googleapis.com/auth/drive'])
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
    for key in ['use_pdf_choice', 'df_calendar', 'show_conflict_options']:
        if key in st.session_state:
            del st.session_state[key]

uploaded_pdf.seek(0)
with pdfplumber.open(uploaded_pdf) as pdf:
    pdf_full_text = unicodedata.normalize('NFKC', pdf.pages[0].extract_text() or "")
    
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

# 最大の日付（月末側）と直下の曜日を優先して抽出
A_date, A_day = None, None
for row in range(df_pdf.shape[0] - 1):
    for col in range(df_pdf.shape[1]):
        val_up = unicodedata.normalize('NFKC', str(df_pdf.iloc[row, col])).strip()
        val_down = unicodedata.normalize('NFKC', str(df_pdf.iloc[row + 1, col])).strip()
        if re.fullmatch(r'^(0?[1-9]|[12][0-9]|3[01])$', val_up) and val_down in "月火水木金土日":
            cand_date = int(val_up)
            if A_date is None or cand_date >= A_date:
                A_date, A_day = cand_date, val_down

if not A_date:
    st.error("日付と曜日が抽出できませんでした。")
    display_pdf_as_images(file_bytes)
    st.stop()

# 1. ファイル名とPDF本文それぞれから年月を抽出
filename = unicodedata.normalize('NFKC', uploaded_pdf.name or "")
fn_y_match = re.search(r'(20\d{2})', filename)
fn_m_match = re.search(r'(\d{1,2})\s*月', filename)

txt_y_match = re.search(r'(20\d{2})\s*年', pdf_full_text)
txt_m_match = re.search(r'(\d{1,2})\s*月', pdf_full_text)

fn_y = int(fn_y_match.group(1)) if fn_y_match else None
fn_m = int(fn_m_match.group(1)) if fn_m_match else None
txt_y = int(txt_y_match.group(1)) if txt_y_match else None
txt_m = int(txt_m_match.group(1)) if txt_m_match else None

# 使用する年月の決定（本文の年月を優先し、なければファイル名を使用）
y = txt_y if txt_y is not None else fn_y
m = txt_m if txt_m is not None else fn_m

# 2. 一致・不一致の判定
mismatch_reasons = []

if fn_y is None or fn_m is None:
    mismatch_reasons.append("ファイル名から年月が取得できませんでした。")
elif (txt_y is not None and fn_y != txt_y) or (txt_m is not None and fn_m != txt_m):
    mismatch_reasons.append(f"ファイル名の年月（{fn_y}年{fn_m}月）とPDF本文の年月（{txt_y}年{txt_m}月）が一致しません。")

if y is not None and m is not None:
    _, last_day_num = calendar.monthrange(y, m)
    last_day_w = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, last_day_num)]
    if not (A_date == last_day_num and A_day == last_day_w):
        mismatch_reasons.append(
            f"抽出された最終日（{A_date}日 {A_day}曜）と、{y}年{m}月のカレンダー末日（{last_day_num}日 {last_day_w}曜）が一致しません。"
        )
else:
    mismatch_reasons.append("年または月を特定できませんでした。")

# 3. 不一致がある場合は必ずファイルを表示して確認する
if mismatch_reasons:
    st.warning("⚠️ ファイル名とファイルの内容に一致しない点があります。")
    for reason in mismatch_reasons:
        st.write(f"・{reason}")
    
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
        reset_to_initial_state()
        st.rerun()
    else:
        if y is None:
            y = 2026
        if m is None:
            m = 12

try:
    creds_drive = get_google_creds(scopes=['https://www.googleapis.com/auth/drive'])
    drive_mgmt_service = build('drive', 'v3', credentials=creds_drive)
    process_drive_pdf_management(drive_mgmt_service, file_bytes, y, m, found_key)
except Exception as e:
    st.sidebar.warning(f"Googleドライブのファイル整理スキップ: {e}")

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

time_schedule_df_init = st.session_state.data_dict[found_key]
time_shift_check_init = time_schedule_df_init.fillna("").astype(str)
time_shift_bases_set = set(time_shift_check_init.iloc[:, 1].apply(get_base_value)) if not time_shift_check_init.empty else set()

staff_names_list = [s[1] for s in staff_data]

start_options
