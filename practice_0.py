import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- 1. 認証とテキスト正規化 ---
def get_unified_services():
    if "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    return None, None

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

# --- 2. 暦情報の取得 ---
def get_month_truth(year, month):
    last_day = calendar.monthrange(year, month)[1]
    first_wday_idx = calendar.monthrange(year, month)[0]
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, weekdays[first_wday_idx]

# --- 3. 解析メインロジック ---
def process_full_logic(pdf_stream, target_staff, time_dic, year, month):
    truth_days, truth_first_wday = get_month_truth(year, month)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())

    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "PDFから表を検出できませんでした。"
        df = tables[0].df

        # A. 拠点Keyの特定（1列目以降に混入している可能性も考慮）
        full_text_head = " ".join(df.iloc[0:5, 0].astype(str)) + " " + " ".join(df.iloc[0:5, 1].astype(str))
        key_match = re.search(r'T\d+', full_text_head)
        found_key = key_match.group(0) if key_match else "不明"
        
        matched_key = next((k for k in time_dic.keys() if normalize_text(found_key) in k or k in normalize_text(found_key)), None)
        if not matched_key:
            return df, f"Key『{found_key}』が時程表に見当たりません。"

        # B. 【改善】1日の列（Index 1）から動的に曜日を特定
        pdf_first_wday = ""
        # 1列目の上部（行0〜9）をスキャン
        for r in range(min(10, len(df))):
            cell_val = str(df.iloc[r, 1])
            # 1. まず「1」という数字が入っている行を探す、あるいは単に曜日を探す
            w_match = re.search(r'[月火水木金土日]', cell_val)
            if w_match:
                # 最初に見つかった曜日文字を採用
                pdf_first_wday = w_match.group(0)
                break
        
        # C. 整合性チェック
        if pdf_first_wday != truth_first_wday:
            return df, f"【整合性エラー】PDF解析では「{pdf_first_wday}曜始」ですが、暦では「{truth_first_wday}曜始」です。"

        # D. スタッフ抽出 (西村 文宏など、改行を含む名前に対応)
        search_col = df.iloc[:, 0].astype(str).apply(lambda x: normalize_text(x))
        clean_target = normalize_text(target_staff)
        
        target_idx = None
        for i, val in enumerate(search_col):
            if clean_target in val:
                target_idx = i
                break

        if target_idx is None:
            return df, f"『{target_staff}』が0列目に見つかりません。"

        return {
            "key": matched_key,
            "my_daily_shift": df.iloc[target_idx : target_idx + 2, :].values.tolist(),
            "other_daily_shift": [df.iloc[i].tolist() for i in range(len(df)) if i not in [0, 1, target_idx, target_idx+1] and any(str(v).strip() for v in df.iloc[i])],
            "time_schedule_full": time_dic[matched_key]
        }, None

    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
