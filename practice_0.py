import pandas as pd
import camelot
import re
import calendar
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account

def get_service():
    info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build('sheets', 'v4', credentials=creds)

def analyze_pdf_structure(pdf_path, y, m):
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    if not tables: return None, "PDF表抽出失敗"
    df = tables[0].df
    
    # location特定[cite: 7]
    raw_0_0 = str(df.iloc[0, 0]).strip()
    loc = re.sub(r'\(?[月火水木金土日]\)?', '', raw_0_0)
    loc = re.sub(r'\d+[\s～~-]+\d+', '', loc)
    loc = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', loc)
    location = re.sub(r'[年月日で\s/：:-]', '', loc).strip()

    # スタッフ名リスト作成 (locationと一致するものは徹底排除)[cite: 5]
    staff_names = []
    for i in range(2, len(df), 2):
        # 名前セルの1行目を取得
        full_name = str(df.iloc[i, 0]).split('\n')[0].strip()
        # 空文字でなく、かつ拠点名(T1等)と一致しない場合のみ追加
        if full_name and full_name != location:
            staff_names.append(full_name)

    # 表示用データフレーム作成[cite: 7]
    rows = []
    rows.append([""] + df.iloc[0, 1:].tolist()) # 0行目
    rows.append([location] + df.iloc[1, 1:].tolist()) # 1行目
    for i in range(2, len(df)):
        cell_val = str(df.iloc[i, 0]).strip()
        name_val = cell_val.split('\n')[0] if i % 2 == 0 else cell_val
        rows.append([name_val] + df.iloc[i, 1:].tolist())

    return {"df": pd.DataFrame(rows), "location": location, "staff_list": staff_names}, "成功"

# ※ load_master_from_sheets と process_time_block は以前のコードを維持してください
