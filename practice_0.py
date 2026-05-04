import streamlit as st
import pandas as pd
import re
import unicodedata
import camelot
import os
import calendar
from googleapiclient.discovery import build
from google.oauth2 import service_account

def get_unified_services():
    """Google DriveおよびSheets APIのサービスを取得"""
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
        else:
            info = dict(st.secrets)
        if not info or "project_id" not in info:
            return None, None
        creds = service_account.Credentials.from_service_account_info(
            info, 
            scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build('drive', 'v3', credentials=creds), build('sheets', 'v4', credentials=creds)
    except Exception:
        return None, None

def normalize_text(text):
    """テキストの正規化（全角半角の統一、空白削除、小文字化）"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def load_time_schedule(sheets_service, file_id):
    """Google Sheetsから時程表（マスター）を読み込み、拠点名をキーとした辞書を作成"""
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
    time_dic = {}
    for s in spreadsheet.get('sheets', []):
        title = s.get("properties", {}).get("title")
        res = sheets_service.spreadsheets().values().get(spreadsheetId=file_id, range=f"'{title}'!A1:Z300").execute()
        vals = res.get('values', [])
        if not vals: continue
        df = pd.DataFrame(vals).fillna('')
        current_loc, start_idx = None, 0
        for i in range(len(df)):
            val_a = str(df.iloc[i, 0]).strip()
            if val_a != "":
                if current_loc:
                    time_dic[normalize_text(current_loc)] = process_schedule_block(df.iloc[start_idx:i, :])
                current_loc, start_idx = val_a, i
        if current_loc:
            time_dic[normalize_text(current_loc)] = process_schedule_block(df.iloc[start_idx:, :])
    return time_dic

def process_schedule_block(block_df):
    """時程表の数値データを時刻形式（HH:mm）に変換"""
    def num_to_time(val):
        try:
            f_val = float(val)
            hours = int(f_val)
            minutes = int(round((f_val - hours) * 60))
            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, TypeError): return val
    new_df = block_df.iloc[:, :3].copy()
    time_cols = block_df.iloc[:, 3:].map(num_to_time)
    return pd.concat([new_df, time_cols], axis=1)

def verify_first_gate(filename, pdf_0_0, manual_date=None):
    """
    年月とPDF内容の整合性を検証する第1ゲート。
    不一致時は詳細な理由を返す。
    """
    if manual_date:
        y, m = manual_date
    else:
        match_y = re.search(r'(\d{4})', filename)
        match_m = re.search(r'(\d{1,2})', filename)
        if match_y and match_m:
            y, m = int(match_y.group(1)), int(match_m.group(1))
        else:
            return False, "理由: ファイル名から年月を特定できません。手動入力が必要です。", None
    
    # 計算上の末日と曜日の取得
    _, last_day_calc = calendar.monthrange(y, m)
    w_list = ["月", "火", "水", "木", "金", "土", "日"]
    first_w_calc = w_list[calendar.weekday(y, m, 1)]

    # PDF(セル0,0)から日付（1-31）と曜日（月-日）を抽出
    found_dates = [int(d) for d in re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', pdf_0_0)]
    found_days = re.findall(r'[月火水木金土日]', pdf_0_0)
    last_day_pdf = max(found_dates) if found_dates else 0
    first_w_pdf = found_days[0] if found_days else ""

    # 1日の曜日と末日が一致するか確認
    if last_day_calc == last_day_pdf and first_w_calc == first_w_pdf:
        return True, "通過", (found_dates, found_days, y, m)
    else:
        reason = (f"理由: 指定年月({y}/{m})とPDF内容が一致しません。\n"
                  f"【期待】 1日({first_w_calc})・末日({last_day_calc}日)\n"
                  f"【PDF 】 1日({first_w_pdf})・末日({last_day_pdf}日)")
        return False, reason, None

def analyze_pdf_structural(pdf_stream, master_keys, filename, manual_date=None):
    """
    PDFを解析し、構造化データとスタッフリストを生成。
    スタッフリストからは拠点名(Key)を完全に除外する。
    """
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='1', flavor='lattice')
        if not tables: return None, "理由: 表が検出されませんでした。"
        
        raw_df = tables[0].df
        raw_0_0 = str(raw_df.iloc[0, 0])
        
        # 整合性検証
        success, msg, date_info = verify_first_gate(filename, raw_0_0, manual_date)
        if not success: return None, msg
        
        found_dates, found_days, y, m = date_info
        
        # 拠点名(location)の特定（マスターキーとの照合）
        location = "特定不能"
        for k in master_keys:
            if k in normalize_text(raw_0_0):
                location = k
                break
        
        # スタッフリストの生成（2行おきに氏名セルを取得し、拠点名を除外）
        staff_list = []
        loc_norm = normalize_text(location)
        for i in range(2, len(raw_df), 2):
            name = str(raw_df.iloc[i, 0]).split('\n')[0].strip()
            if name and name.lower() != 'nan':
                # 氏名が拠点名（マスターキー）と一致する場合はスキップ
                if normalize_text(name) != loc_norm:
                    staff_list.append(name)
            
        # 表示・照合用データフレームの構築
        final_rows = [[""] + found_dates, [location] + found_days]
        for i in range(2, len(raw_df)):
            cell = str(raw_df.iloc[i, 0]).strip()
            row_data = raw_df.iloc[i, 1:].tolist()
            # 氏名行（偶数行）の場合は1行目の名前のみを抽出、それ以外はセルそのまま
            name_val = cell.split('\n')[0] if i % 2 == 0 else cell
            final_rows.append([name_val] + row_data)
            
        return {
            "df": pd.DataFrame(final_rows), 
            "location": location, 
            "staff_list": staff_list, 
            "year": y, 
            "month": m
        }, "通過"
        
    finally:
        if os.path.exists("temp.pdf"): os.remove("temp.pdf")
