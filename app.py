import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from googleapiclient.discovery import build
from google.oauth2 import service_account
from practice_0 import pdf_reader, extract_year_month, time_schedule_from_drive

# --- 設定 ---
TIME_TABLE_ID = "1p7EBN1zTTt09etuQkZTIXBlNutUZqQkG"
TARGET_STAFF = "西村文宏"

st.set_page_config(page_title="シフト変換", layout="wide")
st.title("📅 シフトカレンダー一括変換（最新版）")

def get_gapi_service():
    try:
        info = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

def format_time(val):
    """数値やシリアル値を HH:MM 形式に変換。休憩時間などの無効値は空文字を返す"""
    if pd.isna(val) or str(val).strip() == "" or str(val).lower() == "nan":
        return ""
    try:
        if isinstance(val, str) and ":" in val:
            return val
        num = float(val)
        if num < 1: # シリアル値
            h = int(num * 24)
            m = int(round((num * 24 - h) * 60))
        else: # 17.5 などの数値
            h = int(num)
            m = int(round((num - h) * 60))
        return f"{h:02d}:{m:02d}"
    except:
        return str(val)

def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    """変化点だけを捉えて勤務時間のみを抽出するロジック"""
    clean_info = unicodedata.normalize('NFKC', str(shift_info)).strip()
    t_s = time_schedule.copy()
    
    # 自分の記号行を特定
    my_row = t_s[t_s.iloc[:, 1].astype(str).apply(lambda x: unicodedata.normalize('NFKC', x).strip()) == clean_info]
    if my_row.empty: return

    # 時刻ヘッダーを事前変換
    time_headers = [format_time(t_s.iloc[0, c]) for c in range(t_s.shape[1])]

    # 背景用の終日予定
    final_rows.append([f"{key}_{clean_info}", target_date, "", target_date, "", "True", "", key])
    
    prev_val = ""
    for t_col in range(2, t_s.shape[1]):
        raw_val = my_row.iloc[0, t_col]
        current_val = str(raw_val).strip() if pd.notna(raw_val) and str(raw_val).lower() != "nan" and str(raw_val) != "" else ""
        
        # 変化点の検知
        if current_val != prev_val:
            # 前の予定（勤務中だった場合）の終了時刻をセット
            if prev_val != "" and len(final_rows) > 0 and final_rows[-1][5] == "False":
                final_rows[-1][4] = time_headers[t_col]

            # 新しい勤務の開始（休憩明け含む）
            if current_val != "":
                # 引き継ぎ相手の特定
                h_dep = ""
                mask_h = pd.Series([False] * len(t_s))
                if prev_val == "":
                    # 勤務開始時の交代確認
                    mask_h = (t_s.iloc[:, t_col].astype(str).replace('nan','') == "") & (t_s.iloc[:, t_col-1].astype(str).replace('nan','') != "")
                    if mask_h.any(): h_dep = "(交代)"
                else:
                    h_dep = f"({prev_val})"
                    mask_h = (t_s.iloc[:, t_col].astype(str).str.strip() == prev_val)

                mask_t = (t_s.iloc[:, t_col-1].astype(str).str.strip() == current_val)
                
                # 相手名の抽出
                to_names, from_names = [], []
                for i, mask in enumerate([mask_h, mask_t]):
                    keys = t_s.loc[mask, t_s.columns[1]].unique()
                    names = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.strip().isin(keys)].iloc[:, 0].unique()
                    if i == 0: to_names = names.tolist()
                    else: from_names = names.tolist()

                subject = f"{h_dep}{'to ' + '・'.join(to_names) if to_names else ''}=>【{current_val}】{'from ' + '・'.join(from_names) if from_names else ''}"
                
                final_rows.append([subject, target_date, time_headers[t_col], target_date, "", "False", "", key])
                
        prev_val = current_val

# --- UI ---
uploaded_file = st.file_uploader("1. PDFをアップロード", type="pdf")

if uploaded_file and st.button("2. 変換開始"):
    service = get_gapi_service()
    if service:
        location_dic = time_schedule_from_drive(service, TIME_TABLE_ID)
        y, m = extract_year_month(uploaded_file)
        my_s, other_s = pdf_reader(uploaded_file, TARGET_STAFF)
        
        final_results = []
        for col in range(1, my_s.shape[1]):
            shift_code = str(my_s.iloc[0, col]).strip()
            if not shift_code or shift_code.lower() == "nan": continue
            target_date = f"{y}/{m}/{col}"
            
            if any(h in shift_code for h in ["休", "有給", "公休"]):
                final_results.append([f"T2_休日", target_date, "", target_date, "", "True", "", "T2"])
            elif "T2" in location_dic:
                shift_cal("T2", target_date, col, shift_code, other_s, location_dic["T2"][0], final_results)
        
        if final_results:
            df_res = pd.DataFrame(final_results, columns=['Subject','Start Date','Start Time','End Date','End Time','All Day Event','Description','Location'])
            st.table(df_res)
            csv = df_res.to_csv(index=False, encoding='utf-8-sig')
            st.download_button("3. CSVを保存", csv, f"shift_{y}_{m}.csv", "text/csv")
