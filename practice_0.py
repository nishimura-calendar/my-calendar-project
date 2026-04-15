import pandas as pd
import pdfplumber
import camelot
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
    【改良版】時程表（Excel形式）からブロックを抽出。
    勤務地ごとに「列の境界判定」と「時間表記の変換」を独立して行い、
    各場所独自のスケジュール設定に対応する。
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
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        
        # Excelとして読み込み
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0)
        
        # 勤務地名の行（0列目が空でない行）を特定
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            # 次の勤務地までの範囲を特定
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            
            # この勤務地ブロックの全データを一旦取得
            temp_range = full_df.iloc[start_row:end_row, :].copy()

            # --- 【改良ポイント1】この勤務地独自の列境界(col_limit)を判定 ---
            # 0行目（時刻行）を見て、数値でなくなった時点でその場所の列終わりとする
            current_col_limit = len(temp_range.columns)
            for col_idx in range(2, len(temp_range.columns)):
                val = temp_range.iloc[0, col_idx]
                if pd.isna(val) or val == "": continue
                try:
                    float(val)
                except (ValueError, TypeError):
                    current_col_limit = col_idx
                    break
            
            # 判定された境界でデータを切り出し
            data_range = temp_range.iloc[:, 0:current_col_limit].copy().reset_index(drop=True)
            
            # 型エラー防止のため object に変換
            data_range = data_range.astype(object)

            # --- 【改良ポイント2】この勤務地独自の時間表記変換 ---
            # 1列目(インデックス1)から判定された境界までをループ
            for col in range(1, data_range.shape[1]):
                time_val = data_range.iloc[0, col]
                if pd.notna(time_val) and isinstance(time_val, (int, float)):
                    try:
                        hours = int(time_val)
                        minutes = int(round((time_val - hours) * 60))
                        data_range.iloc[0, col] = f"{hours}:{minutes:02d}"
                    except (ValueError, TypeError):
                        continue
            
            # 欠損値を埋めて辞書に保存
            location_data_dic[location_name] = data_range.fillna('')
        
        return location_data_dic
    except Exception as e:
        raise e

def normalize_text(text):
    """テキスト比較用の正規化"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'[\s　]', '', text).lower()

def pdf_reader(pdf_stream, target_staff):
    """PDFから指定スタッフの行とそれ以外のスタッフ行を抽出。"""
    clean_target = normalize_text(target_staff)
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except Exception:
        return {}

    table_dictionary = {}
    for table in tables:
        df = table.df
        if not df.empty:
            text = str(df.iloc[0, 0])
            lines = text.splitlines()
            target_idx = text.count('\n') // 2
            work_place = lines[target_idx] if target_idx < len(lines) else (lines[-1] if lines else "Unknown")
            
            df = df.fillna('')
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matched_indices = df.index[search_col == clean_target].tolist()
            
            if matched_indices:
                idx = matched_indices[0]
                my_daily_shift = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                other_daily_shift = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily_shift, other_daily_shift]
                
    return table_dictionary

def data_integration(pdf_dic, time_schedule_dic):
    """勤務地名による紐付け"""
    integrated_dic = {}
    logs = []
    
    for pdf_loc, pdf_vals in pdf_dic.items():
        norm_pdf_loc = normalize_text(pdf_loc)
        matched_key = None
        for t_key in time_schedule_dic.keys():
            if norm_pdf_loc in normalize_text(t_key):
                matched_key = t_key
                break
        
        if matched_key:
            integrated_dic[matched_key] = pdf_vals + [time_schedule_dic[matched_key]]
            logs.append({"PDF勤務地": pdf_loc, "時程表側": matched_key, "状態": "OK"})
        else:
            logs.append({"PDF勤務地": pdf_loc, "時程表側": "---", "状態": "未検出"})
            
    return integrated_dic, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """詳細スケジュールの算定"""
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return

    prev_val = ""
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""

        if current_val != prev_val:
            if current_val != "":
                mask = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                codes = time_schedule.loc[mask, time_schedule.columns[1]].tolist()
                
                names = []
                for code in codes:
                    if not str(code).strip(): continue
                    matches = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(str(code))]
                    names.extend([n.split('\n')[0].strip() for n in matches.iloc[:, 0].tolist() if n])
                
                u_names = "・".join(list(set(names)))
                subj = f"【{current_val}】from {u_names}" if u_names else f"【{current_val}】"
                start_t = str(time_schedule.iloc[0, t_col])
                final_rows.append([subj, target_date, start_t, target_date, "", "False", "", key])
            else:
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    """1ヶ月分ループ"""
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        current_col = day + 1 
        for place_key, (my_row, others, time_sched) in integrated_dic.items():
            if current_col >= my_row.shape[1]: continue
            val = str(my_row.iloc[0, current_col])
            if not val or val.strip() == "" or val.lower() == 'nan': continue
            
            items = [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]
            for item in items:
                shift_cal(place_key, target_date_str, current_col, item, my_row, others, time_sched, all_final_rows)
    return all_final_rows
