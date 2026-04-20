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
    ① 時程表を勤務地(シート名)をキーにした辞書として取得。
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

# --- 3. PDF解析 (4/20 確定ロジック組み込み) ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    """
    ② PDFの全ページ・全行をスキャンし、ターゲットの行と他全員の行を抽出。
    勤務地をキーとした辞書に格納する。
    """
    pdf_stream.seek(0)
    # ファイル名から年月を簡易抽出
    year, month = None, None
    nums = re.findall(r'\d+', normalize_text(file_name))
    for n in nums:
        if len(n) == 4: year = int(n)
        if len(n) <= 2: month = int(n)

    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f: f.write(pdf_stream.getbuffer())
    
    pdf_dic = {}
    
    # 解析精度を上げるため lattice と stream 両方を試行
    for flavor in ['lattice', 'stream']:
        try:
            tables = camelot.read_pdf(temp_path, pages='all', flavor=flavor)
        except: continue
        
        for table in tables:
            df = table.df
            if df.empty: continue
            
            # 勤務地判定（0~2行目のヘッダーから）
            header_text = "".join(df.iloc[:3, :].astype(str).values.flatten())
            work_place = "第2ターミナル" if any(x in header_text for x in ["2", "T2", "第2"]) else "免税店"
            
            # 3行目以降を全行スキャン
            start_row = 2 
            for i in range(start_row, len(df)):
                cell_val = str(df.iloc[i, 0])
                found, offset = find_name_and_index_in_cell(target_staff, cell_val)
                
                if found:
                    # 自分の行のみを抽出 (my_daily_shift)
                    my_daily = df.iloc[i : i + 1, :].copy().reset_index(drop=True)
                    # 自分を含む、3行目以降の全スタッフ行 (other_daily_shift)
                    others = df.iloc[start_row:, :].copy().reset_index(drop=True)
                    
                    # 自分の名前セルの位置（何番目の改行か）をメタデータとして保存
                    my_daily.iloc[0, 0] = f"{target_staff}_offset_{offset}"
                    
                    # 勤務地をキーに登録
                    pdf_dic[work_place] = [my_daily, others]
                    st.success(f"✅ '{target_staff}' 様を {work_place} の {i+1} 行目 (段落:{offset+1}) で発見しました。")
                    break
                    
    return pdf_dic, year, month

# --- 4. データ統合 ---
def data_integration(pdf_dic, time_dic):
    """
    ③ 勤務地をキーにして、my_daily, others, time_schedule を紐付ける。
    """
    integrated = {}
    for key in pdf_dic:
        t_sched = time_dic.get(key, pd.DataFrame())
        integrated[key] = [pdf_dic[key][0], pdf_dic[key][1], t_sched]
    return integrated

# --- 5. 詳細シフト計算 (consideration_0.py 完全踏襲) ---
def shift_cal(key, target_date, col, shift_info, other_staff_shift, time_schedule, final_rows):
    time_shift = time_schedule.fillna("").astype(str)
    time_shift.iloc[:, 1] = time_shift.iloc[:, 1].str.strip()
    
    if (time_shift.iloc[:, 1] == shift_info).any():
        final_rows.append([f"{key}_{shift_info}", target_date, "", target_date, "", "True", "", ""])
        my_time_shift = time_shift[time_shift.iloc[:, 1] == shift_info]
        
        if not my_time_shift.empty:
            prev_val = ""
            for t_col in range(2, time_shift.shape[1]):
                current_val = my_time_shift.iloc[0, t_col]
                if current_val != prev_val:
                    if current_val != "":
                        # --- 引取(From)情報の取得 ---
                        taking_over_dept = f"<{current_val}>"
                        mask_t = time_shift.iloc[:, t_col-1] == taking_over_dept
                        codes_t = time_shift.loc[mask_t, time_shift.columns[1]]
                        
                        target_names = []
                        for _, row in other_staff_shift[other_staff_shift.iloc[:, col].isin(codes_t)].iterrows():
                            target_names.append(str(row.iloc[0]).split('\n')[0].strip())
                        
                        taking_over_staff = f"from {','.join(target_names)}" if target_names else ""
                        
                        # --- 引渡(To)情報の取得 ---
                        mask_handing_codes = []
                        if prev_val == "":
                            handing_over_dept = ""
                        else:
                            if final_rows and final_rows[-1][5] == "False":
                                final_rows[-1][4] = time_shift.iloc[0, t_col] # 終了時間
                            handing_over_dept = f"({prev_val})"
                        
                        subject = f"{handing_over_dept} => {taking_over_dept} {taking_over_staff}".strip()
                        final_rows.append([subject, target_date, time_shift.iloc[0, t_col], target_date, "", "False", "", ""])
                    else:
                        # --- 退勤判定 ---
                        if final_rows and final_rows[-1][5] == "False":
                            if (my_time_shift.iloc[0, t_col:] == "").all():
                                final_rows[-1][0] += " => (退勤)"
                            final_rows[-1][4] = time_shift.iloc[0, t_col]
                prev_val = current_val

# --- 6. 画面表示・デバッグ用メイン処理 ---
def main_debug_display(integrated_dic, year, month):
    """
    統合されたデータをループし、3つの表（自分、他人、時程表）を表示して確認する。
    """
    if not integrated_dic:
        st.warning("解析データがありません。")
        return

    for key, data in integrated_dic.items():
        st.subheader(f"📍 勤務地: {key}")
        
        my_daily, others, time_sched = data[0], data[1], data[2]
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("👤 **my_daily_shift (あなたの行)**")
            st.dataframe(my_daily)
            
        with col2:
            st.write("👥 **other_daily_shift (全員の行)**")
            st.dataframe(others)
            
        st.write("⏰ **time_schedule (時程表)**")
        st.dataframe(time_sched)
        
        # 実際にカレンダー行を生成して確認
        st.write("📅 **生成されるカレンダープレビュー (CSV形式)**")
        preview_rows = process_full_month({key: data}, year, month)
        st.dataframe(pd.DataFrame(preview_rows[1:], columns=preview_rows[0]))

def process_full_month(integrated_dic, year, month):
    """1ヶ月分のCSVデータを生成"""
    final_rows = [["Subject", "Start Date", "Start Time", "End Date", "End Time", "All Day Event", "Description", "Location"]]
    if not year or not month: return final_rows
    
    _, last_day = calendar.monthrange(year, month)
    vocation_keywords = ["公", "有", "休", "特", "欠"]

    for day in range(1, last_day + 1):
        target_date = f"{year}/{month:02d}/{day:02d}"
        for place_key, (my_daily, others, time_sched) in integrated_dic.items():
            meta = str(my_daily.iloc[0, 0])
            offset = int(meta.split("_offset_")[-1]) if "_offset_" in meta else 0
            
            # PDFの列構造に合わせ、day番目の列（1日目はindex1以降）を確認
            # ※ camelotの抽出結果により列番号がズレる可能性があるため、安全策をとる
            col_idx = day
            if col_idx >= my_daily.shape[1]: continue
            
            raw_val = str(my_daily.iloc[0, col_idx])
            val_lines = raw_val.split('\n')
            shift_text = val_lines[offset].strip() if offset < len(val_lines) else raw_val

            shifts = re.findall(r'[A-Z\d]+|[公有休特欠]', shift_text)
            for s_info in shifts:
                if any(k in s_info for k in vocation_keywords):
                    final_rows.append([f"【{s_info}】", target_date, "", target_date, "", "True", "休暇", place_key])
                elif not time_sched.empty:
                    shift_cal(place_key, target_date, col_idx, s_info, others, time_sched, final_rows)
    return final_rows
