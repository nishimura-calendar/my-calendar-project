import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    # calendar.weekday: 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
    w_idx = calendar.weekday(y, m, 1)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[w_idx]
    return last_day, first_w

def load_master_from_sheets(service, spreadsheet_id):
    """時程表を読み込み、勤務地をキーに辞書登録"""
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    time_dic = {}
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        res = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=f"'{title}'!A1:Z300").execute()
        vals = res.get('values', [])
        if not vals: continue
        df = pd.DataFrame(vals).fillna('')

        current_loc, start_idx = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_loc:
                    time_dic[current_loc] = process_time_block(df.iloc[start_idx:i, :])
                current_loc, start_idx = val_a, i
        if current_loc:
            time_dic[current_loc] = process_time_block(df.iloc[start_idx:, :])
    return time_dic

def process_time_block(df):
    """時程表の各勤務地ブロックを整形"""
    # A-C列 + 時間列の抽出ロジック（詳細は既存仕様を維持）
    return df

def analyze_pdf_structure(pdf_path, y, m):
    """第1・第2関門：構造解析と照合"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDFから表を抽出できませんでした。"
    
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).replace('\n', ' ').strip()
    
    # --- 第1関門照合 ---
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    days_in_pdf = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(days_in_pdf) if days_in_pdf else 0
    pdf_first_w_match = re.search(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = pdf_first_w_match.group() if pdf_first_w_match else ""

    if pdf_last_day != calc_last_day or pdf_first_w != calc_first_w:
        return None, f"第1関門不通過: 算出={calc_last_day}{calc_first_w} / PDF={pdf_last_day}{pdf_first_w}"

    # --- 第2関門：location特定 ---
    location = re.sub(r'[月火水木金土日]', '', raw_0_0)
    location = re.sub(r'\b(?:[1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]|勤務予定表|～|~', '', location).strip()
    
    # データ組替
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist())
    rows.append([location] + df.iloc[1, 1:].tolist())
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
        if i % 2 == 0 and val and val != location:
            staff_names.append(val)
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"

def extract_target_data(df, target_staff, location):
    """第3関門：データの抽出"""
    if target_staff not in df[0].values: return None
    idx = df[df[0] == target_staff].index[0]
    my_daily_shift = df.iloc[idx : idx+2, :]
    other_daily_shift = df[(df.index >= 2) & (df.index % 2 == 0)
