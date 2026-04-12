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
    """Google Driveから時程表を読み込み、考察2.pyのロジックでクレンジングする"""
    try:
        # スプレッドシートをExcel形式でエクスポート
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
        
        # 全シートを読み込み
        sheets_dict = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
        processed_sheets = {}

        for sheet_name, full_df in sheets_dict.items():
            # --- 【考察2.pyより引用】列の境界（文字列が現れる列）を自動判定 ---
            col_limit = len(full_df.columns)
            # 3列目(Index 2)以降をループし、数値に変換できない文字列が出たらそこを境界とする
            # PDFデータとの整合性を考え、Index 2 からチェック
            for i in range(2, len(full_df.columns)):
                val = full_df.iloc[0, i]
                if pd.isna(val): continue
                try:
                    float(val)
                except (ValueError, TypeError):
                    col_limit = i
                    break

            # 勤務地(ブロック)の特定: 0列目に値がある行を開始行とする
            location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
            
            if not location_rows:
                # 0列目に何もなければ、シート名自体をキーにして全体を保持
                df_part = full_df.iloc[:, 0:col_limit].copy().reset_index(drop=True)
                processed_sheets[sheet_name] = clean_time_header(df_part)
            else:
                for i, start_row in enumerate(location_rows):
                    end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
                    location_name = str(full_df.iloc[start_row, 0]).strip()
                    
                    df_part = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True)
                    processed_sheets[location_name] = clean_time_header(df_part)

        return processed_sheets
    except Exception as e:
        print(f"Error loading Google Sheet: {e}")
        return None

def clean_time_header(df):
    """【考察2.pyより引用】時間行の数値を時刻文字列に変換"""
    df = df.astype(object) # キャストして警告防止
    for col in range(2, df.shape[1]):
        val = df.iloc[0, col]
        try:
            num_val = float(val)
            if 0 < num_val < 1: # Excel時刻シリアル値
                ts = int(num_val * 24 * 3600)
                df.iloc[0, col] = f"{ts // 3600:02d}:{(ts % 3600) // 60:02d}"
            elif num_val >= 1: # 整数（7, 8など）
                df.iloc[0, col] = f"{int(num_val):02d}:00"
        except (ValueError, TypeError):
            pass
    return df

def normalize_for_match(text):
    if not isinstance(text, str): return ""
    return unicodedata.normalize('NFKC', re.sub(r'\s+', '', text)).strip().lower()

def pdf_reader(file_stream, target_staff):
    pdf_data = {}
    target_norm = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue
            df = pd.DataFrame(table)
            for i, row in df.iterrows():
                # 本人名が含まれる行を特定
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
        pdf_loc = normalize_for_match(loc_key)
        matched_sheet = None
        
        for sn in sheet_names:
            sn_norm = normalize_for_match(sn)
            if sn_norm in pdf_loc or pdf_loc in sn_norm:
                matched_sheet = sn
                break
        
        if matched_sheet:
            logs.append(f"✅ マッチ: PDF『{loc_key}』 -> 時程表『{matched_sheet}』")
            idx = pdf_dic[loc_key + "_target_row_idx"]
            integrated[matched_sheet] = [pdf_df.iloc[[idx], :], pdf_df.drop(idx), time_dic[matched_sheet]]
        else:
            logs.append(f"❌ 不一致: PDF『{loc_key}』に対応するシートが時程表にありません。")
            
    return integrated, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    # 終日イベント
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # 時程表（2列目=Index 1）からシフト記号(B, A等)を検索
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return

    prev_val = ""
    # 時程表の3列目(Index 2)から時刻軸データが始まっている前提
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""

        if current_val != prev_val:
            if current_val != "":
                # 交代相手の特定
                mask_curr = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                codes = time_schedule.loc[mask_curr, time_schedule.columns[1]].tolist()
                
                # PDF全体からその時間帯に同じコードを持つ人を検索
                names_list = []
                for code in codes:
                    matched_names = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(str(code))].iloc[:, 0].tolist()
                    names_list.extend([n.split('\n')[0] for n in matched_names if n])
                
                unique_names = "・".join(list(set(names_list)))
                subj = f"【{current_val}】from {unique_names}" if unique_names else f"【{current_val}】"
                final_rows.append([subj, target_date, time_schedule.iloc[0, t_col], target_date, "", "False", "", key])
            else:
                # 終了時刻のセット
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = time_schedule.iloc[0, t_col]
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        # PDFの3列目(Index 2)が1日の場合
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
