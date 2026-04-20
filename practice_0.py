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
    """テキストの正規化（全角→半角、改行、空白、タブをすべて除去）"""
    if not isinstance(text, str): return ""
    # 改行やタブをスペースに置換してから、すべての空白を除去
    text = text.replace('\n', ' ').replace('\t', ' ')
    normalized = unicodedata.normalize('NFKC', text)
    return re.sub(r'\s+', '', normalized).lower()

def extract_date_info(text):
    """セルから日付(数字)と曜日を抽出"""
    day_match = re.search(r'(\d+)', text)
    wday_match = re.search(r'([月火水木金土日])', text)
    day = int(day_match.group(1)) if day_match else None
    wday = wday_match.group(1) if wday_match else None
    return day, wday

def get_workplace_from_cell(cell_text):
    """左上セル(iloc[0,0])から勤務地名を特定"""
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
    """Ghostscriptを利用してPDFから表を抽出"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    # 年月の特定
    with pdfplumber.open(temp_path) as pdf:
        full_text = "\n".join([p.extract_text() or "" for p in pdf.pages])
        y_m = re.search(r'(202\d)年\s*(\d{1,2})月', full_text)
        year = int(y_m.group(1)) if y_m else None
        month = int(y_m.group(2)) if y_m else None

    table_results = {}
    try:
        # flavor='stream' を使用
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
            other_rows_list = []
            
            # スタッフ行の探索
            for r_idx in range(len(df)):
                # 名前が入っている可能性があるのは通常 0列目か1列目
                name_cell = str(df.iloc[r_idx, 0])
                clean_name = normalize_text(name_cell)
                
                # 入力された名前がセル内の文字列に含まれているか判定（部分一致）
                if clean_target != "" and clean_target in clean_name:
                    my_row = df.iloc[r_idx : r_idx+1, :]
                else:
                    other_rows_list.append(df.iloc[r_idx : r_idx+1, :])
            
            if my_row is not None:
                table_results[work_place] = {
                    "my_row": my_row,
                    "others": pd.concat(other_rows_list) if other_rows_list else pd.DataFrame(),
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
        return pd.DataFrame(values)
    except:
        return pd.DataFrame()

# --- スケジュール生成ロジック ---
def shift_cal(key, target_date, col_idx, shift_info, others, time_schedule, final_rows):
    """時程表に基づいた詳細スケジュールの生成"""
    # 終日予定を追加
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", f"コード: {shift_info}", key])
    
    if not time_schedule.empty and shift_info != "":
        # 2列目(index 1)がシフト記号と一致する行を探す
        my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.contains(shift_info, na=False)]
        
        if not my_time_shift.empty:
            prev_val = ""
            for t_col in range(2, time_schedule.shape[1]):
                current_val = str(my_time_shift.iloc[0, t_col]) if t_col < my_time_shift.shape[1] else ""
                if current_val != prev_val:
                    if current_val not in ["", "None", "nan"]:
                        # 開始時刻を取得 (1行目のヘッダー)
                        start_t = str(time_schedule.iloc[0, t_col])
                        final_rows.append([f"【{current_val}】", target_date, start_t, target_date, "", "False", "", key])
                    else:
                        # 終了時刻を直前の行にセット
                        if final_rows and final_rows[-1][5] == "False":
                            final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
                prev_val = current_val

def build_calendar_df(integrated_data, year, month):
    final_rows = []
    if not year or not month: return []
    
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
            # 数字や曜日、改行を除去して純粋なコードを抽出
            parts = re.split(r'[\s\n]+', cell_val)
            codes = [p for p in parts if p and not p.isdigit() and p not in "月火水木金土日"]
            
            for code in codes:
                if any(k in code for k in "休公有特欠振替"):
                    final_rows.append([f"【{code}】", date_str, "", date_str, "", "True", "休暇", loc])
                else:
                    shift_cal(loc, date_str, c_idx, code, others, time_schedule, final_rows)
                    
    return final_rows
