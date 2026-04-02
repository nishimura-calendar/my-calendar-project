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
    Googleスプレッドシートを .xlsx としてダウンロードし、Excelとして読み込む。
    自動で変換される機能を利用し、APIでの複雑な変換を避けスピードアップを図る。
    """
    try:
        # get_mediaで直接ダウンロード（スプレッドシートでもxlsxとして降ってくる挙動を利用）
        request = service.files().get_media(fileId=file_id)
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        # Excelとして全シートを読み込み
        all_sheets = pd.read_excel(fh, sheet_name=None, header=None, dtype=object)
        
        time_dic = {}
        for sheet_name, df in all_sheets.items():
            df = df.fillna("")
            # 数値の末尾 .0 を除去
            def clean_format(x):
                s = str(x)
                return s[:-2] if s.endswith('.0') else s
            df = df.map(clean_format) if hasattr(df, 'map') else df.applymap(clean_format)
            time_dic[sheet_name] = df
                
        return time_dic
    except Exception as e:
        # もしget_mediaで失敗した場合はexport_mediaにフォールバック（保険）
        try:
            request = service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            fh.seek(0)
            all_sheets = pd.read_excel(fh, sheet_name=None, header=None, dtype=object)
            return {k: v.fillna("").astype(str) for k, v in all_sheets.items()}
        except:
            raise Exception(f"時程表のダウンロードに失敗しました: {e}")

def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[\s\n\u3000]+', '', normalized).strip().upper()

def extract_workplace_from_header(header_text):
    """PDFの(0,0)セルから勤務地名を抽出。失敗しても『不明』を返して処理を止めない。"""
    if not header_text: return "不明な拠点"
    text_str = str(header_text)
    lines = text_str.split('\n')
    num_newlines = text_str.count('\n')
    target_index = num_newlines // 2
    try:
        work_place = lines[target_index].strip() if target_index < len(lines) else lines[-1].strip()
        if not work_place:
            non_empty = [e.strip() for e in lines if e.strip()]
            work_place = non_empty[0] if non_empty else "不明"
        return work_place
    except:
        return "解析エラー"

def pdf_reader(file_stream, target_staff):
    """
    原因解決策: まず勤務地を取得し、その後に本人がいるかチェックする。
    """
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)
    
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2: continue
                
                # --- 手順1: まず勤務地を特定する ---
                header_val = df.iloc[0, 0]
                current_workplace = extract_workplace_from_header(header_val)
                
                # --- 手順2: その勤務地テーブル内に本人がいるか探す ---
                search_col = df.iloc[:, 0].astype(str).apply(normalize_for_match)
                found_indices = [i for i, val in enumerate(search_col) if clean_target in val]
                
                if not found_indices:
                    continue # 本人がいない勤務地テーブルは無視して次へ
                
                # 本人が見つかった場合のみ辞書に登録
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
    """
    PDFから取得した勤務地名と、時程表（シート名 or A列）を紐付ける。
    """
    integrated_dic = {}
    logs = []
    for place_name, pdf_data in pdf_dic.items():
        norm_place = normalize_for_match(place_name)
        matched_key = None
        
        for k, df in time_schedule_dic.items():
            # シート名で判定
            if normalize_for_match(k) in norm_place or norm_place in normalize_for_match(k):
                matched_key = k
                break
            # A列の内容で判定
            a_col = df.iloc[:, 0].astype(str).apply(normalize_for_match).tolist()
            if any(norm_place == val for val in a_col if val):
                matched_key = k
                break
        
        if matched_key:
            integrated_dic[place_name] = [pdf_data[0], pdf_data[1], time_schedule_dic[matched_key]]
            logs.append(f"✅ 紐付け成功: {place_name} ↔ {matched_key}")
        else:
            logs.append(f"❌ 紐付け失敗: {place_name}")
            
    return integrated_dic, logs

def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
    """打合.pyのロジックを忠実に再現"""
    if (time_schedule.iloc[:, 1].astype(str) == shift_info).any():
        final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", key])
    
    sched_clean = time_schedule.copy()
    my_time_shift = sched_clean[sched_clean.iloc[:, 1].astype(str) == shift_info]
    
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, sched_clean.shape[1]):
            current_val = str(my_time_shift.iloc[0, t_col])
            if current_val != prev_val:
                if current_val != "":
                    mask_handing_over = (sched_clean.iloc[:, t_col].astype(str) == prev_val) & (sched_clean.iloc[:, 1] != shift_info)
                    mask_taking_over = (sched_clean.iloc[:, t_col].astype(str) == current_val) & (sched_clean.iloc[:, 1] != shift_info)
                    
                    handing_over = ""; taking_over = ""
                    for i in range(2):
                        mask = mask_handing_over if i == 0 else mask_taking_over
                        search_keys = sched_clean.loc[mask, sched_clean.columns[1]]
                        target_rows = other_staff_shift[other_staff_shift.iloc[:, col].isin(search_keys)]
                        names = "・".join(target_rows.iloc[:, 0].unique().astype(str))
                        if i == 0: handing_over = f"to {names}" if names else ""
                        else: taking_over = f"【{current_val}】from {names}" if names else f"【{current_val}】"
                    
                    final_rows.append([f"{handing_over}=>{taking_over}", target_date, sched_clean.iloc[0, t_col], target_date, "", "False", "", key])
                else:
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = sched_clean.iloc[0, t_col]
            prev_val = current_val

def process_full_month(integrated_dic, year, month):
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        current_col = day 
        for place_key, data_list in integrated_dic.items():
            my_shift, other_shift, time_sched = data_list
            if current_col >= my_shift.shape[1]: continue
            raw_val = str(my_shift.iloc[0, current_col])
            if not raw_val or raw_val.lower() == 'nan' or raw_val.strip() == "": continue
            
            items = [i.strip() for i in re.split(r'[,、\s\n]+', raw_val) if i.strip()]
            master_codes = time_sched.iloc[:, 1].astype(str).tolist()
            for item in items:
                if item in master_codes:
                    shift_cal(place_key, target_date_str, current_col, item, my_shift, other_shift, time_sched, all_final_rows)
                else:
                    all_final_rows.append([item, target_date_str, "", target_date_str, "", "True", "", place_key])
    return all_final_rows
