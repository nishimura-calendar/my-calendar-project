import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# --- 共通ユーティリティ (consideration_0.py準拠) ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    """
    consideration_0.pyのロジック。
    ※9114年等の誤判定を防ぐため、年は2000年代(4桁)を優先するよう微調整
    """
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4 and 2020 <= val <= 2040: # 正常な範囲の年を優先
            y_val = val
            break
        elif len(n) == 2 and y_val is None:
            y_val = 2000 + val
            
    if m_val is None:
        for n in nums:
            val = int(n)
            if 1 <= val <= 12:
                m_val = val
                break
    return y_val, m_val

# --- カレンダー整合性チェック (PDFを正とする) ---
def verify_calendar_consistency(df, year, month):
    """
    PDFの日数と初日の曜日がカレンダーと一致するか確認。
    28日〜31日のすべてのケースに対応。
    """
    if not year or not month:
        return False, "年月が特定できません。"
    
    # 実際のカレンダーから日数と初日の曜日(0=月...6=日)を取得
    first_wday_idx, last_day = calendar.monthrange(year, month)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_wday = weekdays_jp[first_wday_idx]

    # PDFの1行目（日付・曜日行）を解析
    pdf_days = []
    # 勤務地セルの右側からデータを取得
    for col in range(1, df.shape[1]):
        val = normalize_text(str(df.iloc[0, col]))
        d_m = re.search(r'(\d+)', val)
        w_m = re.search(r'([月火水木金土日])', val)
        if d_m and w_m:
            pdf_days.append({"d": int(d_m.group(1)), "w": w_m.group(1)})

    if not pdf_days:
        return False, "日付行が正しく読み取れませんでした。"

    # 1. 日数チェック (28, 29, 30, 31日)
    if pdf_days[-1]["d"] != last_day:
        return False, f"日数が不一致です (PDF:{pdf_days[-1]['d']}日 / 正解:{last_day}日)"
    
    # 2. 曜日チェック
    if pdf_days[0]["w"] != expected_first_wday:
        return False, f"1日の曜日が不一致です (PDF:{pdf_days[0]['w']} / 正解:{expected_first_wday})"

    return True, ""

# --- Google連携 (consideration_0.py準拠) ---
def get_sheets_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def time_schedule_from_drive(service, file_id):
    """consideration_0.py のスプレッドシート解析ロジック"""
    try:
        # Drive APIを使用してダウンロード
        creds = service._http.credentials
        drive_service = build('drive', 'v3', credentials=creds)
        
        file_metadata = drive_service.files().get(fileId=file_id, fields='mimeType').execute()
        request = drive_service.files().get_media(fileId=file_id)
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = drive_service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            
            # 時程行（数値）の特定と時刻文字列への変換
            time_row = temp_range.iloc[0, :]
            first_num_col = None
            last_num_col = None
            for col_idx, val in enumerate(time_row):
                if col_idx < 1: continue 
                try:
                    float(val)
                    if first_num_col is None: first_num_col = col_idx
                    last_num_col = col_idx
                except: continue
            
            if first_num_col is not None:
                start_col = max(1, first_num_col - 1)
                end_col = last_num_col + 1
                fixed_cols = [0, 1] 
                target_cols = fixed_cols + list(range(start_col, end_col))
                temp_range = temp_range.iloc[:, target_cols].copy()
                
                for col in range(len(temp_range.columns)):
                    if col < 2: continue
                    v = temp_range.iloc[0, col]
                    try:
                        f_v = float(v)
                        if 0 <= f_v <= 28:
                            h = int(f_v)
                            m = int(round((f_v - h) * 60))
                            temp_range.iloc[0, col] = f"{h}:{m:02d}"
                    except: pass
            
            location_data_dic[location_name] = temp_range.fillna('')
        return location_data_dic
    except Exception as e:
        raise e

def fetch_time_schedule(service, spreadsheet_id):
    """app.py用エイリアス"""
    try:
        dic = time_schedule_from_drive(service, spreadsheet_id)
        return list(dic.values())[0] if dic else pd.DataFrame()
    except: return pd.DataFrame()

# --- PDF解析 (consideration_0.py準拠) ---
def pdf_reader(pdf_stream, target_staff):
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    # 年月抽出
    year, month = None, None
    with pdfplumber.open(temp_path) as pdf:
        if len(pdf.pages) > 0:
            year, month = extract_year_month_from_text(pdf.pages[0].extract_text())

    try:
        # Camelotで全ページ解析
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except:
        return {}, year, month

    table_dictionary = {}
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # カレンダー整合性チェック (一致しない表は飛ばす)
        is_valid, _ = verify_calendar_consistency(df, year, month)
        if not is_valid: continue

        # 勤務地特定
        header = str(df.iloc[0, 0]).splitlines()
        work_place = header[len(header)//2] if header else "Unknown"
        
        # 名前検索
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matched_indices = df.index[search_col == clean_target].tolist()
        
        if matched_indices:
            idx = matched_indices[0]
            # 【仕様】自分は2行、他人は1行
            my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            table_dictionary[work_place] = [my_daily, others]
                
    return table_dictionary, year, month

# --- データ統合 (consideration_0.py準拠) ---
def data_integration(pdf_dic, time_dic):
    integrated = {}
    for pk, pv in pdf_dic.items():
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match:
            # [my_daily, others, time_schedule_df]
            integrated[match] = pv + [time_dic[match]]
    return integrated, []

# --- スケジュール生成 (app.pyからの呼び出し用) ---
def build_calendar_df(integrated_data, year, month):
    # ここに uchiawase.py (shift_cal) のロジックを連結させます
    return []
