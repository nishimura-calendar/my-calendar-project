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
    
    # (2)① Keyの特定が完了した後
    # すでに found_key に "T2" 等が代入されている状態です。
    if not found_key:
        st.error("勤務地(Key)がPDFから特定できませんでした。")
        st.stop()
    
    # 【ここが重要】特定された found_key を使って time_schedule を登録します
    # 他のロジックを介さず、辞書から直接取得します
    try:
        time_schedule = st.session_state.data_dict[found_key]
        st.write(f"使用する勤務地データ: {found_key}")
    except KeyError:
        st.error(f"エラー: 辞書内にキー '{found_key}' が存在しません。")
        st.write("登録されているキー一覧:", list(st.session_state.data_dict.keys()))
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
    
    # (3)④〜⑦ 整合性判定
    _, last_day_num = calendar.monthrange(y, m)
    last_day_w = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, last_day_num)]
    
    if A_date == last_day_num and A_day == last_day_w:
        st.success(f"解析成功: {y}年{m}月 ({A_date}日 {A_day}曜日まで確認済み)")
    else:
        st.error("整合性不一致: アップロードされたシフト表の年月が期待値と異なります。")
        st.write(f"抽出された最終日: {A_date}日 ({A_day}曜日)")
        st.write(f"カレンダー上の最終日: {last_day_num}日 ({last_day_w}曜日)")
        st.stop()
# ---------------------------------------------------------
    # 第2関門突破後の表示ロジック (最終統合版)
    # ---------------------------------------------------------
    st.divider()

    # --- 1. インデックスと人名の抽出 ---
    staff_data = []
    for idx in range(0, df_pdf.shape[0], 2):
        name_val = str(df_pdf.iloc[idx, 0])
        # Key行(勤務地)はスキップ
        if name_val in st.session_state.data_dict.keys():
            continue
        
        # 名前は改行までとする
        clean_name = name_val.split('\n')[0] if name_val != 'None' else "該当なし"
        staff_data.append((idx, clean_name))

    # コンボボックス
    target_name = st.selectbox("スタッフを選択してください", [s[1] for s in staff_data])
    target_idx = [s[0] for s in staff_data if s[1] == target_name][0]

    # --- 2. ① my_daily_shift (本人) ---
    st.header("① my_daily_shift")
    my_df = df_pdf.iloc[target_idx : target_idx + 2, :].copy()
    
    # データ行（2行目）の「人名列（0列目）」のみ空白にする
    my_df.iloc[1, 0] = "" 
    st.dataframe(my_df)
    
    csv_my = my_df.to_csv(index=False, header=False).encode('utf-8-sig')
    st.download_button("my_daily_shift.csv をダウンロード", csv_my, "my_daily_shift.csv", "text/csv")

    # --- 3. ② other_daily_shift (人名行のみ・シフト付) ---
    st.header("② other_daily_shift")
    
    other_rows = []
    for idx, name in staff_data:
        if name != target_name:
            # 人名行(idx)のみを抽出して名前をクレンジング
            row = df_pdf.iloc[idx : idx+1].copy()
            row.iloc[0, 0] = name
            other_rows.append(row)
    
    if other_rows:
        other_df = pd.concat(other_rows)
        st.dataframe(other_df)
        
        # CSV出力：人名行のみ（名前＋全シフトデータ）
        csv_other = other_df.to_csv(index=False, header=False).encode('utf-8-sig')
        st.download_button("other_daily_shift.csv をダウンロード", csv_other, "other_daily_shift.csv", "text/csv")

    # --- 4. ③ time_schedule (ソースの表) ---
    st.header("③ time_schedule (ソースの表)")
    if found_key in st.session_state.data_dict:
        st.write(f"勤務地: {found_key}")
        st.table(st.session_state.data_dict[found_key])
