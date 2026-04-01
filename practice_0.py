import pandas as pd
import pdfplumber
import re
import io
import unicodedata
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 時間表記の整形 (基本事項: 6.25 -> 06:15 等) ---
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
            else:  # 時間数
                h = int(num)
                m = int(round((num - h) * 60))
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        return s_val
    except:
        return s_val

# --- 2. 比較用正規化 ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 3. 時程表（マスター）の抽出 ---
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

        # A列に勤務地がある行を特定
        for r in range(len(df_all)):
            row = df_all.iloc[r]
            if str(row[0]).strip() != "" and str(row[1]).strip() == "" and str(row[2]).strip() == "":
                loc_indices.append((r, str(row[0]).strip()))

        for i, (start_row, raw_name) in enumerate(loc_indices):
            match_key = normalize_for_match(raw_name)
            next_loc = loc_indices[i+1][0] if i+1 < len(loc_indices) else len(df_all)
            df_block = df_all.iloc[start_row:next_loc, :].copy().reset_index(drop=True)
            
            # 時間軸と末尾(出勤/退勤)の検知
            end_col = df_block.shape[1]
            for col in range(3, df_block.shape[1]):
                cell_v = str(df_block.iloc[0, col])
                if any(x in cell_v for x in ["出勤", "退勤", "実働"]):
                    end_col = col
                    break
            df_block = df_block.iloc[:, :end_col]

            # 時間ヘッダーをhh:mmに
            for col in range(3, df_block.shape[1]):
                df_block.iloc[0, col] = format_to_hhmm(df_block.iloc[0, col])
            
            # B列（巡回区域）を正規化リストで保存
            areas_raw = [str(x).strip() for x in df_block.iloc[1:, 1] if str(x).strip()]
            location_data_dic[match_key] = {
                "raw_name": raw_name,
                "df": df_block,
                "norm_areas": [normalize_for_match(a) for a in areas_raw]
            }
        return location_data_dic
    except Exception as e:
        print(f"Schedule extraction error: {e}")
        return {}

# --- 4. PDF解析 (iloc(0,0)から拠点を特定) ---
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
                    
                    # 基本事項: iloc(0,0)に勤務地
                    raw_loc = str(df.iloc[0, 0])
                    lines = [l.strip() for l in raw_loc.split('\n') if l.strip()]
                    work_place = lines[len(lines)//2] if lines else raw_loc
                    
                    match_key = normalize_for_match(work_place)
                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        table_dictionary[match_key] = {
                            "raw_name": work_place, "my_df": my_df
                        }
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return table_dictionary

# --- 5. CSVデータ生成 (「基本事項」完全準拠ロジック) ---
def generate_all_csv_data(pdf_dic, time_dic, target_date):
    shift_rows = []
    holiday_rows = []
    event_rows = []
    
    date_str = target_date.strftime("%Y-%m-%d")
    holiday_kws = ["休", "有休", "有給", "公休", "特休"]

    for k, v in pdf_dic.items():
        matched_key = None
        if k in time_dic: matched_key = k
        else:
            for tk in time_dic.keys():
                if k in tk or tk in k: matched_key = tk; break
        
        if not matched_key: continue
        
        loc_name = v["raw_name"]
        master_data = time_dic[matched_key]
        areas_norm = master_data["norm_areas"]
        master_df = master_data["df"]
        
        # PDF詳細行からアイテムを分解
        detail_vals = v["my_df"].iloc[1].tolist()
        items = []
        for cell in detail_vals:
            for line in str(cell).split('\n'):
                it = line.strip()
                if it and it not in items: items.append(it)

        for item in items:
            # 1. 休日判定
            if any(kw in item for kw in holiday_kws):
                holiday_rows.append([item, date_str])
                continue

            # 2. ロジック判定
            norm_item = normalize_for_match(item)
            
            # B列（巡回区域）にあれば「シフト」
            if norm_item in areas_norm:
                # (拠点+値, 日付, "", 日付, "", True, "", 拠点)
                shift_rows.append([f"{loc_name}+{item}", date_str, "", date_str, "", "True", "", loc_name])
            
            # B列になければ（本町であろうと何であろうと）「イベント」
            else:
                # (値, 日付, "", 日付, "", True, "", "")
                event_rows.append([item, date_str, "", date_str, "", "True", "", ""])
                
                # さらに、値が「本町」ならば2段目の関数処理を追加
                if "本町" in item:
                    # 本町詳細行: (本町, 日付, 開始時間, 日付, 終了時間, False, "", "")
                    # 時間は時程表のヘッダーの最初と最後から取得
                    start_t = master_df.iloc[0, 3] if master_df.shape[1] > 3 else ""
                    end_t = master_df.iloc[0, -1] if master_df.shape[1] > 3 else ""
                    event_rows.append([item, date_str, start_t, date_str, end_t, "False", "", ""])

        # その日の処理の最後に「打ち合わせ通り」を追加して終了
        # (打ち合わせ通り, 日付, 打ち合わせ通り, 日付, 打ち合わせ通り, False, "", "")
        shift_rows.append(["打ち合わせ通り", date_str, "打ち合わせ通り", date_str, "打ち合わせ通り", "False", "", ""])

    return shift_rows, holiday_rows, event_rows
