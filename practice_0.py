import pandas as pd
import pdfplumber
import re
import io
import unicodedata
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 時間軸の整形 (数値 6.25 等を 06:15 に変換) ---
def format_to_hhmm(val):
    if val is None or str(val).lower() == "nan" or str(val).strip() == "":
        return ""
    try:
        s_val = str(val).strip()
        if s_val.replace('.', '').isdigit():
            num = float(s_val)
            if 0 < num < 1:  # シリアル値
                h = int(num * 24)
                m = int(round((num * 24 - h) * 60))
            else:  # 6.25 などの時間数
                h = int(num)
                m = int(round((num - h) * 60))
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        return s_val
    except:
        return s_val

# --- 2. 文字列正規化 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[^a-zA-Z0-9ぁ-んァ-ヶ亜-熙]', '', normalized).strip().upper()

# --- 3. 時程表の解析 (時間軸の範囲を制限) ---
def download_and_extract_schedule(drive_service, file_id):
    """
    A列=勤務地, B列=巡回区域, C列=ロッカ
    勤務地行：D列以降が時間軸。
    「出勤」という文字列が出現する列の前までを有効な時間範囲とする。
    """
    try:
        file_metadata = drive_service.files().get(fileId=file_id).execute()
        mime_type = file_metadata.get('mimeType', '')
        fh = io.BytesIO()
        
        if mime_type == 'application/vnd.google-apps.spreadsheet':
            request = drive_service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            request = drive_service.files().get_media(fileId=file_id)

        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        df_all = pd.read_excel(fh, header=None).fillna('')
        
        location_data_dic = {}
        loc_indices = []

        # 勤務地行の特定
        for r in range(len(df_all)):
            row = df_all.iloc[r]
            a_val = str(row[0]).strip()
            b_val = str(row[1]).strip() if len(row) > 1 else ""
            c_val = str(row[2]).strip() if len(row) > 2 else ""
            
            if a_val != "" and b_val == "" and c_val == "":
                loc_indices.append((r, a_val))

        for i, (start_row, raw_name) in enumerate(loc_indices):
            match_key = normalize_for_match(raw_name)
            next_loc_row = loc_indices[i+1][0] if i+1 < len(loc_indices) else len(df_all)
            
            # ブロック切り出し
            df_block = df_all.iloc[start_row:next_loc_row, :].copy().reset_index(drop=True)
            
            # 時間軸の終端（「出勤」列）を探す
            end_col = df_block.shape[1]
            for col in range(3, df_block.shape[1]):
                if "出勤" in str(df_block.iloc[0, col]):
                    end_col = col
                    break
            
            # 有効な列範囲に絞る (A, B, C列 + D列から終端まで)
            df_block = df_block.iloc[:, :end_col]

            # 勤務地行（1行目）の時間軸（D列目以降）のみ整形
            for col in range(3, df_block.shape[1]):
                time_val = df_block.iloc[0, col]
                if time_val != "":
                    df_block.iloc[0, col] = format_to_hhmm(time_val)
            
            # 巡回区域リスト（B列の2行目以降）
            areas_list = []
            for r_idx in range(1, len(df_block)):
                area_val = str(df_block.iloc[r_idx, 1]).strip()
                if area_val:
                    areas_list.append(area_val)

            location_data_dic[match_key] = {
                "raw_name": raw_name,
                "df": df_block,
                "patrol_areas": areas_list,
                "norm_areas": [normalize_for_match(a) for a in areas_list]
            }
        return location_data_dic
    except Exception as e:
        print(f"Schedule extraction error: {e}")
        return {}

# --- 4. PDF読み取り ---
def pdf_reader(pdf_stream, target_staff):
    table_dictionary = {}
    clean_target = normalize_for_match(target_staff)
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2: continue
                    df = pd.DataFrame(table).fillna('')
                    
                    raw_text = str(df.iloc[0, 0])
                    lines = raw_text.split('\n')
                    target_index = raw_text.count('\n') // 2
                    work_place = lines[target_index].strip() if target_index < len(lines) else lines[0].strip()
                    
                    df.iloc[0, 0] = work_place
                    match_key = normalize_for_match(work_place)
                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        for r in range(len(my_df)):
                            for c in range(len(my_df.columns)):
                                val = str(my_df.iloc[r, c])
                                if '\n' in val:
                                    my_df.iloc[r, c] = val.replace('\n', ' / ')
                        
                        other_df = df.iloc[[i for i in range(len(df)) if i not in [idx, idx+1]]].copy()
                        table_dictionary[match_key] = {
                            "raw_name": work_place, "my_df": my_df, "other_df": other_df
                        }
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
    return table_dictionary

# --- 5. データの紐付け ---
def data_integration(pdf_dic, time_dic):
    integrated = {}
    for k, v in pdf_dic.items():
        matched_key = None
        if k in time_dic: matched_key = k
        else:
            for tk in time_dic.keys():
                if k in tk or tk in k:
                    matched_key = tk
                    break
        if matched_key:
            integrated[v["raw_name"]] = {
                "my_shift": v["my_df"],
                "others": v["other_df"],
                "schedule": time_dic[matched_key]["df"],
                "areas": time_dic[matched_key]["norm_areas"]
            }
    return integrated
