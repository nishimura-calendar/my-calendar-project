import pandas as pd
import pdfplumber
import unicodedata
import re
import io
import calendar
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

def get_gdrive_service(secrets):
    """Google Drive APIへのサービスオブジェクトを作成"""
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def time_schedule_from_drive(service, file_id):
    """
    Google Driveから時程表を読み込み、時刻軸をクレンジングする。
    1列目=勤務地, 2列目=シフト記号, 3列目=ロッカー, 4列目(Index 3)以降=時間行の構造に対応。
    """
    try:
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType')

        if mime_type == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            request = service.files().get_media(fileId=file_id)
            
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        # ヘッダーなしで読み込み
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
        
        # --- 1. 列の境界（文字列が現れる列）を自動判定 ---
        # 4列目(Index 3)以降をループし、数値以外の文字列(「出勤」など)が出たらそこまで。
        col_limit = len(full_df.columns)
        for i in range(3, len(full_df.columns)):
            val = full_df.iloc[0, i]
            if pd.isna(val): continue
            try:
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # --- 2. 勤務地（T1, T2など）の開始行を特定 ---
        # 0列目に値があり、1〜3列目が空白である行を勤務地の区切りとする
        location_rows = []
        for idx, row in full_df.iterrows():
            if pd.notna(row[0]) and pd.isna(row[1]) and pd.isna(row[2]) and pd.isna(row[3]):
                location_rows.append(idx)
        
        processed_data_parts = {}
        if not location_rows:
            df_part = full_df.iloc[:, 0:col_limit].copy().reset_index(drop=True)
            processed_data_parts["Unknown"] = clean_time_header(df_part)
        else:
            for i, start_row in enumerate(location_rows):
                end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
                location_name = str(full_df.iloc[start_row, 0]).strip()
                df_part = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True)
                processed_data_parts[location_name] = clean_time_header(df_part)

        return processed_data_parts
    except Exception as e:
        print(f"Error loading Google Sheet: {e}")
        return None

def clean_time_header(df):
    """
    1行目の時刻（6.25, 6.5 等）を HH:MM 形式に確実に変換する。
    """
    df = df.astype(object)
    # 4列目(Index 3)以降が時間軸
    for col in range(3, df.shape[1]):
        val = df.iloc[0, col]
        try:
            num_val = float(val)
            # 24時間表記の数値（例: 6.25 -> 6:15）として計算
            hours = int(num_val)
            minutes = int(round((num_val - hours) * 60))
            # 24時を超える場合（25.0 -> 01:00）のケア
            df.iloc[0, col] = f"{hours % 24:02d}:{minutes:02d}"
        except (ValueError, TypeError):
            pass
    return df

def normalize_for_match(text):
    """比較用の文字列正規化"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[\(（].*?[\)）]', '', text) 
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'(株式会社|営業所|支店|店舗|ターミナル|旅客)', '', text)
    return text.strip().lower()

def pdf_reader(file_stream, target_staff):
    """PDFから指定スタッフのシフトと勤務地を抽出"""
    pdf_data = {}
    target_norm = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue
            df = pd.DataFrame(table)
            for i, row in df.iterrows():
                if target_norm in normalize_for_match(str(row[0])):
                    location = str(row[1]).strip() if len(row) > 1 else "Unknown"
                    pdf_data[location] = df.copy()
                    pdf_data[location + "_target_row_idx"] = i 
    return pdf_data

def data_integration(pdf_dic, time_dic):
    """PDFと時程表の勤務地を紐付け"""
    integrated = {}
    logs = []
    location_keys = list(time_dic.keys())
    
    for pdf_loc_raw, pdf_df in pdf_dic.items():
        if "_target_row_idx" in pdf_loc_raw: continue
        
        pdf_loc_norm = normalize_for_match(pdf_loc_raw)
        matched_key = None
        
        for lk in location_keys:
            lk_norm = normalize_for_match(lk)
            if lk_norm and pdf_loc_norm and (lk_norm in pdf_loc_norm or pdf_loc_norm in lk_norm):
                matched_key = lk
                break
        
        if matched_key:
            logs.append(f"✅ 紐付け成功: PDF『{pdf_loc_raw}』 -> 時程表内『{matched_key}』")
            idx = pdf_dic[pdf_loc_raw + "_target_row_idx"]
            integrated[matched_key] = [pdf_df.iloc[[idx], :], pdf_df.drop(idx), time_dic[matched_key]]
        else:
            logs.append(f"❌ 紐付け失敗: PDFの『{pdf_loc_raw}』が時程表の勤務地行に見つかりません。")
            logs.append(f"   (候補: {', '.join(location_keys)})")
            
    return integrated, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """個別の時間詳細を算出"""
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 2列目(Index 1)のシフト記号で検索
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return

    prev_val = ""
    # 4列目(Index 3)以降を走査
    for t_col in range(3, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""

        if current_val != prev_val:
            if current_val != "":
                # 交代相手の特定
                mask_curr = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                codes = time_schedule.loc[mask_curr, time_schedule.columns[1]].tolist()
                
                names_list = []
                for code in codes:
                    if not str(code).strip(): continue
                    matched_names = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(str(code))].iloc[:, 0].tolist()
                    names_list.extend([n.split('\n')[0].strip() for n in matched_names if n])
                
                unique_names = "・".join(list(set(names_list)))
                subj = f"【{current_val}】from {unique_names}" if unique_names else f"【{current_val}】"
                # 開始時刻をセット
                final_rows.append([subj, target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", key])
            else:
                # 予定の終了時刻をセット
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        current_col = day + 1 
        
        for place_key, data in integrated_dic.items():
            my_shift, other_shift, time_sched = data
            if current_col >= my_shift.shape[1]: continue
            
            val = str(my_shift.iloc[0, current_col])
            if not val or val.lower() == 'nan' or val.strip() == "": continue
            
            items = [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]
            for item in items:
                shift_cal(place_key, target_date_str, current_col, item, my_shift, other_shift, time_sched, all_final_rows)
    return all_final_rows
