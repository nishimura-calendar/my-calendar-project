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
    """テキストの正規化（空白・改行削除、全角→半角）"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　\n]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_date_info(text):
    """セルから日付(数字)と曜日を抽出"""
    day_match = re.search(r'(\d+)', text)
    wday_match = re.search(r'([月火水木金土日])', text)
    day = int(day_match.group(1)) if day_match else None
    wday = wday_match.group(1) if wday_match else None
    return day, wday

# --- PDF解析（Camelot + 勤務地アンカー） ---

def get_workplace_from_cell(cell_text):
    """基本事項.docxのロジック: 改行数などから勤務地を特定"""
    lines = [l.strip() for l in cell_text.split('\n') if l.strip()]
    if not lines:
        return "empty"
    
    # 勤務地候補の判定
    full_text = normalize_text(cell_text)
    if "t1" in full_text: return "T1"
    if "t2" in full_text: return "T2"
    
    # 基本事項に記載のあった動的判定ロジックのシミュレート
    target_index = cell_text.count('\n') // 2
    work_place = lines[target_index] if target_index < len(lines) else lines[-1]
    return work_place

def pdf_reader(pdf_stream, target_staff):
    """Camelotを使用して勤務地・日付・個人シフトを抽出"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    
    temp_pdf = "temp_process.pdf"
    with open(temp_pdf, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    # 年月の特定 (pdfplumber)
    with pdfplumber.open(temp_pdf) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        y_m = re.search(r'(202\d)年\s*(\d{1,2})月', first_page_text)
        year = int(y_m.group(1)) if y_m else None
        month = int(y_m.group(2)) if y_m else None

    table_dict = {}
    try:
        # 免税店シフト表の構造には stream が最適
        tables = camelot.read_pdf(temp_pdf, pages='all', flavor='stream')
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # 1. 勤務地(iloc(0,0))からのアンカー特定
            raw_work_cell = str(df.iloc[0, 0])
            work_place = get_workplace_from_cell(raw_work_cell)
            
            # T1/T2が含まれない場合はスキップ
            if not any(x in work_place.upper() for x in ["T1", "T2"]):
                # 他のセルも探索（念のため）
                combined_head = normalize_text("".join(df.iloc[0, :2].astype(str)))
                if "t1" in combined_head: work_place = "T1"
                elif "t2" in combined_head: work_place = "T2"
                else: continue

            # 2. 列マップ作成（日付行の特定）
            # 通常、勤務地がある行(0行目)が日付行
            col_map = {}
            for c_idx in range(len(df.columns)):
                cell_val = str(df.iloc[0, c_idx])
                day, wday = extract_date_info(cell_val)
                if day:
                    col_map[c_idx] = {"day": day, "wday": wday}

            # 3. スタッフ行の探索
            staff_row_idx = -1
            for r_idx in range(len(df)):
                row_txt = normalize_text("".join(df.iloc[r_idx, :].astype(str)))
                if clean_target in row_txt:
                    staff_row_idx = r_idx
                    break
            
            if staff_row_idx != -1:
                table_dict[work_place] = {
                    "shift_row": df.iloc[staff_row_idx:staff_row_idx+1, :],
                    "col_map": col_map
                }
                
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
        
    return table_dict, year, month

# --- 時程表解析（Google Sheets） ---

def get_sheets_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def fetch_time_schedule(service, spreadsheet_id):
    """スプレッドシートから勤務地をキーとした時程辞書を作成"""
    try:
        # A列=勤務地, D列以降=時間
        range_name = 'Sheet1!A:Z'
        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        
        time_map = {}
        for row in values:
            if not row: continue
            # A列(勤務地)を正規化してキーにする
            wp_key = normalize_text(row[0]).upper()
            if wp_key:
                # 勤務地行のD列(index 3)以降の時間を抽出
                times = row[3:] if len(row) > 3 else []
                time_map[wp_key] = times
        return time_map
    except Exception as e:
        print(f"Sheets Error: {e}")
        return {}

# --- データ統合・最終生成 ---

def build_calendar_df(integrated_data, year, month):
    """PDFのシフトと時程表の時間を紐付け、CSV用のリストを生成"""
    final_data = []
    if not year or not month: return []
    
    days_in_month = calendar.monthrange(year, month)[1]
    
    for loc, content in integrated_data.items():
        pdf = content.get("pdf")
        times = content.get("times", []) # 時程表のリスト
        
        shift_row = pdf["shift_row"]
        col_map = pdf["col_map"]
        
        for d in range(1, days_in_month + 1):
            date_str = f"{year}-{month:02d}-{d:02d}"
            
            # 日付に対応する列を探す
            col_idx = next((c for c, m in col_map.items() if m["day"] == d), None)
            if col_idx is None: continue
            
            cell_val = str(shift_row.iloc[0, col_idx]).strip()
            if not cell_val or cell_val.lower() == 'nan': continue
            
            # シフトコードの抽出
            # セル内から日付や曜日以外の文字列を取得
            parts = re.split(r'[\s\n]+', cell_val)
            codes = [p for p in parts if p and not p.isdigit() and p not in ["月","火","水","木","金","土","日"]]
            
            for code in codes:
                is_off = any(k in code for k in ["休", "公", "有", "特", "欠", "振", "替"])
                subj = f"【{code}】" if is_off else f"{loc}_{code}"
                
                # 時程表との紐付け（簡易版：将来的にコードに応じたindex計算を実装可能）
                desc = f"勤務地: {loc}, シフト: {code}"
                if times:
                    desc += f"\n参考時程: {' '.join(times[:5])}..."

                final_data.append([
                    subj, date_str, "", date_str, "", "True", desc, loc
                ])
                
    return final_data
