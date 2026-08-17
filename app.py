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
    # ファイルが変更されたら手動確定状態をリセット
    if 'last_uploaded_filename' not in st.session_state or st.session_state.last_uploaded_filename != uploaded_pdf.name:
        st.session_state.last_uploaded_filename = uploaded_pdf.name
        st.session_state.ym_confirmed = False

    # (2)① PDFからキーを検索し、最初に出現するキー（最上部のキー）を判定対象とする
    with pdfplumber.open(uploaded_pdf) as pdf:
        text = unicodedata.normalize('NFKC', pdf.pages[0].extract_text())
        
        matched_keys = []
        for key in st.session_state.data_dict.keys():
            pos = text.find(str(key))
            if pos != -1:
                matched_keys.append((key, pos))
        
        if matched_keys:
            matched_keys.sort(key=lambda x: x[1])
            found_key = matched_keys[0][0]
        else:
            found_key = None
    
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
        if 'manual_y' not in st.session_state:
            st.session_state.manual_y = 2026
        if 'manual_m' not in st.session_state:
            st.session_state.manual_m = 2
        if 'ym_confirmed' not in st.session_state:
            st.session_state.ym_confirmed = False

        if not st.session_state.ym_confirmed:
            st.warning("ファイル名から年月を特定できませんでした。下記を入力して「年月確定」を押してください。")
            st.session_state.manual_y = st.number_input("年を手動入力", min_value=2020, max_value=2030, value=st.session_state.manual_y)
            st.session_state.manual_m = st.number_input("月を手動入力", min_value=1, max_value=12, value=st.session_state.manual_m)
            if st.button("年月確定"):
                st.session_state.ym_confirmed = True
                st.rerun()
            st.stop()
        else:
            y = st.session_state.manual_y
            m = st.session_state.manual_m
    
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
        if name_val in st.session_state.data_dict.keys():
            continue
        
        if name_val != 'None':
            base_name = name_val.split('\n')[0]
            clean_name = re.split(r'[\s ]+(施設|空保|警備|級|研修)|(施設|空保|警備|級|研修)', base_name)[0].strip()
        else:
            clean_name = "該当なし"
            
        staff_data.append((idx, clean_name))

    target_name = st.selectbox("スタッフを選択してください", [s[1] for s in staff_data])
    target_idx = [s[0] for s in staff_data if s[1] == target_name][0]

    # --- 2. ① my_daily_shift (本人) ---
    st.header("① my_daily_shift")
    my_df = df_pdf.iloc[target_idx : target_idx + 2, :].copy()
    
    my_df.iloc[0, 0] = target_name
    my_df.iloc[1, 0] = "" 
    
    st.dataframe(my_df)
    
    csv_my = my_df.to_csv(index=False, header=False).encode('utf-8-sig')
    st.download_button("my_daily_shift.csv をダウンロード", csv_my, "my_daily_shift.csv", "text/csv")

    # --- 3. ② other_daily_shift (人名行のみ・シフト付) ---
    st.header("② other_daily_shift")
    
    other_rows = []
    for idx, name in staff_data:
        if name != target_name:
            row = df_pdf.iloc[idx : idx+1].copy()
            row.iloc[0, 0] = name
            other_rows.append(row)
    
    if other_rows:
        other_df = pd.concat(other_rows)
        st.dataframe(other_df)
        
        csv_other = other_df.to_csv(index=False, header=False).encode('utf-8-sig')
        st.download_button("other_daily_shift.csv をダウンロード", csv_other, "other_daily_shift.csv", "text/csv")

    # --- 4. ③ time_schedule (ソースの表) ---
    st.header("③ time_schedule (ソースの表)")
    if found_key in st.session_state.data_dict:
        st.write(f"勤務地: {found_key} (※PDF内で最初に見つかったキー)")
        st.table(st.session_state.data_dict[found_key])

    # ---------------------------------------------------------
    # [3] カレンダー登録データの生成（consideration_0.py 統合版）
    # ---------------------------------------------------------
    st.divider()
    st.header("③ カレンダー登録データ生成 ([3])")

    def officeschedule(subject_name, start_t, end_t, target_date, final_rows, location_val=""):
        """時間指定イベント（本町など）の登録用関数"""
        final_rows.append([
            subject_name,    # Subject
            target_date,     # StartDate
            start_t,         # StartTime
            target_date,     # EndDate
            end_t,           # EndTime
            "False",         # AllDayEvent
            "",              # Description
            location_val     # Location
        ])

    def get_staff_names(codes, other_staff_shift, col):
        """シフトコードからスタッフ名のリストを取得するヘルパー関数"""
        mask = other_staff_shift.iloc[:, col].isin(codes)
        return other_staff_shift.loc[mask, other_staff_shift.columns[0]].tolist()
    
    def shift_cal(key, target_date, col, shift_info, my_daily_shift, other_staff_shift, time_schedule, final_rows):
        """通常シフトの詳細（時間別引き継ぎ）を計算し、final_rowsに格納する"""
        time_shift = time_schedule.fillna("").astype(str)
        if not (time_shift.iloc[:, 1] == shift_info).any():
            return
           
        my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]
        if my_time_shift.empty:
            return
    
        prev_val = ""
        row_data = my_time_shift.iloc[0]
    
        for t_col in range(3, my_time_shift.shape[1]):
            current_val = row_data[t_col]
    
            # 変数の初期化
            subject = ""
            start = ""
            change = ""
            takeover = ""
            handover = ""
            break_change = ""
            end = ""                    
          
            if current_val != prev_val:
                if current_val != "":
                    final_rows.append([subject, target_date, "", target_date, "", "False", "", ""])
                    start_time = row_data[t_col]
                
                    # 3列目から t_col の1つ手前までの間が全て""なら start="(出勤)："
                    if (row_data[3:t_col] == "").all():
                        start = "(出勤)："
                        
                    if row_data[t_col - 1] == "":              
                        # 勤務_交代
                        mask_change = (time_shift.iloc[:, t_col - 1] != "") & (time_shift.iloc[:, t_col] == "")
                        paired_staff = []
                        for idx in time_shift.index[mask_change]:
                            places = time_shift.loc[idx, time_shift.columns[t_col - 1]]
                            codes = time_shift.loc[idx, time_shift.columns[1]]
                            staff = get_staff_names([codes], other_staff_shift, col)
                            for name in staff:
                                paired_staff.append(f"{name}({places})")       
                        
                        change_formatted = ",".join(paired_staff)
                        change = f"{change_formatted}▷"
                    else:
                        # 前の予定の終了時間をセット
                        final_rows[-2][4] = row_data[t_col]                             
                    
                        # 巡回_引渡
                        handover_codes = time_shift.loc[time_shift.iloc[:, t_col] == prev_val, time_shift.columns[1]]
                        handover_staff = get_staff_names(handover_codes, other_staff_shift, col)
                        handover = f"to {','.join(handover_staff)}"
                        final_rows[-2][0] += handover
                    
                    # 巡回_引継
                    takeover_codes = time_shift.loc[time_shift.iloc[:, t_col - 1] == current_val, time_shift.columns[1]]
                    takeover_staff = get_staff_names(takeover_codes, other_staff_shift, col)
                    takeover = f"frm {','.join(takeover_staff)}【{current_val}】"
    
                    subject = start + change + takeover
                    final_rows[-1][0] = subject
                    final_rows[-1][2] = start_time
                   
                else:
                    # 休憩_交代
                    mask_break = (time_shift.iloc[:, t_col - 1] == "") & (time_shift.iloc[:, t_col] != "")
                    paired_staff = []
                    for idx in time_shift.index[mask_break]:
                        places = time_shift.loc[idx, time_shift.columns[t_col]]
                        codes = time_shift.loc[idx, time_shift.columns[1]]
                        staff = get_staff_names([codes], other_staff_shift, col)
                        for name in staff:
                            paired_staff.append(f"{name}({places})")
    
                    
                    break_formatted = ",".join(paired_staff)
                    break_change = f"▷{break_formatted}"
                                            
                    if (row_data[t_col:] == "").all():
                        end = "(退勤)"
                    end_time = row_data[t_col]
                    
                    # 巡回_引渡
                    handover_codes = time_shift.loc[time_shift.iloc[:, t_col] == prev_val, time_shift.columns[1]]
                    handover_staff = get_staff_names(handover_codes, other_staff_shift, col)
                    handover = f"to {','.join(handover_staff)}"                   
    
                    subject = final_rows[-1][0] + break_change + handover + end
                    final_rows[-1][0] = subject   
                    final_rows[-1][4] = end_time                            
                
            prev_val = current_val
        
    if st.button("カレンダー登録用データを生成"):
        final_rows = []
        holiday_keywords = ["休", "休日", "公休", "有休", "有給"]
        time_schedule_df = st.session_state.data_dict[found_key]
        time_shift_check = time_schedule_df.fillna("").astype(str)

        _, last_day_num = calendar.monthrange(y, m)

        for col in range(1, min(my_df.shape[1], last_day_num + 1)):
            day_num = col
            target_date = f"{y}/{m:02d}/{day_num:02d}"
            
            schedule_val = str(my_df.iloc[0, col]).strip()
            sub_val = str(my_df.iloc[1, col]).strip() if my_df.shape[0] > 1 else ""

            if not schedule_val or schedule_val == "nan":
                continue

            if (time_shift_check.iloc[:, 1] == schedule_val).any():
                # 終日予定
                final_rows.append([
                    f"{found_key}_{schedule_val}", target_date, "", target_date, "", "True", "", found_key
                ])
                # 時間詳細（shift_cal）
                shift_cal(
                    key=found_key,
                    target_date=target_date,
                    col=col,
                    shift_info=schedule_val,
                    my_daily_shift=my_df,
                    other_staff_shift=other_df,
                    time_schedule=time_schedule_df,
                    final_rows=final_rows
                )
            else:
                if any(kw in schedule_val for kw in holiday_keywords):
                    final_rows.append([
                        schedule_val, target_date, "", target_date, "", "True", "", ""
                    ])
                else:
                    if schedule_val == "本町" or "本町" in sub_val or "本町" in schedule_val:
                        time_match = re.search(r'(\d+)[^\d]+(\d+)', sub_val)
                        if time_match:
                            start_t = f"{time_match.group(1)}:00"
                            end_t = f"{time_match.group(2)}:00"
                            officeschedule("本町", start_t, end_t, target_date, final_rows, location_val="本町")
                        else:
                            final_rows.append([
                                schedule_val, target_date, "", target_date, "", "True", "", schedule_val
                            ])
                    else:
                        final_rows.append([
                            schedule_val, target_date, "", target_date, "", "True", "", ""
                        ])

        if final_rows:
            df_calendar = pd.DataFrame(final_rows, columns=["Subject", "StartDate", "StartTime", "EndDate", "EndTime", "AllDayEvent", "Description", "Location"])
            st.success(f"カレンダー登録データの生成が完了しました（計 {len(df_calendar)} 件）")
            st.dataframe(df_calendar)
            
            csv_cal = df_calendar.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button("カレンダー登録用CSVをダウンロード", csv_cal, "calendar_import.csv", "text/csv")
        else:
            st.warning("生成対象のデータがありませんでした。スタッフの選択やシフトデータをご確認ください。")
