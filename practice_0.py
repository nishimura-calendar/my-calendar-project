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

def normalize_text(text):
    """比較のためのテキスト正規化"""
    if not text: return ""
    return unicodedata.normalize('NFKC', str(text)).replace(" ", "").replace("　", "").strip()

def extract_year_month_from_pdf(pdf_stream):
    """PDFのテキストから年月情報を抽出"""
    try:
        pdf_stream.seek(0)
        with pdfplumber.open(pdf_stream) as pdf:
            first_page_text = pdf.pages[0].extract_text()
            if not first_page_text: return None, None
            match = re.search(r'(\d{4})\s*[年/]\s*(\d{1,2})\s*月?', first_page_text)
            if match: return int(match.group(1)), int(match.group(2))
    except: pass
    return None, None

def time_schedule_from_drive(service, file_id):
    """スプレッドシートから勤務地ごとの時程表を辞書形式で抽出"""
    try:
        request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request); done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        full_df = pd.read_excel(fh, header=None, engine='openpyxl')
        
        # 0列目に値がある行を勤務地の開始行とみなす
        location_rows = full_df[full_df.iloc[:, 0].notna()].index.tolist()
        location_data_dic = {}
        for i, start_row in enumerate(location_rows):
            end_row = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            location_name = str(full_df.iloc[start_row, 0]).strip()
            temp_range = full_df.iloc[start_row:end_row, :].copy()
            
            # 数値列（時間列）の範囲特定
            current_col_limit = len(temp_range.columns)
            for col_idx in range(2, len(temp_range.columns)):
                val = temp_range.iloc[0, col_idx]
                if pd.isna(val) or val == "": continue
                try: float(val)
                except: current_col_limit = col_idx; break
            
            data_range = temp_range.iloc[:, 0:current_col_limit].copy().reset_index(drop=True)
            # 時間をシリアル値から文字列に変換
            for col in range(1, data_range.shape[1]):
                t_val = data_range.iloc[0, col]
                if isinstance(t_val, (int, float)):
                    h = int(t_val * 24)
                    m = int(round((t_val * 24 - h) * 60))
                    data_range.iloc[0, col] = f"{h}:{m:02d}"
            
            location_data_dic[location_name] = data_range.fillna('')
        return location_data_dic
    except Exception as e: raise e

def pdf_reader(pdf_stream, target_staff):
    """PDFからスタッフ行(2行分)を抽出"""
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
        table_dic = {}
        for table in tables:
            df = table.df.replace(r'^\s*$', None, regex=True).fillna('')
            if df.empty: continue
            
            # 勤務地判定（セル内改行の中央行を取得）
            loc_text = str(df.iloc[0, 0])
            lines = loc_text.splitlines()
            work_place = lines[len(lines)//2] if lines else "不明"
            
            search_col = df.iloc[:, 0].apply(normalize_text)
            matches = df.index[search_col.str.contains(clean_target)].tolist()
            if matches:
                idx = matches[0]
                # 本人2行、その他を分離
                my_daily = df.iloc[idx:idx+2, :].copy().reset_index(drop=True)
                others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
                table_dic[work_place] = [my_daily, others]
        return table_dic
    except: return {}

def data_integration(pdf_dic, time_schedule_dic):
    """勤務地紐付け"""
    integrated = {}; logs = []
    for p_loc, p_vals in pdf_dic.items():
        norm_p = normalize_text(p_loc)
        matched_key = next((k for k in time_schedule_dic.keys() if norm_p in normalize_text(k)), None)
        if matched_key:
            integrated[matched_key] = p_vals + [time_schedule_dic[matched_key]]
            logs.append({"PDF勤務地": p_loc, "時程表側": matched_key, "状態": "OK"})
        else:
            logs.append({"PDF勤務地": p_loc, "時程表側": "---", "状態": "未検出"})
    return integrated, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """具体的スケジュール算出ロジック"""
    # 終日予定
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str).str.strip() == str(shift_info).strip()]
    if my_time_shift.empty: return
    
    prev_val = ""
    for t_col in range(2, time_schedule.shape[1]):
        current_val = str(my_time_shift.iloc[0, t_col])
        if current_val.lower() == 'nan': current_val = ""
        
        if current_val != prev_val:
            if current_val != "":
                # 交代相手の検索
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
    """月間ループ"""
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date = f"{year}/{month:02d}/{day:02d}"
        for key, (my_row, others, time_sched) in integrated_dic.items():
            # 日付列判定 (1列目名前、2列目以降日付)
            target_col = day 
            if target_col >= my_row.shape[1]: continue
            
            cell_val = str(my_row.iloc[0, target_col]).split('\n')
            shift_info = cell_val[0].strip()
            
            if shift_info and not any(x in shift_info for x in ["休", "有休", "nan", " "]):
                shift_cal(key, target_date, target_col, shift_info, my_row, others, time_sched, all_final_rows)
    return all_final_rows
