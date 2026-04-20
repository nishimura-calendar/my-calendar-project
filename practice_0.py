import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# --- 1. テキストの正規化 (空白・改行を完全に除去) ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 空白、全角スペース、改行、タブをすべて除去して比較しやすくする
    return re.sub(r'[\s　\n\r\t]', '', unicodedata.normalize('NFKC', text)).lower()

# --- 2. 年月の抽出 (ファイル名を正とする) ---
def extract_year_month_from_text(text):
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    
    # 「○月」を特定
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    
    # 4桁の西暦を特定
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4:
            y_val = val
            break
        elif len(n) == 2 and y_val is None:
            y_val = 2000 + val
            
    return y_val, m_val

# --- 3. カレンダー整合性チェック (曜日と日数で比較) ---
def verify_calendar_consistency(df, year, month):
    """
    ファイル名の年月と、0行目の日付・曜日が一致するか確認。一致した表の勤務地名を返す。
    """
    if not year or not month:
        return False, "年月不明", "Unknown"
    
    # カレンダー上の期待される「1日の曜日」と「月末日」
    first_wday_idx, last_day = calendar.monthrange(year, month)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_wday = weekdays_jp[first_wday_idx]

    # 勤務地名（0行0列目の中央行を取得するロジック）
    header_raw = str(df.iloc[0, 0])
    header_lines = header_raw.splitlines()
    work_place = header_lines[len(header_lines)//2].strip() if header_lines else "Unknown"

    # 表から日付・曜日を抽出
    pdf_days = []
    for col in range(1, df.shape[1]):
        val = normalize_text(str(df.iloc[0, col]))
        d_m = re.search(r'(\d+)', val) # 日付
        w_m = re.search(r'([月火水木金土日])', val) # 曜日
        if d_m and w_m:
            pdf_days.append({"d": int(d_m.group(1)), "w": w_m.group(1)})

    if not pdf_days:
        return False, "日付行なし", work_place

    # 整合性チェック: 初日の曜日と末尾の日付を照合
    if pdf_days[0]["w"] != expected_first_wday or pdf_days[-1]["d"] != last_day:
        return False, "不一致", work_place

    return True, "", work_place

# --- 4. PDF解析メイン (基本に忠実な実装) ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    """
    app.pyの期待値に合わせて [table_dictionary, year, month] を返す
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    # ファイル名から年月を確定（これを正解とする）
    year, month = extract_year_month_from_text(file_name)
    
    try:
        # Camelotで解析
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except:
        return {}, year, month

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # 整合性チェック（勤務地行から抽出してファイル名と比較）
        is_valid, _, work_place = verify_calendar_consistency(df, year, month)
        if not is_valid:
            continue

        # 名前検索（1列目を対象）
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matched_indices = [i for i, v in enumerate(search_col) if clean_target in v]
        
        if matched_indices:
            idx = matched_indices[0]
            # 自分は2行取得（仕様通り）
            my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            # 他人は1行（0行目の見出しと、自分の2行分を除外）
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            
            table_dictionary[work_place] = [my_daily, others]
                
    return table_dictionary, year, month

# --- 5. Google Drive 連携 ---
def get_sheets_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly', 'https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def fetch_time_schedule(service, spreadsheet_id):
    try:
        request = service.files().export_media(fileId=spreadsheet_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        df = pd.read_excel(fh, header=None, engine='openpyxl')
        return df.fillna('')
    except:
        return pd.DataFrame()

# --- 6. カレンダーCSV作成用の枠組み ---
def build_calendar_df(integrated_dic, year, month):
    """
    ここから先の詳細ロジック（shift_cal呼び出し等）は uchiawase.py 等と連携して行います
    """
    final_rows = []
    return final_rows
