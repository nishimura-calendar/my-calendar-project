import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import pdfplumber
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

def get_gdrive_service(secrets):
    creds = service_account.Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=creds)

def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　]', '', unicodedata.normalize('NFKC', text)).lower()

def extract_year_month_from_text(text):
    if not text: return None, None
    text = unicodedata.normalize('NFKC', text)
    clean_text = re.sub(r'\s+', '', text)
    y_val, m_val = None, None
    month_match = re.search(r'(\d{1,2})月', clean_text)
    if month_match:
        m_val = int(month_match.group(1))
    nums = re.findall(r'\d+', clean_text)
    for n in nums:
        val = int(n)
        if len(n) == 4:
            y_val = val
        elif len(n) == 2:
            if m_val is None or (val != m_val):
                if y_val is None:
                    y_val = 2000 + val
    return y_val, m_val

def extract_max_day_from_pdf(pdf_stream):
    try:
        pdf_stream.seek(0)
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            if not text: return None
            days = re.findall(r'\b(28|29|30|31)\b', text)
            if days: return int(max(days))
    except: pass
    return None

def extract_first_weekday_from_pdf(pdf_stream):
    try:
        pdf_stream.seek(0)
        with pdfplumber.open(pdf_stream) as pdf:
            text = pdf.pages[0].extract_text()
            if not text: return None
            match = re.search(r'\b1\s*[\(\（]([月火水木金土日])[\)\）]', text)
            if match: return match.group(1)
    except: pass
    return None

def time_schedule_from_drive(service, file_id):
    """
    Google Driveからスプレッドシートを読み込む。
    【再構築】B列(index 1)以降をスキャンし、時間データ(数値)の開始と終了を動的に特定する。
    """
    try:
        request = service.files().get_media(fileId=file_id)
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str).fillna('')
        
        # A列に値がある行を「勤務地（T1等）」の開始行とする
        location_rows = full_df[full_df.iloc[:, 0].str.strip() != ''].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            location_name = temp_range.iloc[0, 0].strip()
            
            # --- 2列目(B列)から右に向かって「時間列」の範囲をスキャン ---
            header_row = temp_range.iloc[0]
            start_col = None
            last_col = None
            
            for c in range(1, len(header_row)):
                val = str(header_row[c]).strip()
                # 数値（6.25など）が含まれているか判定
                is_numeric_time = any(char.isdigit() for char in val) and '.' in val
                
                if is_numeric_time:
                    if start_col is None:
                        start_col = c
                    last_col = c
                else:
                    # 時間データが途切れた（"出勤"などの文字列になった）ら終了
                    if start_col is not None:
                        break
            
            if start_col is not None and last_col is not None:
                # [A列(0), B列(1), C列(2), 指定した時間範囲] を抽出
                # B, C列はシフト情報のために常に含める
                base_cols = [0, 1, 2]
                time_cols = list(range(start_col, last_col + 1))
                # 重複を避けて統合
                all_cols = sorted(list(set(base_cols + time_cols)))
                
                final_block = temp_range.iloc[:, all_cols].copy().reset_index(drop=True)
                
                # 時間行の正規化 (6.25 -> 6:15)
                # final_block上での時間列のインデックスを特定（base_colsの数に依存）
                for c in range(len(all_cols)):
                    orig_col_idx = all_cols[c]
                    if orig_col_idx >= start_col:
                        v = final_block.iloc[0, c]
                        try:
                            fv = float(v)
                            h = int(fv)
                            m = int(round((fv - h) * 60))
                            final_block.iloc[0, c] = f"{h}:{m:02d}"
                        except: pass
                
                location_data_dic[location_name] = final_block
        
        return location_data_dic
    except Exception as e:
        raise Exception(f"時程表スキャンエラー: {str(e)}")

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    観察用シンプル版。t_col-1を使用せず、自分自身の状態変化のみを捉える。
    """
    num_cols = time_schedule.shape[1]
    # B列（インデックス1）にシフトコードが入っている前提
    match_rows = time_schedule[time_schedule.iloc[:, 1].astype(str) == shift_info]
    
    if not match_rows.empty:
        # 終日予定としてシフトを登録
        final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "解析中...", key])
        
        my_task_row = match_rows.iloc[0]
        prev_val = ""
        # 最初の3列(A,B,C)を飛ばして時間データからループ
        for t_col in range(3, num_cols):
            current_val = str(my_task_row[t_col]).strip()
            time_header = str(time_schedule.iloc[0, t_col]).strip()
            
            if current_val != prev_val:
                if current_val == "":
                    # 予定終了
                    if final_rows and final_rows[-1][5] == "False":
                        final_rows[-1][4] = time_header
                        final_rows[-1][0] += " (終了)"
                else:
                    # 予定開始
                    subject = f"【{current_val}】"
                    final_rows.append([subject, target_date, time_header, target_date, "", "False", "自動抽出", key])
            prev_val = current_val

def pdf_reader(pdf_stream, target_staff):
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    # camelot用のテンポラリファイル作成
    with open("temp.pdf", "wb") as f:
        f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except:
        return {}
    
    table_dictionary = {}
    for table in tables:
        df = table.df
        if not df.empty:
            # 勤務地の特定
            header_text = str(df.iloc[0, 0]).splitlines()
            work_place = header_text[len(header_text)//2] if header_text else "Unknown"
            
            # ターゲットスタッフの検索
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matched_indices = df.index[search_col == clean_target].tolist()
            
            if matched_indices:
                idx = matched_indices[0]
                # 自分のシフト（2行分）と他人のシフトを分離
                my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily, others]
                
    return table_dictionary

def data_integration(pdf_dic, time_dic):
    integrated = {}
    for pk, pv in pdf_dic.items():
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match:
            integrated[match] = pv + [time_dic[match]]
    return integrated, []

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        for place_key, data_list in integrated_dic.items():
            my_row, others, time_sched = data_list[0], data_list[1], data_list[2]
            # PDF側の日付列(day+1)の範囲チェック
            if day + 1 >= my_row.shape[1]:
                continue
            val = str(my_row.iloc[0, day + 1])
            if not val or val.strip() == "" or val.lower() == 'nan':
                continue
            
            # 複数シフト（カンマ区切り等）に対応
            shifts = [s.strip() for s in re.split(r'[,、\s\n]+', val) if s.strip()]
            for s_info in shifts:
                shift_cal(place_key, target_date_str, day + 1, s_info, my_row, others, time_sched, all_final_rows)
    return all_final_rows
