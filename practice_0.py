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
    プログラム上の訂正: 
    Googleスプレッドシート（エディタ形式）をダウンロードするための export_media を使用。
    """
    try:
        # ファイルのMIMEタイプを確認
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType')

        # Googleスプレッドシート形式の場合
        if mime_type == 'application/vnd.google-apps.spreadsheet':
            # Excel形式にエクスポートして取得
            request = service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            # 通常のバイナリファイル（.xlsx等）の場合
            request = service.files().get_media(fileId=file_id)
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        # 全シートをオブジェクト形式で読み込み
        all_sheets = pd.read_excel(fh, sheet_name=None, header=None, dtype=object)
        
        time_dic = {}
        for sheet_name, df in all_sheets.items():
            df = df.fillna("")
            def clean_format(x):
                s = str(x)
                return s[:-2] if s.endswith('.0') else s
            # pandasのバージョンに合わせ、mapまたはapplymapを使用
            df = df.map(clean_format) if hasattr(df, 'map') else df.applymap(clean_format)
            time_dic[sheet_name] = df
        return time_dic
    except Exception as e:
        raise Exception(f"時程表取得失敗: {e}")

def normalize_for_match(text):
    """改行・空白を除去し、比較を安定させる"""
    if text is None or str(text).lower() == 'nan': return ""
    text_clean = str(text).replace('\n', '').replace('\r', '')
    normalized = unicodedata.normalize('NFKC', text_clean)
    return re.sub(r'[\s\u3000]+', '', normalized).strip().upper()

def extract_workplace_from_header(header_text):
    """ヘッダーから拠点名を抽出"""
    if not header_text: return "不明な拠点"
    text_str = str(header_text)
    lines = text_str.split('\n')
    num_newlines = text_str.count('\n')
    target_index = num_newlines // 2
    try:
        work_place = lines[target_index].strip() if target_index < len(lines) else lines[-1].strip()
        return work_place if work_place else "不明"
    except: return "解析エラー"

def pdf_reader(file_stream, target_staff):
    """PDF解析。2行表示（名字・名前の分断）に対応した検索ロジックを含む"""
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                df = pd.DataFrame(table)
                if df.empty or df.shape[1] < 2: continue
                
                header_val = df.iloc[0, 0]
                current_workplace = extract_workplace_from_header(header_val)
                
                search_col = df.iloc[:, 0].astype(str)
                found_indices = []
                for i in range(len(search_col)):
                    if clean_target in normalize_for_match(search_col.iloc[i]):
                        found_indices.append(i)
                    elif i > 0:
                        # 上下の行を合体させて再判定
                        combined = normalize_for_match(search_col.iloc[i-1] + search_col.iloc[i])
                        if clean_target in combined and clean_target not in normalize_for_match(search_col.iloc[i-1]):
                            found_indices.append(i)

                if not found_indices: continue
                
                for idx in found_indices:
                    my_data = df.iloc[[idx]].copy()
                    others_data = df[df.index != idx].copy()
                    key_name = current_workplace
                    cnt = 2
                    while key_name in table_dictionary:
                        key_name = f"{current_workplace}_{cnt}"; cnt += 1
                    table_dictionary[key_name] = [my_data.reset_index(drop=True), others_data.reset_index(drop=True)]
    return table_dictionary

def data_integration(pdf_dic, time_schedule_dic):
    """拠点ごとの時程表紐付け"""
    integrated_dic = {}
    logs = []
    for place_name, pdf_data in pdf_dic.items():
        norm_place = normalize_for_match(place_name)
        matched_key = None
        for k, df in time_schedule_dic.items():
            if normalize_for_match(k) in norm_place or norm_place in normalize_for_match(k):
                matched_key = k; break
            a_col = df.iloc[:, 0].astype(str).apply(normalize_for_match).tolist()
            if any(norm_place == val for val in a_col if val):
                matched_key = k; break
        
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
                        
                        names_raw = target_rows.iloc[:, 0].dropna()
                        # 空白やNone、改行後のゴミを除去
                        names_list = [str(n).split('\n')[0].strip() for n in names_raw.unique() if n and str(n).lower() != 'none']
                        
                        if i == 0:
                            staff_names = f"to {'・'.join(names_list)}" if names_list else ""
                            handing_over = f"{staff_names}"
                        else:
                            staff_names = f"from {'・'.join(names_list)}" if names_list else ""
                            taking_over = f"【{current_val}】{staff_names}"
                    
                    final_rows.append([f"{handing_over}=>{taking_over}", target_date, sched_clean.iloc[0, t_col], target_date, "", "False", "", key])
                else:
                    if len(final_rows) > 0 and final_rows[-1][5] == "False":
                        final_rows[-1][4] = sched_clean.iloc[0, t_col]
            prev_val = current_val

def process_full_month(integrated_dic, year, month):
    """月間全日程の処理"""
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
