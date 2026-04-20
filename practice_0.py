import pandas as pd
import camelot
import unicodedata
import re
import io
import calendar
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# --- 1. テキストの正規化 ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 全角半角を統一し、比較しやすくする
    text = unicodedata.normalize('NFKC', text)
    return text

def find_name_and_index_in_cell(target_name, cell_text):
    """
    西村様提案：0列目のセルを改行で分割し、名前が「何番目」に現れるか（\nの数）を数える。
    戻り値: (見つかったか, 改行によるインデックス)
    """
    if not cell_text: return False, 0
    
    # 検索する名前からスペースを除去
    clean_target = re.sub(r'[\s　]', '', normalize_text(target_name)).lower()
    
    # セル内を改行で分割（空行も構造維持のため含める）
    lines = cell_text.split('\n')
    
    for idx, line in enumerate(lines):
        clean_line = re.sub(r'[\s　]', '', normalize_text(line)).lower()
        # 名前、または名字が含まれているか判定
        if clean_target and (clean_target in clean_line or clean_target[:2] in clean_line):
            return True, idx
            
    return False, 0

# --- 2. ファイル名から年月を取得 ---
def extract_year_month_from_filename(file_name):
    if not file_name: return None, None
    text = normalize_text(file_name)
    y_val, m_val = None, None
    month_match = re.search(r'(\d{1,2})月', text)
    if month_match: m_val = int(month_match.group(1))
    nums = re.findall(r'\d+', text)
    for n in nums:
        if len(n) == 4:
            y_val = int(n)
            break
    return y_val, m_val

# --- 3. カレンダーの整合性チェック ---
def verify_pdf_calendar(df, expected_year, expected_month):
    if not expected_year or not expected_month:
        return False, "年月不明", "Unknown"
    first_wday_idx, last_day = calendar.monthrange(expected_year, expected_month)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_wday = weekdays_jp[first_wday_idx]
    
    pdf_days = []
    for r in range(min(15, len(df))):
        for col in range(df.shape[1]):
            cell_val = str(df.iloc[r, col])
            d_match = re.search(r'(\d+)', cell_val)
            w_match = re.search(r'([月火水木金土日])', cell_val)
            if d_match and w_match:
                pdf_days.append({"d": int(d_match.group(1)), "w": w_match.group(1)})
        if pdf_days: break
    
    if not pdf_days: return False, "日付行不明", "Unknown"
    actual_max_day = max([x["d"] for x in pdf_days])
    day_one = next((x for x in pdf_days if x["d"] == 1), None)
    actual_first_wday = day_one["w"] if day_one else "不明"
    
    is_match = (actual_max_day == last_day) and (actual_first_wday == expected_first_wday)
    header_all = "".join(df.iloc[:3, 0].astype(str))
    work_place = "第2ターミナル" if "2" in header_all or "T2" in header_all else "免税店"
    return is_match, "OK", work_place

# --- 4. シフト詳細計算ロジック ---
def shift_cal(key, target_date, col_idx, shift_info, other_staff_shift, time_schedule, final_rows):
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str) == shift_info]
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = str(my_time_shift.iloc[0, t_col])
            if current_val.lower() in ['nan', 'none']: current_val = ""
            if current_val != prev_val:
                if current_val != "":
                    # 交代相手の検索（他のスタッフのシフトセルからも、改行位置を考慮して抽出）
                    mask_t = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                    target_codes = time_schedule.loc[mask_t, time_schedule.columns[1]].tolist()
                    
                    names = []
                    # 他人の行をスキャン
                    for _, row in other_staff_shift.iterrows():
                        s_cell = str(row.iloc[col_idx]).split('\n')
                        n_cell = str(row.iloc[0]).split('\n')
                        # どの改行位置にコードがあるか特定
                        for s_idx, s_txt in enumerate(s_cell):
                            if any(c in s_txt for c in target_codes):
                                if s_idx < len(n_cell):
                                    names.append(n_cell[s_idx].strip())
                    
                    names = list(set([n for n in names if n]))
                    t_info = f"【{current_val}】" + (f" with {'・'.join(names)}" if names else "")
                    start_t = str(time_schedule.iloc[0, t_col])
                    final_rows.append([t_info, target_date, start_t, target_date, "", "False", "", key])
                else:
                    if final_rows and final_rows[-1][5] == "False":
                        final_rows[-1][4] = str(time_schedule.iloc[0, t_col])
            prev_val = current_val

def process_full_month(integrated_dic, year, month):
    final_rows = [["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]]
    _, last_day = calendar.monthrange(year, month)
    
    for day in range(1, last_day + 1):
        target_date = f"{year}/{month:02d}/{day:02d}"
        for place_key, (my_daily, others, time_sched) in integrated_dic.items():
            # 内部保存したオフセットを取得
            meta = str(my_daily.iloc[0, 0])
            offset = 0
            if "_offset_" in meta:
                offset = int(meta.split("_offset_")[-1])
            
            col_idx = day # 1日がインデックス1に対応
            if col_idx >= my_daily.shape[1]: continue
            
            # シフトセルを改行で分割
            raw_val = str(my_daily.iloc[0, col_idx])
            val_lines = raw_val.split('\n')
            
            # 名前と同じ改行位置のシフト記号を取得
            # 1つのセルに1人しかいない場合はそのまま使う
            shift_text = val_lines[offset] if offset < len(val_lines) else raw_val
            
            shifts = re.findall(r'[A-Z\d]+|公|有|明', shift_text)
            for s_info in shifts:
                if s_info in ["公", "有"]:
                    final_rows.append([f"【{s_info}】", target_date, "", target_date, "", "True", "", place_key])
                else:
                    final_rows.append([f"{place_key}_{s_info}", target_date, "", target_date, "", "True", "", place_key])
                    shift_cal(place_key, target_date, col_idx, s_info, others, time_sched, final_rows)
    return final_rows

# --- 5. PDF解析メイン ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = extract_year_month_from_filename(file_name)
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    table_dictionary = {}
    # Camelotの2種類のエンジンで試行
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
        except: continue
        for table in tables:
            df = table.df
            if df.empty: continue
            is_valid, msg, work_place = verify_pdf_calendar(df, year, month)
            if not is_valid: continue

            # 全行をスキャンして名前を探す
            for i in range(len(df)):
                cell_name_col = str(df.iloc[i, 0])
                # 改行の数に基づいた特定（西村様案）
                found, offset = find_name_and_index_in_cell(target_staff, cell_name_col)
                
                if found:
                    # 発見：その行とインデックスを保持
                    my_daily = df.iloc[i : i + 1, :].copy().reset_index(drop=True)
                    others = df.copy().reset_index(drop=True)
                    
                    # 名前が何個目の \n の後にあったかを記録
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{offset}"
                    
                    table_dictionary[work_place] = [my_daily, others]
                    st.success(f"🎯 '{target_staff}' 様をセル内の {offset + 1} 行目に発見しました。")
                    return table_dictionary, year, month

    return table_dictionary, year, month

def time_schedule_from_drive(service, spreadsheet_id):
    try:
        request = service.files().export_media(fileId=spreadsheet_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        return pd.read_excel(fh, header=None, engine='openpyxl').fillna('')
    except: return pd.DataFrame()
