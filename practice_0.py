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
            if 0 < num < 1:
                h = int(num * 24)
                m = int(round((num * 24 - h) * 60))
            else:
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

        for r in range(len(df_all)):
            row = df_all.iloc[r]
            a_val, b_val, c_val = str(row[0]).strip(), str(row[1]).strip(), str(row[2]).strip()
            if a_val != "" and b_val == "" and c_val == "":
                loc_indices.append((r, a_val))

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
        print(f"Error: {e}")
        return {}

# --- 3. PDF読み取り ---
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
                    work_place = lines[len(lines)//2].strip()
                    match_key = normalize_for_match(work_place)
                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        other_df = df.iloc[[i for i in range(len(df)) if i not in [idx, idx+1]]].copy()
                        table_dictionary[match_key] = {
                            "raw_name": work_place, "my_df": my_df, "other_df": other_df
                        }
    except Exception as e:
        print(f"PDF Error: {e}")
    return table_dictionary

# --- 4. 判定とCSV用データ生成 ---
def generate_calendar_data(pdf_dic, time_dic, target_date):
    shift_csv_rows = []
    holiday_csv_rows = []
    event_csv_rows = []
    
    date_str = target_date.strftime("%Y-%m-%d")

    for k, v in pdf_dic.items():
        matched_key = None
        if k in time_dic: matched_key = k
        else:
            for tk in time_dic.keys():
                if k in tk or tk in k: matched_key = tk; break
        
        if not matched_key: continue
        
        loc_name = v["raw_name"]
        areas_norm = time_dic[matched_key]["norm_areas"]
        # PDFの2行目（詳細）を取得
        details = v["my_df"].iloc[1].tolist()
        
        for val in details:
            val_str = str(val).strip()
            if not val_str: continue
            
            # 休日判定
            if val_str in ["休", "公休", "有休"]:
                holiday_csv_rows.append([val_str, date_str])
                continue

            norm_val = normalize_for_match(val_str)
            
            # 本町判定
            if "本町" in val_str:
                # 本町はイベント扱いとする例
                event_csv_rows.append([val_str, date_str, "09:00", date_str, "18:00", "False", "", ""])
            # 区域一致判定
            elif norm_val in areas_norm:
                shift_csv_rows.append([f"{loc_name}+{val_str}", date_str, "", date_str, "", "True", "", loc_name])
            # デフォルト
            else:
                shift_csv_rows.append([val_str, date_str, "", date_str, "", "True", "", ""])
                
        # 打ち合わせ通り
        shift_csv_rows.append(["打ち合わせ通り", date_str, "打ち合わせ通り", date_str, "打ち合わせ通り", "False", "", ""])

    return shift_csv_rows, holiday_csv_rows, event_csv_rows
