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
    """時程表の時間変換処理[cite: 3]"""
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
    raw_0_0 = str(df.iloc[0, 0]).strip()
    
    # 丸数字(①-㉟)を通常の数字に変換する辞書
    maru_map = str.maketrans("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛", 
                             "12345678910111213141516171819202122232425262728293031")
    
    # ② ファイル内容から月末日と第一曜日を抽出
    converted_text = raw_0_0.translate(maru_map)
    nums = [int(n) for n in re.findall(r'\d+', converted_text)]
    pdf_last_day = max(nums) if nums else 0
    days_found = re.findall(r'[月火水木金土日]', raw_0_0)
    pdf_first_w = days_found[0] if days_found else ""
    
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    # 第一関門判定 ①=②なら通過
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        reason = f"不一致：計算={calc_last_day}({calc_first_w}) / PDF={pdf_last_day}({pdf_first_w})"
        return None, reason

    # ＜2＞ location抽出：日付文字列(塊)と曜日文字列を除去
    # 1. 曜日(括弧含む)を除去
    location = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    # 2. 日付の塊 (例: 1～31, 1~31) を除去
    location = re.sub(r'\d+[\s～~-]+\d+', '', location)
    # 3. 単位や記号、端に残った丸数字を除去
    location = re.sub(r'[①-㉟年月日で\s/：:-]', '', location).strip()
    
    # スタッフ名取得 [2,0]から1行おき
    staff_names = [str(df.iloc[i, 0]).split('\n')[0].strip() for i in range(2, len(df), 2) if str(df.iloc[i, 0]).strip()]
    
    # データ組替
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # [0,0]=""
    rows.append([location] + df.iloc[1, 1:].tolist()) # [1,0]=location
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        # 氏名は改行前を取得、資格はそのまま
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"
