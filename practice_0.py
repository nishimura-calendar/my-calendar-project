import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 共通ユーティリティ ---
def normalize_text(text):
    """テキストの正規化（全角→半角、改行削除、空白削除）"""
    if not isinstance(text, str): return ""
    text = text.replace('\n', '')
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_date_info(text):
    """セルから日付(数字)と曜日を抽出"""
    day_match = re.search(r'(\d+)', text)
    wday_match = re.search(r'([月火水木金土日])', text)
    day = int(day_match.group(1)) if day_match else None
    wday = wday_match.group(1) if wday_match else None
    return day, wday

def get_workplace_from_cell(cell_text):
    """
    左上セル(iloc[0,0])から勤務地名を特定。
    基本事項.docx準拠：改行数の中央行を取得。
    """
    if not cell_text or str(cell_text).lower() == 'nan': return "Unknown"
    lines = [l.strip() for l in cell_text.split('\n') if l.strip()]
    if not lines: return "Unknown"
    
    full_norm = normalize_text(cell_text)
    if "t1" in full_norm: return "T1"
    if "t2" in full_norm: return "T2"
    
    target_idx = cell_text.count('\n') // 2
    return lines[target_idx] if target_idx < len(lines) else lines[-1]

# --- PDF解析 (Camelot) ---
def pdf_reader(pdf_stream, target_staff):
    """Ghostscriptを利用してPDFから表を抽出。勤務地・スタッフ行を特定。"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    # 年月の特定 (pdfplumber)
    with pdfplumber.open(temp_path) as pdf:
        full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])
        y_m = re.search(r'(202\d)年\s*(\d{1,2})月', full_text)
        year = int(y_m.group(1)) if y_m else None
        month = int(y_m.group(2)) if y_m else None

    table_results = {}
    try:
        # Ghostscriptがインストールされていれば、flavor='stream'または'lattice'が動作
        tables = camelot.read_pdf(temp_path, pages='all', flavor='stream')
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # 1. 勤務地アンカー特定
            work_place = get_workplace_from_cell(str(df.iloc[0, 0]))
            
            # 2. 列マップ（日付）
            col_map = {}
            for c_idx in range(len(df.columns)):
                day, wday = extract_date_info(str(df.iloc[0, c_idx]))
                if day: col_map[c_idx] = {"day": day, "wday": wday}
            
            if not col_map: continue

            # 3. スタッフ行抽出
            my_row = None
            other_rows = []
            for r_idx in range(len(df)):
                row_content = normalize_text("".join(df.iloc[r_idx, :].astype(str)))
                if clean_target in row_content:
                    my_row = df.iloc[r_idx : r_idx+1, :]
                else:
                    other_rows.append(df.iloc[r_idx : r_idx+1, :])
            
            if my_row is not None:
                table_results[work_place] = {
                    "my_row": my_row,
                    "others": pd.concat(other_rows) if other_rows else pd.DataFrame(),
                    "col_map": col_map
                }
    except Exception as e:
        print(f"Camelot解析エラー: {e}")
        
    return table_results, year, month

# --- Google Sheets 連携 ---
def get_sheets_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def fetch_time_schedule(service, spreadsheet_id):
    """勤務地名をキーに時程表を取得"""
    try:
        res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range='Sheet1!A:Z').execute()
        values = res.get('values', [])
        return {normalize_text(r[0]).upper(): r for r in values if r}
    except: return {}

# --- スケジュール生成ロジック (打合.py由来) ---
def shift_cal(key, target_date, col_idx, shift_info, others, time_schedule_row, final_rows):
    """
    時程表(SS)に基づいた詳細スケジュールの生成。
    time_schedule_row[0]は勤務地、[1]はシフトコードを想定。
    """
    # 終日予定（勤務地_シフト名）
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", f"コード: {shift_info}", key])
    
    # 時程詳細（簡易実装：SSのA列(勤務地)と一致するデータを使用）
    # ※ 本来はここで詳細な時間割ループを行う
    pass

def build_calendar_df(integrated_data, year, month):
    final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    
    for loc, content in integrated_data.items():
        pdf = content["pdf"]
        ss_row = content["times"]
        my_row, col_map, others = pdf["my_row"], pdf["col_map"], pdf["others"]
        
        for d in range(1, num_days + 1):
            date_str = f"{year}-{month:02d}-{d:02d}"
            c_idx = next((k for k, v in col_map.items() if v["day"] == d), None)
            if c_idx is None: continue
            
            cell_val = str(my_row.iloc[0, c_idx]).strip()
            codes = [p for p in re.split(r'[\s\n]+', cell_val) if p and not p.isdigit() and p not in "月火水木金土日"]
            
            for code in codes:
                if any(k in code for k in "休公有特欠振替"):
                    final_rows.append([f"【{code}】", date_str, "", date_str, "", "True", "休暇", loc])
                else:
                    shift_cal(loc, date_str, c_idx, code, others, ss_row, final_rows)
                    
    return final_rows
