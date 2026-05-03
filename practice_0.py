import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import math
from googleapiclient.discovery import build
from google.oauth2 import service_account

def get_unified_services():
    info = st.secrets.get("gcp_service_account")
    if not info: return None, None
    try:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except: return None, None

def normalize_text(text):
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', str(text))).lower()

def clean_strictly(text):
    """[0,0]から拠点名(T1/T2等)のみを抽出"""
    text = re.sub(r'\b([1-9]|[12][0-9]|3[01])\b', '', str(text))
    text = re.sub(r'[月火水木金土日()/:：\s　\n]', '', text)
    return normalize_text(text)

def analyze_pdf_full(pdf_file, master_keys):
    """
    要求:
    0行目: 日付 (1-31)
    1行目: 曜日 & 拠点 [1,0]=location
    2行目以降: 氏名行
    3行目以降: 資格行 (氏名の直下)
    """
    with open("temp.pdf", "wb") as f:
        f.write(pdf_file.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, pd.DataFrame([{"エラー": "表未検出"}])
        
        raw_df = tables[0].df
        
        # 1. 拠点の特定
        ans = clean_strictly(str(raw_df.iloc[0, 0]))
        location = "T1"
        for k in master_keys:
            if k in ans:
                location = k
                break

        # 2. 日付・曜日の抽出 (NaN回避ロジック)
        # raw_dfのどこかに日付(1-31)と曜日が含まれている前提で再取得
        dates = []
        days = []
        for col in range(1, len(raw_df.columns)):
            # セル内の全ての改行から数字(日付)と曜日を分離
            cell_text = str(raw_df.iloc[0, col]) + "\n" + str(raw_df.iloc[1, col])
            d_match = re.search(r'\b([1-9]|[12][0-9]|3[01])\b', cell_text)
            w_match = re.search(r'[月火水木金土日]', cell_text)
            dates.append(d_match.group(0) if d_match else "")
            days.append(w_match.group(0) if w_match else "")

        # 3. 氏名・資格の展開
        # 同一セル内の改行、または上下のセルから「氏名」と「資格」を分離
        final_rows = []
        final_rows.append(["日付"] + dates)      # 行0
        final_rows.append([location] + days)     # 行1
        
        max_name_len = len(location)
        
        # 2行目以降を走査
        for i in range(2, len(raw_df)):
            cell_0 = str(raw_df.iloc[i, 0]).strip()
            if not cell_0 or cell_0 == "nan": continue
            
            # セル内に改行がある場合は分割 (氏名\n資格 のパターン対応)
            parts = cell_0.split('\n')
            name = parts[0]
            license = parts[1] if len(parts) > 1 else ""
            
            # シフトデータ行の取得
            shift_row = raw_df.iloc[i, 1:].tolist()
            
            # 氏名行を追加
            final_rows.append([name] + shift_row)
            # 資格行を追加 (氏名の直下)
            final_rows.append([license] + [""] * len(shift_row))
            
            max_name_len = max(max_name_len, len(name))

        final_df = pd.DataFrame(final_rows)
        l = math.ceil(max_name_len)

        report_df = pd.DataFrame([{
            "拠点": location,
            "算出座標 l": l,
            "日付・曜日": "抽出成功" if any(dates) else "要確認"
        }])

        return {"df": final_df, "location": location, "l": l}, report_df
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
