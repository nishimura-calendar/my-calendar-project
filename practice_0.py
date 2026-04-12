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
    時程表（Excel形式）からブロックを抽出。
    ダウンロード時に.xlsxになる仕様に合わせ、バイナリとして取得し、
    小数点の時間（6.25等）を HH:MM に変換する。
    """
    try:
        # ファイルのメタデータを取得（MIMEタイプを確認）
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType')
        
        # 1. ダウンロード処理
        if mime_type == 'application/vnd.google-apps.spreadsheet':
            # スプレッドシート形式の場合はExcelに変換してエクスポート
            request = service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            # 既にExcel(.xlsx)等の場合はそのまま取得
            request = service.files().get_media(fileId=file_id)
            
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        
        # 2. Excelとして読み込み
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0)
        
        # --- 境界判定と時間変換 ---
        col_limit = len(full_df.columns)
        # 数値が入っている列の限界を調べる
        for i in range(3, len(full_df.columns)):
            val = full_df.iloc[0, i]
            if pd.isna(val): continue
            try:
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # 小数点形式の時間を HH:MM 形式に変換
        for i in range(3, col_limit):
            val = full_df.iloc[0, i]
            if pd.notna(val) and isinstance(val, (int, float)):
                hours = int(val)
                minutes = int(round((val - hours) * 60))
                full_df.iloc[0, i] = f"{hours}:{minutes:02d}"

        # 3. 勤務地ごとのブロック分割 (A列に名前がある場所を区切りとする)
        location_indices = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        processed_data_parts = {}
        
        if not location_indices:
            processed_data_parts["Unknown"] = full_df.iloc[:, 0:col_limit].copy().fillna('')
        else:
            for i, start_row in enumerate(location_indices):
                end_row = location_indices[i+1] if i+1 < len(location_indices) else len(full_df)
                location_name = str(full_df.iloc[start_row, 0]).strip()
                df_part = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True)
                processed_data_parts[location_name] = df_part.fillna('')

        return processed_data_parts
    except Exception as e:
        raise e

def normalize_for_match(text):
    """比較用の正規化"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[\(（].*?[\)）]', '', text) 
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'(株式会社|営業所|支店|店舗|ターミナル|旅客|免税店)', '', text)
    return text.strip().lower()

def pdf_reader(file_stream, target_staff):
    """PDFからスタッフ行を抽出"""
    pdf_data = {}
    target_norm = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue
            df = pd.DataFrame(table)
            for i, row in df.iterrows():
                row_str = "".join([str(x) for x in row if x])
                if target_norm in normalize_for_match(row_str):
                    location = str(row[1]).strip() if len(row) > 1 else "Unknown"
                    pdf_data[location] = df.copy()
                    pdf_data[location + "_target_row_idx"] = i 
    return pdf_data

def data_integration(pdf_dic, time_dic):
    """PDFの場所と時程表のブロックを紐付ける"""
    integrated = {}
    logs = []
    location_keys = list(time_dic.keys())
    for pdf_loc_raw, pdf_df in pdf_dic.items():
        if "_target_row_idx" in pdf_loc_raw: continue
        pdf_loc_norm = normalize_for_match(pdf_loc_raw)
        matched_key = None
        for lk in location_keys:
            if pdf_loc_norm and (pdf_loc_norm in normalize_for_match(lk)):
                matched_key = lk
                break
        if not matched_key and pdf_loc_norm == "c":
            for lk in location_keys:
                if "T2" in lk.upper():
                    matched_key = lk
                    break
        if matched_key:
            logs.append({"PDF勤務地": pdf_loc_raw, "時程表側": matched_key, "状態": "✅ 完了"})
            idx = pdf_dic[pdf_loc_raw + "_target_row_idx"]
            integrated[matched_key] = [pdf_df.iloc[[idx], :], pdf_df.drop(idx), time_dic[matched_key]]
        else:
            logs.append({"PDF勤務地": pdf_loc_raw, "時程表側": "未検出", "状態": "❌ 失敗"})
    return integrated, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """詳細スケジュールの生成ロジック"""
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return
    
    prev_val = ""
    for t_col in range(3, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""
        
        if current_val != prev_val:
            if current_val != "":
                mask_curr = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                codes = time_schedule.loc[mask_curr, time_schedule.columns[1]].tolist()
                
                names_list = []
                for code in codes:
                    if not str(code).strip(): continue
                    matched_names = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(str(code))].iloc[:, 0].tolist()
                    names_list.extend([n.split('\n')[0].strip() for n in matched_names if n])
                
                unique_names = "・".join(list(set(names_list)))
                subj = f"【{current_val}】from {unique_names}" if unique_names else f"【{current_val}】"
                start_time = str(time_schedule.iloc[0, t_col])
                final_rows.append([subj, target_date, start_time, target_date, "", "False", "", key])
            else:
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        current_col = day + 1 
        for place_key, data in integrated_dic.items():
            my_row, others, time_sched = data
            if current_col >= my_row.shape[1]: continue
            val = str(my_row.iloc[0, current_col])
            if not val or val.lower() == 'nan' or val.strip() == "": continue
            items = [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]
            for item in items:
                shift_cal(place_key, target_date_str, current_col, item, my_row, others, time_sched, all_final_rows)
    return all_final_rows
