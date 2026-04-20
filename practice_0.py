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

def time_schedule_from_drive(service, file_id):
    """
    基本事項に準拠した時程表の再構築ロジック。
    A列=勤務地, B列=巡回区域, C列=ロッカ, D列以降=時間行。
    時間列のスタートとエンドを動的に抽出する。
    """
    try:
        request = service.files().get_media(fileId=file_id)
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
            request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_df = pd.read_excel(fh, header=None, engine='openpyxl', sheet_name=0, dtype=str).fillna('')
        # A列(index 0)が空白でない行を勤務地の開始行とみなす
        location_rows = full_df[full_df.iloc[:, 0].str.strip() != ''].index.tolist()
        location_data_dic = {}
        
        for i, start_row in enumerate(location_rows):
            next_start = location_rows[i+1] if i+1 < len(location_rows) else len(full_df)
            temp_range = full_df.iloc[start_row:next_start, :].copy().reset_index(drop=True)
            location_name = temp_range.iloc[0, 0].strip()
            
            # 時間ヘッダー列(D列以降)の特定
            header_row = temp_range.iloc[0]
            start_col, last_col = None, None
            for c in range(1, len(header_row)):
                val = str(header_row[c]).strip()
                # 数字が含まれる列を時間列の範囲とする
                if any(char.isdigit() for char in val):
                    if start_col is None: start_col = c
                    last_col = c
                elif start_col is not None: break
            
            if start_col is not None:
                # 基本事項通りの構成 (A, B, C列 + 特定した時間列)
                base_indices = [0, 1, 2]
                time_indices = list(range(start_col, last_col + 1))
                all_indices = sorted(list(set(base_indices + time_indices)))
                final_block = temp_range.iloc[:, all_indices].copy().reset_index(drop=True)
                
                # エクセル時刻（シリアル値）を HH:MM に変換
                for c in range(len(final_block.columns)):
                    if all_indices[c] in time_indices:
                        v = final_block.iloc[0, c]
                        try:
                            fv = float(v)
                            total_min = int(round(fv * 24 * 60))
                            final_block.iloc[0, c] = f"{total_min//60}:{total_min%60:02d}"
                        except: pass
                location_data_dic[location_name] = final_block
        return location_data_dic
    except Exception as e:
        raise Exception(f"時程表読込エラー: {str(e)}")

def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    """
    時間別詳細スケジュールの生成。
    交代相手の検索(From/To)および退勤判定を含む。
    """
    if time_schedule is None: return

    ts = time_schedule.fillna("").astype(str)
    # B列(index 1)がシフト記号（Cなど）に一致する行を抽出
    my_rows = ts[ts.iloc[:, 1] == shift_info]
    if my_rows.empty: return
    
    my_row = my_rows.iloc[0]
    num_cols = ts.shape[1]
    prev_val = ""
    
    # 3列目(index 3)以降が実際の業務割り当て
    for t_col in range(3, num_cols):
        current_val = my_row[t_col].strip()
        time_header = ts.iloc[0, t_col].strip()
        
        if current_val != prev_val:
            # 終了処理（EndTime確定と引き継ぎ相手特定）
            if prev_val != "" and final_rows and final_rows[-1][5] == "False":
                final_rows[-1][4] = time_header
                
                # to (次) の検索
                mask_next = (ts.iloc[:, t_col] == prev_val) & (ts.iloc[:, 1] != shift_info)
                next_codes = ts.loc[mask_next, ts.columns[1]].tolist()
                
                next_staff = []
                for _, s_row in other_staff_shift.iterrows():
                    if str(s_row.iloc[col]).strip() in next_codes:
                        n = str(s_row.iloc[0]).split('\n')[0].strip()
                        if n and n.lower() != 'nan': next_staff.append(n)
                
                if next_staff:
                    final_rows[-1][0] += f" => to {'・'.join(sorted(list(set(next_staff))))}"
                elif all(my_row[k].strip() == "" for k in range(t_col, num_cols)):
                    final_rows[-1][0] += " => (退勤)"

            # 開始処理（新規業務行の追加）
            if current_val != "":
                # from (前) の検索
                mask_prev = (ts.iloc[:, t_col - 1] == current_val) & (ts.iloc[:, 1] != shift_info)
                prev_codes = ts.loc[mask_prev, ts.columns[1]].tolist()
                
                prev_staff = []
                for _, s_row in other_staff_shift.iterrows():
                    if str(s_row.iloc[col]).strip() in prev_codes:
                        n = str(s_row.iloc[0]).split('\n')[0].strip()
                        if n and n.lower() != 'nan': prev_staff.append(n)
                
                from_str = f"from {'・'.join(sorted(list(set(prev_staff))))} " if prev_staff else ""
                subject = f"{from_str}【{current_val}】"
                
                # AllDay=False で詳細行を追加
                final_rows.append([subject, target_date, time_header, target_date, "", "False", "詳細スケジュール", key])
                
        prev_val = current_val

def process_full_month(integrated_dic, year, month):
    """
    1ヶ月分のループと場合分けの司令塔。
    1. 休暇系の判定
    2. 通常勤務時の『終日イベント(True)』登録
    3. 時程表に基づく『詳細スケジュール(False)』登録
    """
    all_final_rows = []
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        target_date_str = f"{year}-{month:02d}-{day:02d}"
        
        for place_key, data_list in integrated_dic.items():
            my_daily, others = data_list[0], data_list[1]
            time_sched = data_list[2] if len(data_list) > 2 else None
            
            col_idx = day + 1 
            if col_idx >= my_daily.shape[1]: continue
            
            raw_val = str(my_daily.iloc[0, col_idx]).strip()
            if not raw_val or raw_val.lower() == 'nan': continue
            
            shifts = [s.strip() for s in re.split(r'[,、\s\n]+', raw_val) if s.strip()]
            
            for s_info in shifts:
                # --- 基本事項：場合分けの実施 ---
                
                # A. 休暇・非勤務系
                if s_info in ["公", "公休", "有", "有給", "特", "欠", "振", "替"]:
                    all_final_rows.append([f"【{s_info}】", target_date_str, "", target_date_str, "", "True", "休暇等", place_key])
                    continue
                
                # B. 通常勤務
                # B-1. まず終日イベントとして勤務状態を登録 (AllDay=True)
                all_final_rows.append([f"{place_key}_{s_info}", target_date_str, "", target_date_str, "", "True", "勤務予定", place_key])
                
                # B-2. 次に時程表がある場合のみ、詳細な動きを登録 (AllDay=False)
                if time_sched is not None:
                    shift_cal(place_key, target_date_str, col_idx, s_info, others, time_sched, all_final_rows)
                
    return all_final_rows

def pdf_reader(pdf_stream, target_staff):
    """
    基本事項の『iloc(0,0)からの勤務地特定』ロジックを実装。
    中央の行を勤務地名として採用する。
    """
    clean_target = normalize_text(target_staff)
    pdf_stream.seek(0)
    with open("temp.pdf", "wb") as f: f.write(pdf_stream.getbuffer())
    try:
        tables = camelot.read_pdf("temp.pdf", pages='all', flavor='lattice')
    except: return {}
    
    table_dictionary = {}
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # --- 基本事項準拠の勤務地特定 ---
        text = str(df.iloc[0, 0])
        lines = text.splitlines()
        # 改行数 // 2 をインデックスとして中央の行を取得
        target_index = text.count('\n') // 2
        work_place = lines[target_index].strip() if target_index < len(lines) else (lines[-1].strip() if lines else "Unknown")
        
        search_col = df.iloc[:, 0].astype(str).apply(normalize_text)
        matched_indices = df.index[search_col == clean_target].tolist()
        
        if matched_indices:
            idx = matched_indices[0]
            my_daily = df.iloc[idx : idx + 2, :].copy().reset_index(drop=True)
            others = df.drop([0, idx, idx+1] if idx+1 < len(df) else [0, idx]).copy().reset_index(drop=True)
            table_dictionary[work_place] = [my_daily, others]
            
    return table_dictionary

def data_integration(pdf_dic, time_dic):
    """
    PDFと時程表のマッチング。
    本町のように時程表がない場所も保持する。
    """
    integrated = {}
    for pk, pv in pdf_dic.items():
        match = next((k for k in time_dic.keys() if normalize_text(pk) in normalize_text(k)), None)
        if match:
            integrated[match] = pv + [time_dic[match]]
        else:
            # 時程表なし（本町など）
            integrated[pk] = pv
    return integrated, []
