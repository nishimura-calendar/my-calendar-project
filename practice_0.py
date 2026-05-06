import pandas as pd
import camelot
import re
import calendar
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account

def get_service():
    """GCP認証[cite: 8]"""
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build('sheets', 'v4', credentials=creds)

def load_master_from_sheets(service, spreadsheet_id):
    """スプレッドシートから時程表を読み込む[cite: 7]"""
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
    """時程データの整形[cite: 7]"""
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
    """PDF解析、拠点特定、およびスタッフ抽出[cite: 5, 7]"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    raw_0_0 = str(df.iloc[0, 0]).strip()
    
    # 拠点名の特定 (T1など)[cite: 7]
    loc = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    loc = re.sub(r'\d+[\s～~-]+\d+', '', loc)
    loc = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', loc)
    location = re.sub(r'[年月日で\s/：:-]', '', loc).strip()

    # スタッフ名リスト作成 (拠点名と一致するものは除外)
    staff_names = []
    for i in range(2, len(df), 2):
        name = str(df.iloc[i, 0]).split('\n')[0].strip()
        if name and name != location:
            staff_names.append(name)
    
    # 表示用データフレームの整形[cite: 7]
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) 
    rows.append([location] + df.iloc[1, 1:].tolist()) 
    for i in range(2, len(df)):
        cell = str(df.iloc[i, 0]).strip()
        val = cell.split('\n')[0] if i % 2 == 0 else cell
        rows.append([val] + df.iloc[i, 1:].tolist())
            
    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "通過"
