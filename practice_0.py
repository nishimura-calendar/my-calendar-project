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
    考察2.pyのロジックに基づき、列境界の自動判定と勤務地ごとの分割を行う。
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
        
        # エンジンを openpyxl に指定して読み込み
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
        
        # --- 列の境界判定 (考察2.pyの最新ロジック) ---
        # 3列目(Index 2 or 3)からループ。数値(時刻)以外の文字列が出たらそこまで。
        col_limit = len(full_df.columns)
        # 時刻データが始まる3列目(Index 3)から走査
        for i in range(3, len(full_df.columns)):
            val = full_df.iloc[0, i]
            if pd.isna(val): continue
            try:
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # --- 勤務地行の特定 ---
        # 0列目に値がある行を特定（T1, T2など）
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        
        processed_sheets = {}
        if not location_rows:
            # 勤務地行が見つからない場合は全体を一つのデータとして扱う
            df_part = full_df.iloc[:, 0:col_limit].copy().reset_index(drop=True)
            processed_sheets["Default"] = clean_time_header(df_part)
        else:
            for i, start_row in enumerate(location_rows):
                end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
                location_name = str(full_df.iloc[start_row, 0]).strip()
                
                # 指定された列範囲（col_limit）で抽出
                df_part = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True)
                processed_sheets[location_name] = clean_time_header(df_part)

        return processed_sheets
    except Exception as e:
        print(f"Error loading Google Sheet: {e}")
        return None

def clean_time_header(df):
    """
    1行目の時刻インデックス（数値/シリアル値）を HH:MM 形式に変換する。
    """
    df = df.astype(object)
    # 時程表の構成に合わせて3列目(Index 3)から変換
    for col in range(3, df.shape[1]):
        val = df.iloc[0, col]
        try:
            num_val = float(val)
            if 0 < num_val < 1: # シリアル値
                ts = int(num_val * 24 * 3600 + 0.5)
                df.iloc[0, col] = f"{ts // 3600:02d}:{(ts % 3600) // 60:02d}"
            elif num_val >= 1: # 整数（6.25など）
                total_minutes = int(num_val * 60 + 0.5)
                df.iloc[0, col] = f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
        except:
            pass
    return df

def normalize_for_match(text):
    """比較用の文字列正規化"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[\(（].*?[\)）]', '', text) 
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'(株式会社|営業所|支店|店舗|ターミナル)', '', text)
    return text.strip().lower()

def pdf_reader(file_stream, target_staff):
    pdf_data = {}
    target_norm = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue
            df = pd.DataFrame(table)
            for i, row in df.iterrows():
                if target_norm in normalize_for_match(str(row[0])):
                    location = str(row[1]) if len(row) > 1 else "Unknown"
                    pdf_data[location] = df.copy()
                    pdf_data[location + "_target_row_idx"] = i 
    return pdf_data

def data_integration(pdf_dic, time_dic):
    integrated = {}
    logs = []
    sheet_names = list(time_dic.keys())
    
    for loc_key, pdf_df in pdf_dic.items():
        if "_target_row_idx" in loc_key: continue
        
        pdf_loc_raw = loc_key
        pdf_loc_norm = normalize_for_match(loc_key)
        matched_sheet = None
        
        for sn in sheet_names:
            sn_norm = normalize_for_match(sn)
            if sn_norm and pdf_loc_norm and (sn_norm in pdf_loc_norm or pdf_loc_norm in sn_norm):
                matched_sheet = sn
                break
        
        if matched_sheet:
            logs.append(f"✅ マッチング成功: PDF『{pdf_loc_raw}』 -> 時程表『{matched_sheet}』")
            idx = pdf_dic[loc_key + "_target_row_idx"]
            integrated[matched_sheet] = [pdf_df.iloc[[idx], :], pdf_df.drop(idx), time_dic[matched_sheet]]
        else:
            logs.append(f"❌ マッチング失敗: PDF内の『{pdf_loc_raw}』に対応する時程表データがありません。")
            logs.append(f"   (正規化後: PDF={pdf_loc_norm} / 時程表={', '.join([normalize_for_match(s) for s in sheet_names])})")
            
    return integrated, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    # 終日予定としてシフト記号を登録
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 2列目(Index 1)からシフト記号を探す
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return

    prev_val = ""
    # 時程表の時刻軸はIndex 3から始まる
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
                final_rows.append([subj, target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", key])
            else:
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        # PDFの1日はIndex 2から始まる想定
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
