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

# --- 1. テキストの正規化（全角・半角・改行の壁をなくす） ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 全角を半角に、濁点を結合
    text = unicodedata.normalize('NFKC', text)
    # 改行、空白、記号を完全に消し去る
    clean = re.sub(r'[\s　\n\r\t\.\,・\-|_]', '', text).lower()
    return clean

def is_name_match(target_name, text_to_check):
    """
    ターゲットの名前（例：西村文宏）が、セルの塊（例：大喜多晃\n西村文宏）の中に
    含まれているかを判定します。
    """
    clean_target = normalize_text(target_name)
    clean_cell = normalize_text(text_to_check)
    
    if not clean_target or not clean_cell:
        return False
        
    # 方法1: 名前がまるごと含まれているか（スペース無視）
    if clean_target in clean_cell:
        return True
    
    # 方法2: 名字（最初の2文字）が含まれているか
    surname = clean_target[:2]
    if surname in clean_cell:
        return True
        
    return False

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
    # 広めに探す（15行目まで）
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

# --- 4. シフト計算ロジック（そのまま） ---
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
            shifts = re.findall(r'[A-Z\d]+|公|有|明', shift_val)
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
                # 名前が含まれているかチェック（行全体を結合して探す）
                row_full_text = "".join(df.iloc[i, :].astype(str))
                if is_name_match(target_staff, row_full_text):
                    # 発見：西村さんのデータ（2行セット）を抽出
                    my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                    # 他の人のデータを抽出
                    others = df.drop(index=[i, i+1] if i+1 < len(df) else [i]).copy().reset_index(drop=True)
                    table_dictionary[work_place] = [my_daily, others]
                    st.success(f"🎯 西村様のデータを自動検出しました（行 {i}）")
                    return table_dictionary, year, month

    # 万が一見つからない場合
    st.warning(f"'{target_staff}' 様を特定できませんでした。")
    with st.expander("🛠️ 手動指定（最終手段）"):
        manual_row = st.number_input("行番号を入力", min_value=0, value=20)
        if st.button("この行で確定する"):
            my_daily = df.iloc[manual_row : manual_row + 2, :].copy().reset_index(drop=True)
            others = df.drop(index=[manual_row, manual_row+1] if manual_row+1 < len(df) else [manual_row]).copy().reset_index(drop=True)
            table_dictionary[work_place] = [my_daily, others]
            return table_dictionary, year, month
        for r in range(len(df)):
            st.text(f"行 {r}: {str(df.iloc[r, 0])[:50]}")
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
