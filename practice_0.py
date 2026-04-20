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
    text = unicodedata.normalize('NFKC', text)
    # 比較用には空白を消すが、改行 \n は構造解析に使うためここでは残す
    return text

def find_name_in_cell_and_offset(target_name, cell_text):
    """
    セル内の改行を数えて、名前が「何番目」に登場するかを判定する。
    戻り値: (見つかったか, 相対的な行オフセット)
    """
    clean_target = re.sub(r'[\s　]', '', normalize_text(target_name)).lower()
    # セルを改行で分割し、空要素を除去してリスト化
    lines = [l.strip() for l in cell_text.split('\n') if l.strip()]
    
    for idx, line in enumerate(lines):
        clean_line = re.sub(r'[\s　]', '', line).lower()
        # 名字または名前が含まれているか
        if clean_target in clean_line or clean_target[:2] in clean_line:
            # 1つのセルに2人入っている構造（例: 嵯峨根 \n 大喜多）の場合、
            # 1人目ならオフセット0, 2人目ならオフセット1を返すイメージ
            # PDFのシフト行が名前の行と1対1で対応しているか、2行1セットかにより調整
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

# --- 4. シフト詳細計算 ---
def shift_cal(key, target_date, col_idx, shift_info, other_staff_shift, time_schedule, final_rows):
    my_time_shift = time_schedule[time_schedule.iloc[:, 1].astype(str) == shift_info]
    if not my_time_shift.empty:
        prev_val = ""
        for t_col in range(2, time_schedule.shape[1]):
            current_val = str(my_time_shift.iloc[0, t_col])
            if current_val.lower() in ['nan', 'none']: current_val = ""
            if current_val != prev_val:
                if current_val != "":
                    mask_t = (time_schedule.iloc[:, t_col].astype(str) == current_val) & (time_schedule.iloc[:, 1] != shift_info)
                    target_codes = time_schedule.loc[mask_t, time_schedule.columns[1]].tolist()
                    target_rows = other_staff_shift[other_staff_shift.iloc[:, col_idx].isin(target_codes)]
                    names = [str(n).split('\n')[0].strip() for n in target_rows.iloc[:, 0].unique() if n and str(n).lower() != 'nan']
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
            col_idx = day 
            if col_idx >= my_daily.shape[1]: continue
            shift_val = str(my_daily.iloc[0, col_idx]).strip()
            if not shift_val or shift_val.lower() == 'nan': continue
            
            # シフトセル内も改行で分かれている場合があるため、適切に分割
            # (名前がセル内2番目なら、シフトも2番目の要素を取るなどの処理)
            lines = [l.strip() for l in shift_val.split('\n') if l.strip()]
            # 基本は最初の要素、複数あればオフセットに合わせる（要調整）
            current_s_text = lines[0] if lines else ""
            
            shifts = re.findall(r'[A-Z\d]+|公|有|明', current_s_text)
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
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
        except: continue
        for table in tables:
            df = table.df
            if df.empty: continue
            is_valid, msg, work_place = verify_pdf_calendar(df, year, month)
            if not is_valid: continue

            for i in range(len(df)):
                cell_content = str(df.iloc[i, 0])
                found, offset = find_name_in_cell_and_offset(target_staff, cell_content)
                
                if found:
                    # 発見！
                    # my_daily は、その人のシフト行（このPDF構造だと名前の行と同一）
                    # 1つのセルに2人いる場合、shift_valの取り方を工夫する必要がある
                    my_daily = df.iloc[i : i + 1, :].copy().reset_index(drop=True)
                    others = df.drop(index=[i]).copy().reset_index(drop=True)
                    
                    # 内部で「何番目の名前か」を my_daily に持たせておく（後の抽出用）
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{offset}"
                    
                    table_dictionary[work_place] = [my_daily, others]
                    st.success(f"🎯 構造解析により '{target_staff}' 様を特定しました（{work_place}）")
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
