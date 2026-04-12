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
    Google Driveから時程表を読み込み。
    0列目に「T1」「T2」がある行をブロックの開始点として動的に抽出。
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
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
        
        # --- 1. 列の境界判定 ---
        # 4列目(Index 3)以降が時刻軸。数値でなくなった列を終端とする。
        col_limit = len(full_df.columns)
        for i in range(3, len(full_df.columns)):
            val = full_df.iloc[0, i]
            if pd.isna(val): continue
            try:
                float(val)
            except (ValueError, TypeError):
                col_limit = i
                break

        # --- 2. 勤務地ブロックの抽出 ---
        # 0列目に T1, T2 等の値が入っている行のインデックスを取得
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        
        processed_data_parts = {}
        if not location_rows:
            processed_data_parts["Unknown"] = full_df.iloc[:, 0:col_limit].copy().fillna('')
        else:
            for i, start_row in enumerate(location_rows):
                end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
                location_name = str(full_df.iloc[start_row, 0]).strip()
                # 数値変換ロジックを削除し、そのまま抽出
                df_part = full_df.iloc[start_row:end_row, 0:col_limit].copy().reset_index(drop=True)
                processed_data_parts[location_name] = df_part.fillna('')

        return processed_data_parts
    except Exception as e:
        print(f"Error loading Google Sheet: {e}")
        return None

def normalize_for_match(text):
    """氏名・勤務地の比較用正規化（スペース・ノイズ除去）"""
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[\(（].*?[\)）]', '', text) 
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'(株式会社|営業所|支店|店舗|ターミナル|旅客|免税店)', '', text)
    return text.strip().lower()

def pdf_reader(file_stream, target_staff):
    """
    PDF解析: 指定された target_staff（西村文宏など）を全ページから検索し、
    その行を抽出。1列目(Index 1)を勤務地キーとして取得。
    """
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
                    # 1列目: 勤務地 (例: 'C')
                    location = str(row[1]).strip() if len(row) > 1 else "Unknown"
                    pdf_data[location] = df.copy()
                    pdf_data[location + "_target_row_idx"] = i 
    return pdf_data

def data_integration(pdf_dic, time_dic):
    """PDF上の勤務地略称と、時程表のブロック名を紐付ける。'C' -> 'T2' 等の救済込。"""
    integrated = {}
    logs = []
    location_keys = list(time_dic.keys())
    
    for pdf_loc_raw, pdf_df in pdf_dic.items():
        if "_target_row_idx" in pdf_loc_raw: continue
        
        pdf_loc_norm = normalize_for_match(pdf_loc_raw)
        matched_key = None
        
        # 1. 部分一致マッチング
        for lk in location_keys:
            if pdf_loc_norm in normalize_for_match(lk):
                matched_key = lk
                break
        
        # 2. 救済: PDFが 'C' 一文字などの場合、時程表の 'T2' に紐付ける
        if not matched_key and pdf_loc_norm == "c":
            for lk in location_keys:
                if "T2" in lk.upper():
                    matched_key = lk
                    break

        if matched_key:
            logs.append(f"✅ 紐付け成功: PDF『{pdf_loc_raw}』 -> 時程表内『{matched_key}』")
            idx = pdf_dic[pdf_loc_raw + "_target_row_idx"]
            # integrated = {勤務地名: [自分の行, 他人の表, 時程表]}
            integrated[matched_key] = [pdf_df.iloc[[idx], :], pdf_df.drop(idx), time_dic[matched_key]]
        else:
            logs.append(f"❌ 紐付け失敗: PDFの『{pdf_loc_raw}』に対応するマスタが時程表にありません。")
            
    return integrated, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    時程表に基づき詳細予定を算出。
    ※時刻変換をせず、時程表の0行目の値をそのまま時刻として扱う。
    """
    # 終日予定
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    # シフト記号(1列目/Index 1)が一致する行を抽出
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return

    prev_val = ""
    # 時刻軸（4列目/Index 3 以降）
    for t_col in range(3, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""

        if current_val != prev_val:
            if current_val != "":
                # 交代相手の検索
                mask_curr = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                codes = time_schedule.loc[mask_curr, time_schedule.columns[1]].tolist()
                
                names_list = []
                for code in codes:
                    if not str(code).strip(): continue
                    matched_names = other_staff_shift[other_staff_shift.iloc[:, col].astype(str).str.contains(str(code))].iloc[:, 0].tolist()
                    names_list.extend([n.split('\n')[0].strip() for n in matched_names if n])
                
                unique_names = "・".join(list(set(names_list)))
                subj = f"【{current_val}】from {unique_names}" if unique_names else f"【{current_val}】"
                
                # 開始時刻: 時程表の0行目の値を直接使用
                start_time = str(time_schedule.iloc[0, t_col])
                final_rows.append([subj, target_date, start_time, target_date, "", "False", "", key])
            else:
                # 終了時刻のセット
                if final_rows and final_rows[-1][5] == "False":
                    final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    """月間全日程の行を生成"""
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        current_col = day + 1 # PDFの1日は Index 2
        
        for place_key, data in integrated_dic.items():
            my_shift_row, other_staff_df, time_sched = data
            if current_col >= my_shift_row.shape[1]: continue
            
            val = str(my_shift_row.iloc[0, current_col])
            if not val or val.lower() == 'nan' or val.strip() == "": continue
            
            items = [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]
            for item in items:
                shift_cal(place_key, target_date_str, current_col, item, my_shift_row, other_staff_df, time_sched, all_final_rows)
    return all_final_rows
