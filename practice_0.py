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
    return text

def find_name_and_index_in_cell(target_name, cell_text):
    """
    4/20ロジック：セル内を改行で分割し、ターゲット名が「何番目の要素」か(offset)を返す。
    """
    if not cell_text: return False, 0
    clean_target = re.sub(r'[\s　]', '', normalize_text(target_name)).lower()
    if not clean_target: return False, 0
    
    lines = cell_text.split('\n')
    for idx, line in enumerate(lines):
        clean_line = re.sub(r'[\s　]', '', normalize_text(line)).lower()
        # 完全一致または名字(2文字以上)での部分一致
        if clean_target in clean_line or clean_line in clean_target:
            return True, idx
        if len(clean_target) >= 2 and clean_target[:2] in clean_line:
            return True, idx
    return False, 0

# --- 2. 時程表の取得 (Google Drive) ---
def time_schedule_from_drive(service, file_id):
    """
    時程表を勤務地(シート名)をキーにした辞書として取得。
    """
    try:
        request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        all_sheets = pd.read_excel(fh, sheet_name=None, header=None, engine='openpyxl')
        return {k: v.fillna('') for k, v in all_sheets.items()}
    except Exception as e:
        st.error(f"時程表取得エラー: {e}")
        return {}

# --- 3. PDF解析 (勤務地自動取得 + 4/20 確定ロジック) ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    """
    PDFから勤務地を自動判別し、ターゲットの行(my_daily)と他全員の行(others)を抽出。
    """
    pdf_stream.seek(0)
    year, month = None, None
    nums = re.findall(r'\d+', normalize_text(file_name))
    for n in nums:
        if len(n) == 4: year = int(n)
        if len(n) <= 2: month = int(n)

    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    pdf_dic = {}
    
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
        except: continue
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # --- 勤務地キーの自動取得ロジック ---
            # consideration_0.pyに基づき、左上のセル周辺から勤務地(T1, T2, 羽田等)を取得
            possible_keys = [str(df.iloc[0,0]), str(df.iloc[1,0]), str(df.iloc[0,1])]
            work_place = "不明"
            for pk in possible_keys:
                clean_pk = pk.replace('\n', '').strip()
                if clean_pk and not any(x in clean_pk for x in ["警備", "勤務", "202"]):
                    work_place = clean_pk
                    break
            
            # 3行目以降をスキャン
            start_row = 2 
            for i in range(start_row, len(df)):
                cell_val = str(df.iloc[i, 0])
                found, offset = find_name_and_index_in_cell(target_staff, cell_val)
                
                if found:
                    # 自分の行 (my_daily_shift)
                    my_daily = df.iloc[i : i + 1, :].copy().reset_index(drop=True)
                    # 他全員の行 (other_daily_shift)
                    others = df.iloc[start_row:, :].copy().reset_index(drop=True)
                    
                    # 4/20ロジックの肝: offsetを保存
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{offset}"
                    
                    pdf_dic[work_place] = [my_daily, others]
                    st.info(f"📍 勤務地「{work_place}」として解析を開始します（{i+1}行目に発見）")
                    break
                    
    return pdf_dic, year, month

# --- 4. データ統合 ---
def data_integration(pdf_dic, time_dic):
    integrated = {}
    for key in pdf_dic:
        t_sched = time_dic.get(key, pd.DataFrame())
        integrated[key] = [pdf_dic[key][0], pdf_dic[key][1], t_sched]
    return integrated

# --- 5. 詳細シフト計算 (アップロードされた consideration.py のロジック) ---
def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    time_shift = time_schedule.fillna("").astype(str)
    # 時程表の2列目（インデックス1）がシフトコード
    if (time_shift.iloc[:, 1] == shift_info).any():
        final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", ""])
        
        my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]

        if not my_time_shift.empty:
            prev_val = ""
            for t_col in range(2, my_time_shift.shape[1]):
                current_val = my_time_shift.iloc[0, t_col]
                
                if current_val != prev_val:
                    if current_val != "": 
                        # --- 引取(From)情報の取得 ---
                        taking_over_dept = f"<{current_val}>"
                        mask_t = time_shift.iloc[:, t_col-1] == taking_over_dept
                        codes_t = time_shift.loc[mask_t, time_shift.columns[1]] 
                        target_names = other_staff_shift[other_staff_shift.iloc[:, col].isin(codes_t)].iloc[:,0].tolist()
                        # 名前部分のみ抽出
                        taking_over_staff = f"from {','.join([n.split()[0] for n in target_names])}" if target_names else ""
                        
                        # --- 引渡(To)情報の取得 ---
                        handing_over_dept = f"({prev_val})" if prev_val != "" else ""
                        if prev_val != "":
                            if final_rows and final_rows[-1][5] == "False":
                                final_rows[-1][4] = time_shift.iloc[0, t_col] # 前の終了時間
                        
                        # 交代相手(To)の検索ロジック
                        mask_h_dept = time_shift.iloc[:, t_col] == prev_val
                        codes_h = time_shift.loc[mask_h_dept, time_shift.columns[1]]
                        handing_names = other_staff_shift[other_staff_shift.iloc[:, col].isin(codes_h)].iloc[:,0].tolist()
                        handing_over_staff = f"to {','.join([n.split()[0] for n in handing_names])}" if handing_names else ""

                        subject = f"{handing_over_dept} {handing_over_staff}=>{taking_over_dept} {taking_over_staff}".strip()
                        final_rows.append([subject.replace("  ", " "), target_date, time_shift.iloc[0, t_col], target_date, "", "False", "", ""])
                    else:
                        # --- 退勤判定 ---
                        taking_over_department = " => (退勤)" if (my_time_shift.iloc[0, t_col:] == "").all() else ""
                        final_rows[-1][0] += taking_over_department
                        final_rows[-1][4] = time_shift.iloc[0, t_col]    
                prev_val = current_val

# --- 6. デバッグ用表示処理 ---
def main_debug_display(integrated_dic, year, month):
    """
    3つの表（my_daily_shift, other_daily_shift, time_schedule）を表形式で確認
    """
    if not integrated_dic:
        st.warning("解析データがありません。ターゲット名やPDFの内容を確認してください。")
        return

    for key, data in integrated_dic.items():
        st.markdown(f"### 🔍 検証パネル: {key}")
        
        my_daily, others, time_sched = data[0], data[1], data[2]
        
        # 1. 自分の行
        st.write("📘 **my_daily_shift (抽出されたあなたの行)**")
        st.dataframe(my_daily, use_container_width=True)
        
        # 2. 他人の行
        st.write("📗 **other_daily_shift (交代相手参照用マスタ)**")
        st.dataframe(others, use_container_width=True)
        
        # 3. 時程表
        st.write("🕒 **time_schedule (Spreadsheetからの設定値)**")
        st.dataframe(time_sched, use_container_width=True)
        
        # 4. プレビュー
        st.write("🗓️ **Googleカレンダー用データ変換結果**")
        preview_rows = process_full_month({key: data}, year, month)
        st.dataframe(pd.DataFrame(preview_rows[1:], columns=preview_rows[0]), use_container_width=True)

def process_full_month(integrated_dic, year, month):
    final_rows = [["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]]
    if not year or not month: return final_rows
    _, last_day = calendar.monthrange(year, month)
    
    for day in range(1, last_day + 1):
        target_date = f"{year}/{month:02d}/{day:02d}"
        for place_key, (my_daily, others, time_sched) in integrated_dic.items():
            meta = str(my_daily.iloc[0, 0])
            offset = int(meta.split("_offset_")[-1]) if "_offset_" in meta else 0
            
            col_idx = day # 日付列の調整
            if col_idx >= my_daily.shape[1]: continue
            
            raw_val = str(my_daily.iloc[0, col_idx])
            val_lines = raw_val.split('\n')
            shift_text = val_lines[offset].strip() if offset < len(val_lines) else raw_val

            shifts = re.findall(r'[A-Z\d]+|[公有休特欠]', shift_text)
            for s_info in shifts:
                if any(k in s_info for k in ["公", "有", "休", "特", "欠"]):
                    final_rows.append([f"【{s_info}】", target_date, "", target_date, "", "True", "休暇", place_key])
                elif not time_sched.empty:
                    shift_cal(place_key, target_date, col_idx, s_info, others, time_sched, final_rows)
    return final_rows
