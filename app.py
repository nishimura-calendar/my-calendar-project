import streamlit as st
import pandas as pd
import io
import pdfplumber
import re
import calendar
import unicodedata
import fitz  # PyMuPDF
import datetime
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
    query = f"mimeType='application/pdf' and createdTime >= '{thirty_days_ago}' and trashed = false"
    
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
    while done is not False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# --- ★新規追加: アップロードされたPDFをDriveに保存し、前々月データを削除する関数 ---
def save_pdf_to_drive_and_cleanup(service, file_bytes, file_name):
    try:
        # 1. 保存先のフォルダID（必要に応じて特定のフォルダIDに変更してください。ルートの場合はNoneまたは省略）
        # ここではマイドライブ直下に保存する例としてフォルダ指定なしで実装します
        
        # 2. アップロードするファイルの年月を抽出（例: "8月度 2026" や "2026年8月" などから取得）
        year_match = re.search(r'(\d{4})', file_name)
        month_match = re.search(r'(\d{1,2})月', file_name)
        
        target_y, target_m = None, None
        if year_match and month_match:
            target_y = int(year_match.group(1))
            target_m = int(month_match.group(1))
            
            # 前々月の計算
            # 例: 2026年8月の前々月 = 2026年6月
            target_date_obj = datetime.date(target_y, target_m, 1) - datetime.timedelta(days=1) # 前月月末
            prev_prev_date_obj = datetime.date(target_date_obj.year, target_date_obj.month, 1) - datetime.timedelta(days=1) # 前々月月末
            pp_y, pp_m = prev_prev_date_obj.year, prev_prev_date_obj.month
            
            # Google Drive内から前々月のPDFを検索して削除
            query = f"mimeType='application/pdf' and trashed = false"
            results = service.files().list(q=query, fields="files(id, name)").execute()
            
            for f in results.get('files', []):
                fname = f['name']
                if f['id'] == 'some_protected_id': # 必要なら除外IDを設定
                    continue
                # ファイル名に前々月の年と月が含まれているか判定
                if str(pp_y) in fname and (f"{pp_m}月" in fname or f"{pp_m:02d}月" in fname or f"/{pp_m:02d}/" in fname):
                    service.files().delete(fileId=f['id']).execute()
                    st.toast(f"🗑️ 古いデータ（前々月: {fname}）を自動削除しました。")

        # 3. 新規ファイルのアップロード
        media_body = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='application/pdf', resumable=True)
        body = {'name': file_name}
        service.files().create(body=body, media_body=media_body, fields='id').execute()
        st.success(f"☁️ 「{file_name}」をGoogle Driveに保存しました。")
        
    except Exception as e:
        st.warning(f"Google Driveへの自動保存/クリーンアップ処理でエラーが発生しました: {e}")

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

# --- 補助関数：カレンダーの自動取得・作成 ---
def get_or_create_calendar(service, calendar_name):
    calendar_list = service.calendarList().list().execute()
    for cal in calendar_list.get('items', []):
        if cal.get('summary') == calendar_name:
            return cal.get('id')
    
    new_cal = {'summary': calendar_name}
    created_cal = service.calendars().insert(body=new_cal).execute()
    return created_cal.get('id')

# --- 補助関数：カラーID自動判定 ---
def get_color_id(shift_code, time_shift_check=None, found_key=None):
    shift_code_str = str(shift_code)
    if any(holiday in shift_code_str for holiday in ["休", "休日", "公休", "有休", "有給"]):
        return "11"
    
    blue_palette = ["7", "9", "1"]
    assigned_blue = "7"
    if found_key:
        hash_val = sum(ord(c) for c in str(found_key))
        assigned_blue = blue_palette[hash_val % len(blue_palette)]

    blue_patterns = ["T1", "T2", "H1", "K2", "A", "B", "C", "D"]
    if any(pattern in shift_code_str for pattern in blue_patterns):
        return assigned_blue
        
    if found_key and (found_key in shift_code_str or found_key == shift_code_str):
        return assigned_blue
        
    if time_shift_check is not None and not time_shift_check.empty:
        if (time_shift_check.iloc[:, 1] == shift_code_str).any():
            return assigned_blue
            
    if any(k in shift_code_str for k in ["出勤", "退勤", "frm", "to", "▷", "【"]) or "_" in shift_code_str:
        return assigned_blue
    
    return "5"

# --- [2] メイン処理 ---
st.title("シフト表解析システム")

if 'data_dict' not in st.session_state:
    st.session_state.data_dict = load_and_process_data()

if 'loaded_pdf_bytes' not in st.session_state:
    st.session_state.loaded_pdf_bytes = None
    st.session_state.loaded_pdf_name = None

if st.session_state.loaded_pdf_bytes is not None:
    if st.sidebar.button("📁 別のPDFを選択し直す"):
        st.session_state.loaded_pdf_bytes = None
        st.session_state.loaded_pdf_name = None
        for key in ['last_file_bytes', 'use_pdf_choice', 'df_calendar', 'show_conflict_options']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

if st.session_state.loaded_pdf_bytes is None:
    upload_option = st.radio("PDFの取得方法を選択してください", ["手動アップロード", "Google Driveから選択"], index=0)

    uploaded_file_obj = None

    if upload_option == "手動アップロード":
        uploaded_file_obj = st.file_uploader("PDFシフト表をアップロード", type="pdf")
        if uploaded_file_obj is not None:
            file_bytes_val = uploaded_file_obj.getvalue()
            file_name_val = uploaded_file_obj.name
            
            st.session_state.loaded_pdf_bytes = file_bytes_val
            st.session_state.loaded_pdf_name = file_name_val
            
            # --- 手動アップロード時にDriveへ保存し前々月を削除する処理 ---
            try:
                creds_dict = st.secrets["google_oauth_credentials"]
                creds_drive = Credentials.from_authorized_user_info(
                    creds_dict, 
                    scopes=["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive.readonly"]
                )
                drive_service = build('drive', 'v3', credentials=creds_drive)
                save_pdf_to_drive_and_cleanup(drive_service, file_bytes_val, file_name_val)
            except Exception as e:
                pass # 認証スコープ等の関係で失敗してもアプリ自体は止めない
                
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

# --- ファイルが選択・保持されたあとの処理 ---
uploaded_pdf = io.BytesIO(st.session_state.loaded_pdf_bytes)
uploaded_pdf.name = st.session_state.loaded_pdf_name

uploaded_pdf.seek(0)
file_bytes = uploaded_pdf.getvalue()

if 'last_file_bytes' not in st.session_state || st.session_state.last_file_bytes != file_bytes:
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
        st.warning("このファイルの利用がキャンセルされました。別のファイルをアップロードし直してください。")
        st.stop()
    else:
        year_text_match = re.search(r'(\d{4})\s*年', pdf_full_text)
        y = int(year_text_match.group(1)) if year_text_match else 2026
        
        month_text_match = re.search(r'(\d{1,2})\s*月', pdf_full_text)
        m = int(month_text_match.group(1)) if month_text_match else 2

_, last_day_num = calendar.monthrange(y, m)
last_day_w = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, last_day_num)]

if A_date != last_day_num or A_day != last_day_w:
    st.error("整合性不一致: アップロードされたシフト表の年月が期待値と異なります。")
    display_pdf_as_images(file_bytes)
    st.stop()

st.divider()

staff_data = []
for idx in range(0, df_pdf.shape[0], 2):
    name_val = str(df_pdf.iloc[idx, 0])
    if name_val in st.session_state.data_dict.keys():
        continue
    
    clean_name = name_val.split('\n')[0].strip() if name_val != 'None' else "該当なし"
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
    mask = other_staff_shift.iloc[:, col].isin(codes)
    return other_staff_shift.loc[mask, other_staff_shift.columns[0]].tolist()

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    time_shift = time_schedule.fillna("").astype(str)
    if not (time_shift.iloc[:, 1] == shift_info).any():
        return
       
    my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]
    if my_time_shift.empty:
        return

    prev_val = ""
    row_data = my_time_shift.iloc[0]

    for t_col in range(3, my_time_shift.shape[1]):
        current_val = row_data[t_col]
        subject, start, change, takeover, handover, break_change, end = "", "", "", "", "", "", ""
      
        if current_val != prev_val:
            if current_val != "":
                final_rows.append([subject, target_date, "", target_date, "", "False", "", found_key])
                start_time = time_shift.iloc[0, t_col]
            
                if (row_data[3:t_col] == "").all():
                    start = "(出勤)："
                    
                if row_data[t_col - 1] == "":              
                    mask_change = (time_shift.iloc[:, t_col - 1] != "") & (time_shift.iloc[:, t_col] == "")
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
                    handover_codes = time_shift.loc[time_shift.iloc[:, t_col] == prev_val, time_shift.columns[1]]
                    handover_staff = get_staff_names(handover_codes, other_staff_shift, col)
                    handover = f"to {','.join(handover_staff)}"
                    final_rows[-2][0] += handover
                
                takeover_codes = time_shift.loc[time_shift.iloc[:, t_col - 1] == current_val, time_shift.columns[1]]
                takeover_staff = get_staff_names(takeover_codes, other_staff_shift, col)
                takeover = f"from {','.join(takeover_staff)}【{current_val}】" if takeover_staff else f"frm 【{current_val}】"

                subject = start + change + takeover
                final_rows[-1][0] = subject
                final_rows[-1][2] = start_time
               
            else:
                mask_break = (time_shift.iloc[:, t_col - 1] == "") & (time_shift.iloc[:, t_col] != "")
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
                
                handover_codes = time_shift.loc[time_shift.iloc[:, t_col] == prev_val, time_shift.columns[1]]
                handover_staff = get_staff_names(handover_codes, other_staff_shift, col)
                handover = f"to {','.join(handover_staff)}"                   

                final_rows[-1][0] += handover + break_change + end   
                final_rows[-1][4] = end_time                            
            
        prev_val = current_val

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

        if (time_shift_check.iloc[:, 1] == schedule_val).any():
            final_rows.append([f"{found_key}_{schedule_val}", target_date, "", target_date, "", "True", "", found_key])
            shift_cal(found_key, target_date, col, schedule_val, my_df, other_df, time_schedule_df, final_rows)
        else:
            final_rows.append([schedule_val, target_date, "", target_date, "", "True", "", schedule_val])
            time_match = re.search(r'(\d+)[^\d]+(\d+)', sub_val)
            if time_match:
                final_rows.append([schedule_val, target_date, f"{time_match.group(1)}:00", target_date, f"{time_match.group(2)}:00", "False", "", ""])

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
        count = st.session_state.get('existing_count', 0)
        st.warning(f"⚠️ 登録済みデータが **{count}件** あります。どうしますか？")
        
        conflict_action = st.radio(
            "処理方法を選択してください",
            ["全て削除後新たにデータを登録する", "既存のデータに重複表示する（そのまま追加）"],
            key="conflict_action_radio"
        )
        
        if st.button("実行する", key="execute_conflict_action_btn"):
            try:
                SCOPES = ['https://www.googleapis.com/auth/calendar']
                creds_dict = st.secrets["google_oauth_credentials"]
                creds = Credentials.from_authorized_user_info(creds_dict, scopes=SCOPES)
                service = build('calendar', 'v3', credentials=creds)
                target_cal_id = get_or_create_calendar(service, found_key)
                
                last_day = calendar.monthrange(y, m)[1]
                min_date = f"{y}-{m:02d}-01T00:00:00+09:00"
                max_date = f"{y}-{m:02d}-{last_day}T23:59:59+09:00"
                
                deleted_count = 0
                if "全て削除" in conflict_action:
                    events_result = service.events().list(
                        calendarId=target_cal_id, 
                        timeMin=min_date, 
                        timeMax=max_date,
                        singleEvents=True
                    ).execute()
                    for event in events_result.get('items', []):
                        service.events().delete(calendarId=target_cal_id, eventId=event['id']).execute()
                        deleted_count += 1

                success_count = 0
                time_schedule_df_check = st.session_state.data_dict.get(found_key, pd.DataFrame())
                time_shift_check_reg = time_schedule_df_check.fillna("").astype(str)
                total_rows = len(st.session_state.df_calendar)

                # --- ★機能追加①: カレンダー登録時のタイマー（プログレスバー）表示 ---
                progress_bar = st.progress(0)
                status_text = st.empty()

                with st.spinner("Googleカレンダーへ登録中です。しばらくお待ちください..."):
                    for idx, row in st.session_state.df_calendar.iterrows():
                        is_all_day = (str(row['AllDayEvent']) == "True")
                        start_date = str(row['StartDate']).replace('/', '-')
                        end_date = str(row['EndDate']).replace('/', '-')
                        
                        c_id = get_color_id(row['Subject'], time_shift_check_reg, found_key)
                        
                        if is_all_day:
                            event_body = {
                                'summary': row['Subject'], 
                                'location': row['Location'], 
                                'start': {'date': start_date}, 
                                'end': {'date': end_date},
                                'colorId': c_id
                            }
                        else:
                            start_time = str(row['StartTime']).zfill(5) if ':' in str(row['StartTime']) else str(row['StartTime'])
                            end_time = str(row['EndTime']).zfill(5) if ':' in str(row['EndTime']) else str(row['EndTime'])
                            event_body = {
                                'summary': row['Subject'], 
                                'location': row['Location'],
                                'start': {'dateTime': f"{start_date}T{start_time}:00", 'timeZone': 'Asia/Tokyo'},
                                'end': {'dateTime': f"{end_date}T{end_time}:00", 'timeZone': 'Asia/Tokyo'},
                                'colorId': c_id
                            }
                        
                        service.events().insert(calendarId=target_cal_id, body=event_body).execute()
                        success_count += 1
                        
                        # プログレスバーの更新
                        progress_val = min(success_count / total_rows, 1.0)
                        progress_bar.progress(progress_val)
                        status_text.text(f"登録中... ({success_count} / {total_rows} 件完了)")

                # 完了後にプログレスバー等をクリア
                progress_bar.empty()
                status_text.empty()

                st.session_state.show_conflict_options = False
                if "全て削除" in conflict_action:
                    st.success(f"「{found_key}」カレンダーを刷新しました！（削除: {deleted_count}件 / 新規登録: {success_count}件）")
                else:
                    st.success(f"「{found_key}」カレンダーにデータを追加しました！（重複登録: {success_count}件）")
            except Exception as e:
                st.error(f"登録実行エラー: {e}")
