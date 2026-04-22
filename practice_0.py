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

# --- 2. 時程表の取得 ---
def time_schedule_from_drive(service, file_id):
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
            location_indices = df[df.iloc[:, 0].str.strip() != ''].index.tolist()
            
            for i, start_idx in enumerate(location_indices):
                end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
                work_place_name = normalize_text(df.iloc[start_idx, 0])
                temp_df = df.iloc[start_idx:end_idx, :].copy().reset_index(drop=True)
                
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

# --- 3. 整合性チェック（抽出精度の向上） ---
def check_calendar_consistency(df, year, month):
    if not year or not month:
        return False, "ファイル名から年月を特定できません。"
    
    _, last_day_theory = calendar.monthrange(year, month)
    first_weekday_theory = calendar.weekday(year, month, 1)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    theory_wd_str = weekdays_jp[first_weekday_theory]

    pdf_days = []
    pdf_first_wd = ""
    
    # 日付行（通常は0行目か1行目）をスキャン
    # 2026などの西暦を除外するため、1〜31の範囲に限定
    for row_idx in range(min(3, len(df))):
        for col_idx in range(1, df.shape[1]):
            cell = str(df.iloc[row_idx, col_idx])
            # 数字のみを抽出
            day_matches = re.findall(r'(\d+)', cell)
            for d_str in day_matches:
                d_val = int(d_str)
                if 1 <= d_val <= 31:
                    pdf_days.append(d_val)
                    if d_val == 1:
                        for wd in weekdays_jp:
                            if wd in cell:
                                pdf_first_wd = wd

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
    # ファイル名から「年(4桁)」と「月(1-2桁)」を厳密に探す
    year_match = re.search(r'(20\d{2})', file_name)
    month_match = re.search(r'(?<!\d)(0?[1-9]|1[0-2])(?![0-9])', file_name.replace(year_match.group(0) if year_match else "", ""))
    
    if year_match: year = int(year_match.group(0))
    if month_match: month = int(month_match.group(0))

    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    pdf_results = {}
    consistency_report = {}

    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
            for table in tables:
                df = table.df
                if df.empty or df.shape[1] < 10: continue # 列が極端に少ないのは無視
                
                # 勤務地特定: セル(0,0)の全テキストから記号を除いた単語リストを作成
                full_text_00 = str(df.iloc[0, 0])
                header_tokens = re.findall(r'[^\s\d\(\)（）\-\/：:、,]+', full_text_00)
                # ユーザー指定ルール: 中央の値
                work_place_raw = header_tokens[len(header_tokens)//2] if header_tokens else "Unknown"
                work_place = normalize_text(work_place_raw)
                
                is_ok, reason = check_calendar_consistency(df, year, month)
                if not is_ok:
                    consistency_report[work_place] = {"reason": reason, "df": df}
                    # 救済措置: もし末日が0なら解析を強行せず報告のみ
                    if "理論" in reason and "PDF:0" in reason:
                        continue

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
                        if not row_head: continue
                        just_nums = re.sub(r'[\s\n　]', '', row_head)
                        if just_nums.isdigit() and len(just_nums) > 5: continue
                        if any(wd in row_head for wd in ["日", "月", "火", "水", "木", "金", "土"]) and len(row_head) < 5:
                            continue
                        others.append(df.iloc[i, :])
                    
                    pdf_results[work_place] = [my_daily, pd.DataFrame(others).reset_index(drop=True)]
                    # 1つ見つかればそのページのlattice/streamループは抜ける
                    break
            if pdf_results: break
        except:
            continue
            
    return pdf_results, year, month, consistency_report
