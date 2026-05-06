import pandas as pd
import camelot
import re
import calendar
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account

def get_service():
    """GCP認証：app.pyから呼び出せるように定義"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def get_calc_date_info(y, m):
    """① ファイル名から算出する日数と第一曜日[cite: 7]"""
    _, last_day = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w = w_list[calendar.weekday(y, m, 1)]
    return last_day, first_w

def load_master_from_sheets(service, spreadsheet_id):
    """時程表を読み込み[cite: 7]"""
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    time_dic = {}
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        res = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"'{title}'!A1:Z300"
        ).execute()
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
    """時程表の時間変換[cite: 7]"""
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
    """PDF解析とスタッフリスト作成[cite: 5, 7]"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).strip()
    
    # location確定 (T1等)
    loc = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    loc = re.sub(r'\d+[\s～~-]+\d+', '', loc)
    loc = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', loc)
    location = re.sub(r'[年月日で\s/：:-]', '', loc).strip()
    
    # 第一関門判定[cite: 7]
    nums = [int(n) for n in re.findall(r'\d+', raw_0_0)]
    pdf_last_day = max(nums) if nums else 0
    pdf_first_w = re.findall(r'[月火水木金土日]', raw_0_0)[0] if re.findall(r'[月火水木金土日]', raw_0_0) else ""
    calc_last_day, calc_first_w = get_calc_date_info(y, m)
    
    if not (pdf_last_day == calc_last_day and pdf_first_w == calc_first_w):
        return None, f"不一致：計算={calc_last_day}({calc_first_w}) / PDF={pdf_last_day}({pdf_first_w})"

    # 第3関門：スタッフ名リスト作成（locationと同じ名前を除去）
    staff_names = []
    for i in range(2, len(df), 2):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        if name and name != location: # ここで T1 等を除外
            staff_names.append(name)
    
    # データ組替[cite: 7]
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location] + df.iloc[1, 1:].tolist()) 
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"
