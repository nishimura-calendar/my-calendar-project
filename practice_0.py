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

def time_schedule_from_drive(service, file_id):
    """
    Google Driveからスプレッドシートを読み込む。
    【再構築版】幅方向の整合性を重視し、列不足によるIndexErrorを防ぐ。
    """
    try:
        request = service.files().get_media(fileId=file_id)
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        
        # スプレッドシートの場合はExcel形式でエクスポート
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        
        # dtype=str で読み込み、すべてのセルを文字列として扱う
        # header=None にして1行目（時間行）もデータとして保持
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str)
        full_df = full_df.fillna('') # NaNを空文字に統一
        
        # --- 幅方向のチェック ---
        # A列(iloc[:, 0])に勤務地名が入っている行を起点とする
        location_rows = full_df[full_df.iloc[:, 0].str.strip() != ''].index.tolist()
        
        location_data_dic = {}
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            
            # 各勤務地ブロックを切り出し
            temp_range = full_df.iloc[start_row:end_row, :].copy().reset_index(drop=True)
            location_name = temp_range.iloc[0, 0].strip()
            
            # 【重要】時間行（ブロックの1行目）のシリアル値を時刻文字列に変換
            # D列（インデックス3）以降が時間データという前提で処理
            for c in range(3, len(temp_range.columns)):
                val = temp_range.iloc[0, c]
                if val and val.replace('.', '', 1).isdigit():
                    try:
                        fv = float(val)
                        if fv < 1: # シリアル値（0.25など）の場合
                            h = int(fv * 24)
                            m = int(round((fv * 24 - h) * 60))
                            temp_range.iloc[0, c] = f"{h}:{m:02d}"
                        else: # 既に数値（6.25など）の場合
                            h = int(fv)
                            m = int(round((fv - h) * 60))
                            temp_range.iloc[0, c] = f"{h}:{m:02d}"
                    except:
                        pass
            
            location_data_dic[location_name] = temp_range
            
        return location_data_dic
    except Exception as e:
        # どこで止まったか特定しやすくするためエラーを再送
        raise Exception(f"時程表の構築中にエラーが発生しました: {str(e)}")

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """
    【観察用】t_col-1を使用しないシンプル版
    """
    # 読み込んだ time_schedule の形状を確認
    num_rows, num_cols = time_schedule.shape
    
    # 1. シフトコード自体の終日予定
    # B列（インデックス1）がシフトコード列という前提
    if num_cols > 1:
        match_rows = time_schedule[time_schedule.iloc[:, 1].astype(str) == shift_info]
        if not match_rows.empty:
            final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "観察用：シフト一致", key])
            
            # 自分の予定行（最初の1行）
            my_task_row = match_rows.iloc[0]
            prev_val = ""
            
            # 時間のデータはD列（インデックス3）から開始
            # rangeの終端を実際の列数(num_cols)に合わせることで安全にループ
            for t_col in range(3, num_cols):
                current_val = str(my_task_row[t_col]).strip()
                time_header = str(time_schedule.iloc[0, t_col]).strip()
                
                if current_val != prev_val:
                    if current_val == "":
                        # 終了処理
                        if final_rows and final_rows[-1][5] == "False":
                            final_rows[-1][4] = time_header
                            final_rows[-1][0] += " (終了)"
                    else:
                        # 開始処理
                        subject = f"【{current_val}】"
                        final_rows.append([subject, target_date, time_header, target_date, "", "False", "観察用：詳細", key])
                
                prev_val = current_val

def pdf_reader(pdf_stream, target_staff):
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except: return {}
    table_dictionary = {}
    for table in tables:
        df = table.df
        if not df.empty:
            header = str(df.iloc[0, 0]).splitlines()
            work_place = header[len(header)//2] if header else "Unknown"
            search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
            matched_indices = df.index[search_col == clean_target].tolist()
            if matched_indices:
                idx = matched_indices[0]
                my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily, others]
    return table_dictionary

def data_integration(pdf_dic, time_dic):
    integrated = {}
    for pk, pv in pdf_dic.items():
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match: integrated[match] = pv + [time_dic[match]]
    return integrated, []

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        for place_key, data_list in integrated_dic.items():
            my_row, others, time_sched = data_list[0], data_list[1], data_list[2]
            # PDF側の日付列チェック
            if day + 1 >= my_row.shape[1]: continue
            val = str(my_row.iloc[0, day + 1])
            if not val or val.strip() == "" or val.lower() == 'nan': continue
            for item in [i.strip() for i in re.split(r'[,、\s\n]+', val) if i.strip()]:
                shift_cal(place_key, target_date_str, day + 1, item, my_row, others, time_sched, all_final_rows)
    return all_final_rows
