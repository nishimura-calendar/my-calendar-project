import pandas as pd
import pdfplumber
import re
import io
import unicodedata
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 時間表記の変換 (基本事項: 6.25, 6.5 などを hh:mm へ) ---
def format_to_hhmm(val):
    if val is None or str(val).lower() == "nan" or str(val).strip() == "":
        return ""
    try:
        s_val = str(val).strip()
        # 数値（時間数またはシリアル値）の場合
        if s_val.replace('.', '').isdigit():
            num = float(s_val)
            if 0 < num < 1:  # シリアル値 (例: 0.25 -> 06:00)
                h = int(num * 24)
                m = int(round((num * 24 - h) * 60))
            else:  # 時間数 (例: 6.25 -> 06:15)
                h = int(num)
                m = int(round((num - h) * 60))
            if m >= 60: h += 1; m = 0
            return f"{h:02d}:{m:02d}"
        return s_val  # "出勤" などの文字列はそのまま返す
    except:
        return s_val

# --- 2. 文字列正規化 (基本事項: 比較用) ---
def normalize_for_match(text):
    if text is None or str(text).lower() == 'nan': return ""
    # 全角を半角に、空白を除去
    normalized = unicodedata.normalize('NFKC', str(text))
    return re.sub(r'\s+', '', normalized).strip().upper()

# --- 3. 時程表の取得 (基本事項: A列=勤務地, B列=巡回区域) ---
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
        # openpyxlを使用して読み込み
        df_all = pd.read_excel(fh, header=None).fillna('')
        
        location_data_dic = {}
        loc_indices = []

        # 基本事項: A列に勤務地がある行を特定
        for r in range(len(df_all)):
            row = df_all.iloc[r]
            a_val = str(row[0]).strip()
            b_val = str(row[1]).strip()
            c_val = str(row[2]).strip()
            # A列のみに値がある行を拠点行とする
            if a_val != "" and b_val == "" and c_val == "":
                loc_indices.append((r, a_val))

        for i, (start_row, raw_name) in enumerate(loc_indices):
            match_key = normalize_for_match(raw_name)
            next_loc = loc_indices[i+1][0] if i+1 < len(loc_indices) else len(df_all)
            df_block = df_all.iloc[start_row:next_loc, :].copy().reset_index(drop=True)
            
            # 基本事項: D列目以降の時間行を整形、末尾の"出勤/退勤"までを範囲とする
            end_col = df_block.shape[1]
            for col in range(3, df_block.shape[1]):
                cell_v = str(df_block.iloc[0, col])
                if any(x in cell_v for x in ["出勤", "退勤", "実働"]):
                    end_col = col
                    break
            df_block = df_block.iloc[:, :end_col]

            # 時間ヘッダーの整形
            for col in range(3, df_block.shape[1]):
                df_block.iloc[0, col] = format_to_hhmm(df_block.iloc[0, col])
            
            # 巡回区域 (B列 2行目以降) のマスター作成
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

# --- 4. PDF読み取り (基本事項: iloc(0,0)に勤務地) ---
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
                    
                    # 基本事項: iloc(0,0)から勤務地を抽出
                    raw_loc_text = str(df.iloc[0, 0])
                    # 改行が含まれる場合、中心付近の行を勤務地とする(PDFの構造に依存)
                    lines = [l.strip() for l in raw_loc_text.split('\n') if l.strip()]
                    work_place = lines[len(lines)//2] if lines else raw_loc_text
                    
                    match_key = normalize_for_match(work_place)
                    # 氏名列(0列目)を正規化して検索
                    col_0_norm = [normalize_for_match(str(val)) for val in df.iloc[:, 0].tolist()]
                    
                    if clean_target in col_0_norm:
                        idx = col_0_norm.index(clean_target)
                        # 対象者行と詳細行（下段）の2行をセットで抽出
                        my_df = df.iloc[idx : idx+2].copy().reset_index(drop=True)
                        table_dictionary[match_key] = {
                            "raw_name": work_place, "my_df": my_df
                        }
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return table_dictionary

# --- 5. CSVデータ生成 (基本事項の判定ロジック) ---
def generate_all_csv_data(pdf_dic, time_dic, target_date):
    shift_rows = []
    holiday_rows = []
    event_rows = []
    
    date_str = target_date.strftime("%Y-%m-%d")
    holiday_kws = ["休", "公休", "休日", "有休", "有給", "特休"]

    for k, v in pdf_dic.items():
        # 時程表マスターとの照合
        matched_key = None
        if k in time_dic: matched_key = k
        else:
            for tk in time_dic.keys():
                if k in tk or tk in k: matched_key = tk; break
        
        if not matched_key: continue
        
        loc_name = v["raw_name"]
        areas_norm = time_dic[matched_key]["norm_areas"]
        
        # PDF詳細セルから個別のシフトコードを抽出
        raw_vals = v["my_df"].iloc[1].tolist()
        contents = []
        for cell in raw_vals:
            for part in str(cell).split('\n'):
                if part.strip(): contents.append(part.strip())

        for val in contents:
            # A. 休日判定 (最優先)
            if any(kw in val for kw in holiday_kws):
                holiday_rows.append([val, date_str])
                continue

            norm_val = normalize_for_match(val)
            
            # B. 巡回区域一致判定 (シフト扱い)
            if norm_val in areas_norm:
                # 形式: (拠点+値, 日付, "", 日付, "", True, "", 拠点)
                shift_rows.append([f"{loc_name}+{val}", date_str, "", date_str, "", "True", "", loc_name])
            
            # C. その他（本町・その他不一致すべて）はイベント扱い
            else:
                # 形式: (値, 日付, "", 日付, "", True, "", "")
                event_rows.append([val, date_str, "", date_str, "", "True", "", ""])
                
        # 最後に「打ち合わせ通り」を追加
        shift_rows.append(["打ち合わせ通り", date_str, "打ち合わせ通り", date_str, "打ち合わせ通り", "False", "", ""])

    return shift_rows, holiday_rows, event_rows
