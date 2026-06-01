import pandas as pd
import camelot
import re
import calendar

def get_calc_date_info(y, m):
    """A：取得した年月から算出する最終日付（日数）と最終曜日を取得する"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    last_w = w_list[calendar.weekday(y, m, last_day)]
    return last_day, last_w

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

def process_time_block(block):
    """時程表の時間変換処理"""
    def to_time(v):
        try:
            f = float(v)
            return f"{int(f):02d}:{int(round((f-int(f))*60)):02d}"
        except: return v
    time_cols = []
    for col in range(3, block.shape[1]):
        try:
            float(block.iloc[0, col])
            time_cols.append(col)
        except:
            if time_cols: break
    res_df = block.iloc[:, [0, 1, 2] + time_cols].copy()
    for i in range(len(time_cols)):
        res_df.iloc[0, 3 + i] = to_time(res_df.iloc[0, 3 + i])
    return res_df

def analyze_pdf_structure(pdf_path, y, m):
    """第1関門：仕様(2)に基づき、1行目の日付文字列全体から月末日・末尾曜日を厳密に特定する"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    
    # A：取得した年月から算出する最終日付と最終曜日
    calc_last_day, calc_last_w = get_calc_date_info(y, m)
    
    # B：詠込んだpdfシフト表ファイルから最終日付と最終曜日を取得する
    pdf_last_day = 0
    pdf_last_w = ""
    target_col_idx = -1
    
    # 仕様(2)より、行0は1〜月末までの日付文字列。
    # 各セルから数値をすべて抽出し、その中で「最大の数値」を月末日として特定する
    for col_idx in range(1, df.shape[1]):
        cell_text = str(df.iloc[0, col_idx]).strip()
        days_in_cell = [int(d) for d in re.findall(r'\d+', cell_text)]
        if days_in_cell:
            max_day_in_cell = max(days_in_cell)
            if max_day_in_cell > pdf_last_day:
                pdf_last_day = max_day_in_cell
                target_col_idx = col_idx

    # 月末日が見つかった列の、行1（曜日行）から末尾の曜日を取得する
    if target_col_idx != -1:
        combined_text = str(df.iloc[0, target_col_idx]) + " " + str(df.iloc[1, target_col_idx])
        weeks_found = re.findall(r'[月火水木金土日士]', combined_text)
        if weeks_found:
            pdf_last_w = weeks_found[-1]
            if pdf_last_w == "士":
                pdf_last_w = "土"

    # A=Bならそのまま通過、A≠Bなら不一致エラー
    if not (pdf_last_day == calc_last_day and pdf_last_w == calc_last_w):
        return None, f"不一致：計算上の月末={calc_last_day}日({calc_last_w}) ／ PDFの末尾={pdf_last_day}日({pdf_last_w})"

    # [0,0]近辺から勤務地(location)を抽出
    raw_0_0 = str(df.iloc[0, 0]).strip()
    if raw_0_0 == "" or len(raw_0_0) <= 2:
        raw_0_0 = str(df.iloc[1, 0]).strip()
        
    location = re.sub(r'\(?[月火水木金土日士]\)?', '', raw_0_0)
    location = re.sub(r'\d+[\s～~-]+\d+', '', location)
    location = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', location)
    location = re.sub(r'[年月日で\s/：:-]', '', location).strip()
    
    # 内部処理用データ構造への組み替え
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location] + df.iloc[1, 1:].tolist())
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.
