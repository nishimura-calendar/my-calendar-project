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
    """
    if not cell_text or str(cell_text).lower() == 'nan': return "Unknown"
    lines = [l.strip() for l in cell_text.split('\n') if l.strip()]
    if not lines: return "Unknown"
    
    full_norm = normalize_text(cell_text)
    if "t1" in full_norm: return "T1"
    if "t2" in full_norm: return "T2"
    
    # 改行数の中央行を取得
    target_idx = cell_text.count('\n') // 2
    return lines[target_idx] if target_idx < len(lines) else lines[-1]

# --- PDF解析 (Camelot) ---
def pdf_reader(pdf_stream, target_staff):
    """Ghostscriptを利用してPDFから表を抽出。"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    with pdfplumber.open(temp_path) as pdf:
        full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])
        y_m = re.search(r'(202\d)年\s*(\d{1,2})月', full_text)
        year = int(y_m.group(1)) if y_m else None
        month = int(y_m.group(2)) if y_m else None

    table_results = {}
    try:
        # flavor='stream' は罫線がなくても文字の配置で表を認識するモード
        tables = camelot.read_pdf(temp_path, pages='all', flavor='stream')
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            work_place = get_workplace_from_cell(str(df.iloc[0, 0]))
            
            col_map = {}
            for c_idx in range(len(df.columns)):
                day, wday = extract_date_info(str(df.iloc[0, c_idx]))
                if day: col_map[c_idx] = {"day": day, "wday": wday}
            
            if not col_map: continue

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
    try:
        res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range='Sheet1!A:Z').execute()
        values = res.get('values', [])
        # 1行目は時間ヘッダー
        return pd.DataFrame(values)
    except: return pd.DataFrame()

# --- スケジュール生成ロジック ---
def shift_cal(key, target_date, col_idx, shift_info, others, time_schedule, final_rows):
    """
    時程表(DataFrame)に基づいた詳細スケジュールの生成。
    """
    # 終日予定
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", f"コード: {shift_info}", key])
    
    # 時程詳細の探索 (2列目がシフトコードと一致する行を探す)
    if not time_schedule.empty:
        my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str) == shift_info]
        if not my_time_shift.empty:
            prev_val = ""
            for t_col in range(2, time_schedule.shape[1]):
                current_val = str(my_time_shift.iloc[0, t_col]) if t_col < my_time_shift.shape[1] else ""
                if current_val != prev_val:
                    if current_val != "" and current_val != 'None':
                        start_t = str(time_schedule.iloc[0, t_col])
                        final_rows.append([f"【{current_val}】", target_date, start_t, target_date, "", "False", "", key])
                    else:
                        if final_rows and final_rows[-1][5] == "False":
                            final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
                prev_val = current_val

def build_calendar_df(integrated_data, year, month):
    final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    
    for loc, content in integrated_data.items():
        pdf_data = content["pdf"]
        time_schedule = content["times"]
        my_row, col_map, others = pdf_data["my_row"], pdf_data["col_map"], pdf_data["others"]
        
        for d in range(1, num_days + 1):
            date_str = f"{year}-{month:02d}-{d:02d}"
            c_idx = next((k for k, v in col_map.items() if v["day"] == d), None)
            if c_idx is None: continue
            
            cell_val = str(my_row.iloc[0, c_idx]).strip()
            # 数字や曜日を除いたシフトコードを抽出
            codes = [p for p in re.split(r'[\s\n]+', cell_val) if p and not p.isdigit() and p not in "月火水木金土日"]
            
            for code in codes:
                if any(k in code for k in "休公有特欠振替"):
                    final_rows.append([f"【{code}】", date_str, "", date_str, "", "True", "休暇", loc])
                else:
                    shift_cal(loc, date_str, c_idx, code, others, time_schedule, final_rows)
                    
    return final_rows
