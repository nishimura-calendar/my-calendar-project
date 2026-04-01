import pandas as pd
import pdfplumber
import re
import io
import unicodedata
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 時間整形 ---
def format_to_hhmm(val):
    if val is None or str(val).lower() == "nan" or str(val).strip() == "":
        return ""
    try:
        s_val = str(val).strip()
        if s_val.replace('.', '').isdigit():
            num = float(s_val)
            if 0 < num < 1:  # Serial value
                h = int(num * 24)
                m = int(round((num * 24 - h) * 60))
            else:  # Hours like 6.25
                h = int(num)
                m = int(round((num - h) * 60))
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        return s_val
    except:
        return s_val

def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'[^a-zA-Z0-9ぁ-んァ-ヶ亜-熙]', '', normalized).strip().upper()

# --- 2. 時程表解析 ---
def download_and_extract_schedule(drive_service, file_id):
    try:
        fh = io.BytesIO()
        request = drive_service.files().export_media(
            fileId=file_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        df_all = pd.read_excel(fh, header=None).fillna('')
        
        location_data_dic = {}
        loc_indices = []

        for r in range(len(df_all)):
            row = df_all.iloc[r]
            if str(row[0]).strip() != "" and str(row[1]).strip() == "" and str(row[2]).strip() == "":
                loc_indices.append((r, str(row[0]).strip()))

        for i, (start_row, raw_name) in enumerate(loc_indices):
            match_key = normalize_for_match(raw_name)
            next_loc = loc_indices[i+1][0] if i+1 < len(loc_indices) else len(df_all)
            df_block = df_all.iloc[start_row:next_loc, :].copy().reset_index(drop=True)
            
            end_col = df_block.shape[1]
            for col in range(3, df_block.shape[1]):
                if "出勤" in str(df_block.iloc[0, col]):
                    end_col = col
                    break
            df_block = df_block.iloc[:, :end_col]

            for col in range(3, df_block.shape[1]):
                df_block.iloc[0, col] = format_to_hhmm(df_block.iloc[0, col])
            
            areas = [str(x).strip() for x in df_block.iloc[1:, 1] if str(x).strip()]
            location_data_dic[match_key] = {
                "raw_name": raw_name,
                "df": df_block,
                "norm_areas": [normalize_for_match(a) for a in areas]
            }
        return location_data_dic
    except Exception as e:
        print(f"Schedule Error: {e}")
        return {}

# --- 3. PDF解析 ---
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
                    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                    if not lines: continue
                    work_place = lines[len(lines)//2]
                    
                    match_key = normalize_for_match(work_place)
                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        table_dictionary[match_key] = {
                            "raw_name": work_place, "my_df": my_df
                        }
    except Exception as e:
        print(f"PDF Error: {e}")
    return table_dictionary

# --- 4. 判定と出力データ生成 ---
def generate_all_csv_data(pdf_dic, time_dic, target_date):
    shift_rows = []
    holiday_rows = []
    event_rows = []
    
    date_str = target_date.strftime("%Y-%m-%d")
    # 休日キーワード
    holiday_keywords = ["休", "公休", "休日", "有休", "有給", "特休"]

    for k, v in pdf_dic.items():
        matched_key = None
        if k in time_dic: matched_key = k
        else:
            for tk in time_dic.keys():
                if k in tk or tk in k: matched_key = tk; break
        
        if not matched_key: continue
        
        loc_name = v["raw_name"]
        areas_norm = time_dic[matched_key]["norm_areas"]
        
        shift_vals = []
        for cell in v["my_df"].iloc[1].tolist():
            for sub_val in str(cell).split('\n'):
                if sub_val.strip(): shift_vals.append(sub_val.strip())

        for val in shift_vals:
            # A. 休日判定
            if any(kw in val for kw in holiday_keywords):
                holiday_rows.append([val, date_str])
                continue

            norm_val = normalize_for_match(val)
            
            # B. 巡回区域一致判定 (シフト扱い)
            if norm_val in areas_norm:
                shift_rows.append([f"{loc_name}+{val}", date_str, "", date_str, "", "True", "", loc_name])
            
            # C. それ以外（本町、その他すべて）はイベント扱い
            else:
                event_rows.append([val, date_str, "", date_str, "", "True", "", ""])
                
        # シフトの最後に「打ち合わせ通り」を挿入
        shift_rows.append(["打ち合わせ通り", date_str, "打ち合わせ通り", date_str, "打ち合わせ通り", "False", "", ""])

    return shift_rows, holiday_rows, event_rows
