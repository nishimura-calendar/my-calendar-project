import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import streamlit as st
from googleapiclient.http import MediaIoBaseDownload

# --- 1. テキストの正規化 ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[\s　\n]', '', unicodedata.normalize('NFKC', text)).lower()

def find_name_and_index_in_cell(target_name, cell_text):
    if not cell_text: return False, 0
    clean_target = normalize_text(target_name)
    lines = str(cell_text).split('\n')
    for idx, line in enumerate(lines):
        if clean_target in normalize_text(line):
            return True, idx
    return False, 0

# --- 2. 時程表の取得（A列を勤務地として識別） ---
def time_schedule_from_drive(service, file_id):
    """
    時程表の構成ルールを厳守:
    - A列: 勤務地名 (記載がある行が開始点。それ以外は空白)
    - B列: 勤務コード (A, B, C...)
    - C列: ロッカー列
    - D列以降: 時間列 (文字列表記になるまで)
    """
    try:
        request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        
        full_dict = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl', dtype=str)
        location_data_dic = {}
        
        for sheet_name, df in full_dict.items():
            df = df.fillna('')
            # A列(index 0)が空白でない行を勤務地の開始行とする
            location_indices = df[df.iloc[:, 0].str.strip() != ''].index.tolist()
            
            for i, start_idx in enumerate(location_indices):
                end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
                
                work_place_name = normalize_text(df.iloc[start_idx, 0])
                temp_df = df.iloc[start_idx:end_idx, :].copy().reset_index(drop=True)
                
                # 時間列の特定（D列以降、時刻形式または数字である限り継続）
                time_row = temp_df.iloc[0, :]
                valid_time_cols = [0, 1, 2] 
                for col_idx in range(3, len(time_row)):
                    val = str(time_row[col_idx]).strip()
                    if val and (not any(c.isalpha() for c in val) or ":" in val):
                        valid_time_cols.append(col_idx)
                    else:
                        break 
                
                final_time_df = temp_df.iloc[:, valid_time_cols].copy()
                final_time_df.columns = range(len(final_time_df.columns))
                location_data_dic[work_place_name] = final_time_df
                
        return location_data_dic
    except Exception as e:
        raise e

# --- 3. 整合性チェック ---
def check_calendar_consistency(df, year, month):
    if not year or not month:
        return False, "ファイル名から年月を特定できません。"
    
    _, last_day_theory = calendar.monthrange(year, month)
    first_weekday_theory = calendar.weekday(year, month, 1)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    theory_wd_str = weekdays_jp[first_weekday_theory]

    pdf_days = []
    pdf_first_wd = ""
    found_1st = False
    
    for col in range(1, df.shape[1]):
        cell = str(df.iloc[0, col])
        day_match = re.search(r'(\d+)', cell)
        if day_match:
            d_val = int(day_match.group(1))
            pdf_days.append(d_val)
            if d_val == 1 and not found_1st:
                for wd in weekdays_jp:
                    if wd in cell:
                        pdf_first_wd = wd
                        found_1st = True

    pdf_last_day = max(pdf_days) if pdf_days else 0
    errors = []
    if pdf_last_day != last_day_theory:
        errors.append(f"末日不一致(理論:{last_day_theory}/PDF:{pdf_last_day})")
    if pdf_first_wd and pdf_first_wd != theory_wd_str:
        errors.append(f"1日曜日不一致(理論:{theory_wd_str}/PDF:{pdf_first_wd})")
    
    if errors:
        return False, "・".join(errors)
    return True, ""

# --- 4. PDF解析 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = None, None
    nums = re.findall(r'\d+', normalize_text(file_name))
    for n in nums:
        if len(n) == 4: year = int(n)
        if len(n) <= 2: month = int(n)

    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    pdf_results = {}
    consistency_report = {}

    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
            for table in tables:
                df = table.df
                if df.empty: continue
                
                # --- 勤務地特定ロジック：ヘッダー中央付近から抽出 ---
                header_tokens = re.findall(r'[\u4E00-\u9FD5a-zA-Z0-9]+', str(df.iloc[0, 0]))
                work_place_raw = header_tokens[len(header_tokens)//2] if header_tokens else "Unknown"
                work_place = normalize_text(work_place_raw)
                
                # 整合性チェック
                is_ok, reason = check_calendar_consistency(df, year, month)
                if not is_ok:
                    consistency_report[work_place] = {"reason": reason, "df": df}
                    continue

                # ターゲット行の検索
                target_row_idx = -1
                target_offset = 0
                for i in range(len(df)):
                    found, offset = find_name_and_index_in_cell(target_staff, df.iloc[i, 0])
                    if found:
                        target_row_idx = i
                        target_offset = offset
                        break
                
                if target_row_idx != -1:
                    my_daily = df.iloc[target_row_idx : target_row_idx + 2, :].copy()
                    my_daily.columns = range(len(my_daily.columns))
                    my_daily = my_daily.reset_index(drop=True)
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{target_offset}"

                    others = []
                    for i in range(len(df)):
                        if i in [target_row_idx, target_row_idx + 1]: continue
                        row_head = str(df.iloc[i, 0]).strip()
                        
                        # 判定に不要な空行を除外
                        if not row_head: continue
                        
                        # 数字・曜日行を除外するための汎用判定
                        # 1. 数字のみの長い文字列（日付行の誤検知防止）
                        just_nums = re.sub(r'[\s\n　]', '', row_head)
                        if just_nums.isdigit() and len(just_nums) > 5: continue
                        
                        # 2. 短い文字列に曜日が含まれる（曜日行の除外）
                        if any(wd in row_head for wd in ["日", "月", "火", "水", "木", "金", "土"]) and len(row_head) < 5:
                            continue
                            
                        # "勤務予定表" などのタイトル行は、名前が含まれないため自然にスルーされますが
                        # 文字列が含まれる場合は others として登録
                        others.append(df.iloc[i, :])
                    
                    pdf_results[work_place] = [my_daily, pd.DataFrame(others).reset_index(drop=True)]
                    break
            if pdf_results: break
        except Exception:
            continue
            
    return pdf_results, year, month, consistency_report
