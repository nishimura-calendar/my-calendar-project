import pandas as pd
import pdfplumber
import unicodedata
import re
import io
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
    指定されたファイルID(xlsx)をダウンロードしてExcelとして読み込む。
    A列:勤務地, B列:巡回区域(シフトコード), C列:ロッカ, D列以降:時間行
    """
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    
    fh.seek(0)
    # Excelとして全シートを読み込み
    all_sheets = pd.read_excel(fh, sheet_name=None, header=None)
    
    time_dic = {}
    for sheet_name, df in all_sheets.items():
        df = df.fillna("")
        
        # 数値の末尾 .0 を除去する関数
        def clean_format(x):
            s = str(x)
            return s[:-2] if s.endswith('.0') else s

        # Pandasバージョン互換性を考慮してmap/applymapを使い分け
        if hasattr(df, 'map'):
            df = df.map(clean_format)
        else:
            df = df.applymap(clean_format)
            
        time_dic[sheet_name] = df
            
    return time_dic

def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': 
        return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s\n]+', '', normalized).strip().upper()

def extract_workplace_from_header(header_text):
    """(0,0)セルの改行数から勤務地を特定するロジック"""
    if not header_text: return "不明な拠点"
    text_str = str(header_text)
    lines = text_str.split('\n')
    num_newlines = text_str.count('\n')
    target_index = num_newlines // 2
    try:
        work_place = lines[target_index].strip() if target_index < len(lines) else lines[-1].strip()
        if not work_place:
            non_empty = [e.strip() for e in lines if e.strip()]
            if len(non_empty) >= 2: work_place = non_empty[1]
            elif non_empty: work_place = non_empty[0]
        return work_place
    except:
        return "解析エラー"

def pdf_reader(file_stream, target_staff):
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty: continue
                
                # A列1行目(0,0)から勤務地を特定
                header_val = df.iloc[0, 0]
                current_workplace = extract_workplace_from_header(header_val)
                
                # スタッフがいるか検索
                search_col = df.iloc[:, 0].apply(normalize_for_match)
                found_indices = [i for i, val in enumerate(search_col) if clean_target in val]
                
                if not found_indices: continue
                
                for idx in found_indices:
                    my_data = df.iloc[[idx]].copy()
                    others_data = df[df.index != idx].copy()
                    key_name = current_workplace
                    cnt = 2
                    while key_name in table_dictionary:
                        key_name = f"{current_workplace}_{cnt}"
                        cnt += 1
                    table_dictionary[key_name] = [my_data.reset_index(drop=True), others_data.reset_index(drop=True)]
    return table_dictionary

def data_integration(pdf_dic, time_schedule_dic):
    integrated_dic = {}
    for place_name, pdf_data in pdf_dic.items():
        norm_place = normalize_for_match(place_name)
        matched_key = None
        for k in time_schedule_dic.keys():
            if normalize_for_match(k) in norm_place or norm_place in normalize_for_match(k):
                matched_key = k
                break
        if matched_key:
            integrated_dic[place_name] = [pdf_data[0], pdf_data[1], time_schedule_dic[matched_key]]
    return integrated_dic

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """基本事項: B列(1)=シフトコード, D列(3)以降=時間行"""
    # 終日予定の追加
    final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    sched_clean = time_schedule.copy()
    # シフトコード(B列)でフィルタリング
    my_time_shift = sched_clean[sched_clean.iloc[:, 1] == shift_info]
    
    if not my_time_shift.empty:
        prev_val = ""
        # D列(index 3)以降が時間軸
        for t_col in range(3, sched_clean.shape[1]):
            current_val = my_time_shift.iloc[0, t_col]
            if current_val != prev_val:
                if current_val != "": 
                    # 交代相手の検索 (打合.pyのロジック)
                    mask_handing_over = (sched_clean.iloc[:, t_col] == prev_val) & (sched_clean.iloc[:, 1] != shift_info)
                    mask_taking_over = (sched_clean.iloc[:, t_col] == current_val) & (sched_clean.iloc[:, 1] != shift_info)
                    
                    handing_over = ""
                    taking_over = ""
                    for i in range(2):
                        mask = mask_handing_over if i == 0 else mask_taking_over
                        search_codes = sched_clean.loc[mask, sched_clean.columns[1]]
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_codes)]
                        names = '・'.join(target_rows.iloc[:, 0].unique().astype(str))
                        if i == 0: handing_over = f"to {names}" if names else ""
                        else: taking_over = f"【{current_val}】from {names}" if names else f"【{current_val}】"
                    
                    # 開始時刻は1行目(index 0)から取得
                    start_time = sched_clean.iloc[0, t_col]
                    final_rows.append([f"{handing_over}=>{taking_over}", target_date, start_time, target_date, "", "False", "", key])
                else:
                    # 終了時刻の設定
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = sched_clean.iloc[0, t_col]
            prev_val = current_val

def process_integrated_data(integrated_dic, target_date_str, current_col):
    all_final_rows = []
    for place_key, data_list in integrated_dic.items():
        my_shift, other_shift, time_sched = data_list
        raw_val = str(my_shift.iloc[0, current_col])
        items = [i.strip() for i in re.split(r'[,、\s\n]+', raw_val) if i.strip()]
        
        # 時程表のB列(コード)と比較
        master_codes = [normalize_for_match(x) for x in time_sched.iloc[:, 1].tolist()]
        
        for item in items:
            if normalize_for_match(item) in master_codes:
                shift_cal(place_key, target_date_str, current_col, item, my_shift, other_shift, time_sched, all_final_rows)
            else:
                # マスターにない場合はそのまま終日イベントとして登録
                all_final_rows.append([item, target_date_str, "", target_date_str, "", "True", "", place_key])
    return all_final_rows
