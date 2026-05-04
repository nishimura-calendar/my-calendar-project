import pandas as pd
import camelot
import re
import calendar
import math

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def load_master_from_sheets(service, spreadsheet_id):
    """時程表を読み込み、勤務地をキーに辞書登録[cite: 3, 5]"""
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
    """時程表の時間列変換[cite: 3]"""
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
    """第一関門・座標設定・データ抽出"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0])
    
    # ② ファイル内容から抽出
    # 日付文字列（連続した数字）を抽出
    date_nums = re.findall(r'\d+', raw_0_0)
    pdf_last_day = int(date_nums[-1]) if date_nums else 0
    # 曜日を抽出
    days_found = re.findall(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = days_found[0] if days_found else ""
    
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        reason = f"第一関門失敗: 計算={calc_last_day}({calc_first_w}) / PDF={pdf_last_day}({pdf_first_w})"
        return None, reason

    # <2> location抽出: 日付文字列(連続数字の始〜終)と曜日文字列を除去[cite: 8]
    # 連続した数字の塊をすべて除去
    location = re.sub(r'\d+', '', raw_0_0)
    # 曜日および付随する記号を除去
    location = re.sub(r'\(?[月火水木金土日]\)?', '', location)
    # その他年月表記などを掃除
    location = re.sub(r'[年月\s/：:-]', '', location).strip()
    
    # 整形データ作成
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # [0,0]=""[cite: 8]
    rows.append([location] + df.iloc[1, 1:].tolist()) # [1,0]=location[cite: 8]
    
    staff_names = []
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        if i % 2 == 0 and cell:
            name = cell.split('\n')[0]
            staff_names.append(name)
            rows.append([name] + df.iloc[i, 1:].tolist()) # 氏名[cite: 8]
        else:
            rows.append([cell] + df.iloc[i, 1:].tolist()) # 資格[cite: 8]
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"
