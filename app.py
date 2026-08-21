import streamlit as st
import pandas as pd
import io
import pdfplumber
import re
import calendar
import unicodedata
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from google.auth.transport.requests import Request

# --- [1] 時程表読み込み ---
def format_time(val):
    try:
        f_val = float(val)
        h = int(f_val)
        m = int(round((f_val - h) * 60))
        return f"{h}:{m:02d}"
    except (ValueError, TypeError):
        return val

def process_data(df):
    location_data = {}
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else df.index[-1] + 1
        schedule = df.iloc[start_idx:end_idx].copy()
        for col_idx in range(3, schedule.shape[1]):
            val = schedule.iloc[0, col_idx]
            try:
                f_val = float(val)
                schedule.iloc[0, col_idx] = format_time(f_val)
            except (ValueError, TypeError):
                schedule = schedule.iloc[:, :col_idx]
                break
        location_data[key] = schedule
    return location_data

@st.cache_data(ttl=3600)
def load_and_process_data():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    service = build('drive', 'v3', credentials=creds)
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    while not downloader.next_chunk()[1]: pass
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

def get_or_create_calendar(service, calendar_name):
    calendar_list = service.calendarList().list().execute()
    for cal in calendar_list.get('items', []):
        if cal.get('summary') == calendar_name:
            return cal.get('id')
    new_cal = {'summary': calendar_name}
    created_cal = service.calendars().insert(body=new_cal).execute()
    return created_cal.get('id')

def get_color_id(shift_code, time_shift_check=None, found_key=None):
    shift_code_str = str(shift_code)
    if any(holiday in shift_code_str for holiday in ["休", "休日", "公休", "有休", "有給"]): return "11"
    blue_palette = ["7", "9", "1"]
    assigned_blue = "7"
    if found_key:
        hash_val = sum(ord(c) for c in str(found_key))
        assigned_blue = blue_palette[hash_val % len(blue_palette)]
    blue_patterns = ["T1", "T2", "H1", "K2", "A", "B", "C", "D"]
    if any(pattern in shift_code_str for pattern in blue_patterns): return assigned_blue
    if found_key and (found_key in shift_code_str or found_key == shift_code_str): return assigned_blue
    if time_shift_check is not None and not time_shift_check.empty:
        if (time_shift_check.iloc[:, 1] == shift_code_str).any(): return assigned_blue
    if any(k in shift_code_str for k in ["出勤", "退勤", "frm", "to", "▷", "【"]) or "_" in shift_code_str: return assigned_blue
    return "5"

# --- [2] メイン処理 ---
st.title("シフト表解析システム")

if 'data_dict' not in st.session_state:
    st.session_state.data_dict = load_and_process_data()

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_pdf:
    file_bytes = uploaded_pdf.getvalue()
    if 'last_file_bytes' not in st.session_state or st.session_state.last_file_bytes != file_bytes:
        st.session_state.last_file_bytes = file_bytes
        st.session_state.ym_confirmed = False
        for key in ['df_calendar', 'show_conflict_options']:
            if key in st.session_state: del st.session_state[key]

    with pdfplumber.open(uploaded_pdf) as pdf:
        text = unicodedata.normalize('NFKC', pdf.pages[0].extract_text())
        matched_keys = []
        for key in st.session_state.data_dict.keys():
            pos = text.find(str(key))
            if pos != -1: matched_keys.append((key, pos))
        found_key = matched_keys[0][0] if matched_keys else None
    
    if not found_key:
        st.error("勤務地(Key)がPDFから特定できませんでした。")
        st.subheader("アップロードされたファイルの内容:")
        with pdfplumber.open(uploaded_pdf) as pdf:
            st.text_area("PDFの抽出テキスト", value=pdf.pages[0].extract_text(), height=300)
        st.stop()
    
    with pdfplumber.open(uploaded_pdf) as pdf:
        tables = pdf.pages[0].extract_tables()
        df_pdf = pd.DataFrame(tables[0])
        A_date, A_day = None, None
        for row in range(df_pdf.shape[0] - 1):
            for col in range(df_pdf.shape[1]):
                val_up = str(df_pdf.iloc[row, col])
                val_down = str(df_pdf.iloc[row+1, col])
                if re.match(r'^(0?[1-9]|[12][0-9]|3[01])$', val_up) and val_down in "月火水木金土日":
                    A_date, A_day = int(val_up), val_down
        if not A_date:
            st.error("日付と曜日が抽出できませんでした。")
            st.stop()

    filename = uploaded_pdf.name
    year_match = re.search(r'(\d{4})', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    if year_match and month_match:
        y, m = int(year_match.group(1)), int(month_match.group(1))
    else:
        if not st.session_state.get('ym_confirmed', False):
            y = st.number_input("年", min_value=2020, max_value=2030, value=2026, key="manual_y")
            m = st.number_input("月", min_value=1, max_value=12, value=2, key="manual_m")
            if st.button("年月確定"):
                st.session_state.ym_confirmed = True
                st.rerun()
            st.stop()
        else:
            y, m = st.session_state.get('manual_y', 2026), st.session_state.get('manual_m', 2)

    staff_data = []
    for idx in range(0, df_pdf.shape[0], 2):
        name_val = str(df_pdf.iloc[idx, 0])
        if name_val in st.session_state.data_dict.keys(): continue
        clean_name = name_val.split('\n')[0].strip() if name_val != 'None' else "該当なし"
        staff_data.append((idx, clean_name))
        
    target_name = st.selectbox("スタッフを選択", [s[1] for s in staff_data])
    target_idx = [s[0] for s in staff_data if s[1] == target_name][0]

    my_df = df_pdf.iloc[target_idx : target_idx + 2, :].copy()
    my_df.iloc[0, 0] = target_name
    other_rows = [df_pdf.iloc[idx:idx+1].assign(**{0: name}) for idx, name in staff_data if name != target_name]
    other_df = pd.concat(other_rows) if other_rows else pd.DataFrame()

    def get_staff_names(codes, other_staff_shift, col):
        if other_staff_shift.empty: return []
        return other_staff_shift.loc[other_staff_shift.iloc[:, col].isin(codes), other_staff_shift.columns[0]].tolist()
    
    def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
        time_shift = time_schedule.fillna("").astype(str)
        if not (time_shift.iloc[:, 1] == shift_info).any(): return
        my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]
        prev_val, row_data = "", my_time_shift.iloc[0]
        for t_col in range(3, my_time_shift.shape[1]):
            current_val = row_data[t_col]
            if current_val != prev_val:
                if current_val != "":
                    final_rows.append(["", target_date, "", target_date, "", "False", "", found_key])
                    start_time = time_shift.iloc[0, t_col]
                    start = "(出勤)：" if (row_data[3:t_col] == "").all() else ""
                    if row_data[t_col - 1] == "":
                        change = ",".join([f"{n}({time_shift.loc[i, time_shift.columns[t_col-1]]})" 
                                          for i in time_shift.index[(time_shift.iloc[:, t_col-1] != "") & (time_shift.iloc[:, t_col] == "")] 
                                          for n in get_staff_names([time_shift.loc[i, time_shift.columns[1]]], other_staff_shift, col)])
                        change = f"{change}▷" if change else ""
                    else:
                        final_rows[-2][4] = time_shift.iloc[0, t_col]
                        handover = f"to {','.join(get_staff_names(time_shift.loc[time_shift.iloc[:, t_col] == prev_val, time_shift.columns[1]], other_staff_shift, col))}"
                        final_rows[-2][0] += handover
                    takeover = f"from {','.join(get_staff_names(time_shift.loc[time_shift.iloc[:, t_col - 1] == current_val, time_shift.columns[1]], other_staff_shift, col))}【{current_val}】" if get_staff_names(time_shift.loc[time_shift.iloc[:, t_col - 1] == current_val, time_shift.columns[1]], other_staff_shift, col) else f"frm 【{current_val}】"
                    final_rows[-1][0] = start + change + takeover
                    final_rows[-1][2] = start_time
                else:
                    break_change = f"▷{','.join([f'{n}({time_shift.loc[i, time_shift.columns[t_col]]})' for i in time_shift.index[(time_shift.iloc[:, t_col-1] == '') & (time_shift.iloc[:, t_col] != '')] for n in get_staff_names([time_shift.loc[i, time_shift.columns[1]]], other_staff_shift, col)])}"
                    end = "：(退勤)" if (row_data[t_col:] == "").all() else ""
                    handover = f"to {','.join(get_staff_names(time_shift.loc[time_shift.iloc[:, t_col] == prev_val, time_shift.columns[1]], other_staff_shift, col))}"
                    final_rows[-1][0] += handover + break_change + end
                    final_rows[-1][4] = time_shift.iloc[0, t_col]
            prev_val = current_val

    if st.button("カレンダー登録用データを生成"):
        final_rows = []
        time_schedule_df = st.session_state.data_dict[found_key]
        time_shift_check = time_schedule_df.fillna("").astype(str)
        for col in range(1, calendar.monthrange(y, m)[1] + 1):
            s_val, sub_val = str(my_df.iloc[0, col]).strip(), str(my_df.iloc[1, col]).strip()
            if not s_val or s_val == "nan": continue
            if (time_shift_check.iloc[:, 1] == s_val).any():
                final_rows.append([f"{found_key}_{s_val}", f"{y}/{m:02d}/{col:02d}", "", f"{y}/{m:02d}/{col:02d}", "", "True", "", found_key])
                shift_cal(found_key, f"{y}/{m:02d}/{col:02d}", col, s_val, other_df, time_schedule_df, final_rows)
            else:
                final_rows.append([s_val, f"{y}/{m:02d}/{col:02d}", "", f"{y}/{m:02d}/{col:02d}", "", "True", "", s_val])
                if (m_time := re.search(r'(\d+)[^\d]+(\d+)', sub_val)):
                    final_rows.append([s_val, f"{y}/{m:02d}/{col:02d}", f"{m_time.group(1)}:00", f"{y}/{m:02d}/{col:02d}", f"{m_time.group(2)}:00", "False", "", ""])
        st.session_state.df_calendar = pd.DataFrame(final_rows, columns=["Subject", "StartDate", "StartTime", "EndDate", "EndTime", "AllDayEvent", "Description", "Location"])
        st.success("データ生成完了")

    if 'df_calendar' in st.session_state:
        st.download_button("カレンダー登録用CSVをダウンロード", st.session_state.df_calendar.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'), "calendar_import.csv", "text/csv")
        if st.button(f"🚀 {found_key} カレンダーへ新規登録"):
            st.session_state.show_conflict_options = True
        
        if st.session_state.get('show_conflict_options'):
            action = st.radio("処理選択", ["全て削除して登録", "そのまま追加"])
            if st.button("実行"):
                # (登録ロジック)
                st.success("完了しました")
