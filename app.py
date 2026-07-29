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

# --- [2] メイン処理 ---
st.title("シフト表解析システム")

if 'data_dict' not in st.session_state:
    st.session_state.data_dict = load_and_process_data()

uploaded_pdf = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_pdf:
    # (2)① Keyの特定
    found_key = None
    with pdfplumber.open(uploaded_pdf) as pdf:
        text = unicodedata.normalize('NFKC', pdf.pages[0].extract_text())
        for key in st.session_state.data_dict.keys():
            if str(key) in text:
                found_key = key
                break
    
    if not found_key:
        st.error("勤務地(Key)がPDFから特定できませんでした。")
        st.stop()
    
    # (3)② 整合性データの抽出（表構造解析）
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

    # (3)③ 年月の特定
    filename = uploaded_pdf.name
    year_match = re.search(r'(\d{4})', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    
    if year_match and month_match:
        y, m = int(year_match.group(1)), int(month_match.group(1))
    else:
        st.warning("ファイル名から年月を特定できませんでした。")
        y = st.number_input("年を手動入力", min_value=2020, max_value=2030, value=2026)
        m = st.number_input("月を手動入力", min_value=1, max_value=12, value=7)
        if not st.button("年月確定"):
            st.stop()
    
    _, last_day_num = calendar.monthrange(y, m)
    
    # --- [1] 人名リストの作成と選択 ---
    all_staff_names = []
    for row in range(2, df_pdf.shape[0] - 1):
        name = str(df_pdf.iloc[row, 1]).strip()
        if name != "None" and len(name) >= 2:
            all_staff_names.append(name)
            
    selected_name = st.selectbox("対象の本人（Target Staff）を選択してください", all_staff_names)

    # --- [2] 辞書への登録と振り分け ---
    final_data = {
        found_key: {
            "my_daily_shift": {},
            "other_daily_shift": {},
            "time_schedule": st.session_state.data_dict.get(found_key)
        }
    }

    # PDF抽出済みデータからループして振り分け
    for row in range(2, df_pdf.shape[0] - 1): 
        name = str(df_pdf.iloc[row, 1]).strip()
        if name == "None" or len(name) < 2: continue
            
        if name == selected_name:
            # 本人の場合: 本人行＋下段1行
            my_shifts = [
                df_pdf.iloc[row, 3:3+last_day_num].tolist(),    # 本人行
                df_pdf.iloc[row+1, 3:3+last_day_num].tolist()   # 下段1行
            ]
            final_data[found_key]["my_daily_shift"][name] = my_shifts
        else:
            # その他の場合: 通常のシフト抽出
            shifts = df_pdf.iloc[row, 3:3+last_day_num].tolist()
            final_data[found_key]["other_daily_shift"][name] = shifts

    # --- [3] 結果の表示 ---
    st.write("---")
    st.header(f"解析結果: {found_key}")

    # 1. my_daily_shift 表示
    st.subheader("1. my_daily_shift (本人)")
    st.write(f"選択された本人: {selected_name}")
    st.dataframe(pd.DataFrame(final_data[found_key]["my_daily_shift"][selected_name], index=["本人行", "下段1行"]))

    # 2. other_daily_shift 表示
    st.subheader("2. other_daily_shift (他スタッフ)")
    if final_data[found_key]["other_daily_shift"]:
        df_other = pd.DataFrame.from_dict(final_data[found_key]["other_daily_shift"], orient='index')
        st.dataframe(df_other)

    # 3. time_schedule 表示
    st.subheader("3. time_schedule")
    st.dataframe(final_data[found_key]["time_schedule"])
