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

# --- 1. テキストの正規化（ノイズ除去と全角半角統一） ---
def normalize_text(text):
    if not isinstance(text, str): return ""
    # 全角を半角に変換
    text = unicodedata.normalize('NFKC', text)
    # 改行、空白、タブ、特定の記号を完全に削除
    clean = re.sub(r'[\s　\n\r\t\.\,・-]', '', text).lower()
    return clean

def is_name_match(target_name, cell_text):
    """
    名前のヒット率を最大化するロジック
    PDF抽出時に名字と名前が逆転したり、間にノイズ(Cなど)が入る場合に対応
    """
    clean_target = normalize_text(target_name)
    clean_cell = normalize_text(cell_text)
    
    if not clean_target or not clean_cell:
        return False
        
    # パターン1: そのまま含まれているか
    if clean_target in clean_cell:
        return True
    
    # パターン2: 名字と名前を入れ替えて判定（例: 文宏西村）
    if len(clean_target) >= 4:
        # 名字2文字、名前2文字を想定した入れ替え
        reversed_name = clean_target[2:] + clean_target[:2]
        if reversed_name in clean_cell:
            return True

    # パターン3: 包含判定（ターゲットの各文字がバラバラでも全て含まれているか）
    # 西村文宏の「西」「村」「文」「宏」が全てセル内に存在すればOK
    match_count = sum(1 for char in clean_target if char in clean_cell)
    if match_count == len(clean_target):
        return True
            
    return False

# --- 2. ファイル名から「期待値」を取得 ---
def extract_year_month_from_filename(file_name):
    if not file_name: return None, None
    text = normalize_text(file_name)
    y_val, m_val = None, None
    
    month_match = re.search(r'(\d{1,2})月', text)
    if month_match:
        m_val = int(month_match.group(1))
    
    nums = re.findall(r'\d+', text)
    for n in nums:
        if len(n) == 4:
            y_val = int(n)
            break
    return y_val, m_val

# --- 3. カレンダー整合性チェックと結果表示 ---
def verify_pdf_calendar(df, expected_year, expected_month):
    """
    ファイル名から算出した「正解」と、PDF内容から抽出した「実測値」を比較表示する
    """
    if not expected_year or not expected_month:
        return False, "年月特定不能", "Unknown"

    # カレンダー上の正解（期待値）
    first_wday_idx, last_day = calendar.monthrange(expected_year, expected_month)
    weekdays_jp = ["月", "火", "水", "木", "金", "土", "日"]
    expected_first_wday = weekdays_jp[first_wday_idx]
    
    # PDFからの抽出（実測値）
    pdf_days = []
    # 1行目をスキャンして数字と曜日を探す
    for col in range(1, df.shape[1]):
        cell_val = str(df.iloc[0, col])
        d_match = re.search(r'(\d+)', cell_val)
        w_match = re.search(r'([月火水木金土日])', cell_val)
        if d_match and w_match:
            pdf_days.append({"d": int(d_match.group(1)), "w": w_match.group(1)})

    if not pdf_days:
        return False, "日付行が認識できません", "Unknown"

    actual_max_day = max([x["d"] for x in pdf_days])
    day_one = next((x for x in pdf_days if x["d"] == 1), None)
    actual_first_wday = day_one["w"] if day_one else "不明"

    # --- UI表示 ---
    st.markdown("### 📊 ファイル整合性チェック")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**【ファイル名（期待値）】**")
        st.write(f"対象: {expected_year}年{expected_month}月")
        st.write(f"日数: {last_day}日間")
        st.write(f"1日の曜日: {expected_first_wday}")
    with col2:
        st.write("**【PDFデータ（実測値）】**")
        st.write(f"最大日数: {actual_max_day}日")
        st.write(f"読み取れた1日: {actual_first_wday}")

    is_match = (actual_max_day == last_day) and (actual_first_wday == expected_first_wday)
    
    if is_match:
        st.success("✅ ファイル名と中身のカレンダーが一致しました。")
    else:
        st.error("❌ カレンダーの整合性が取れません。ファイルを確認してください。")

    header_cell = str(df.iloc[0, 0])
    work_place = header_cell.splitlines()[len(header_cell.splitlines())//2].strip() if header_cell else "Unknown"

    return is_match, "OK", work_place

# --- 4. メイン解析 ---
def pdf_reader(pdf_stream, target_staff, file_name=""):
    pdf_stream.seek(0)
    year, month = extract_year_month_from_filename(file_name)
    
    temp_path = "temp_process.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_stream.getbuffer())
    
    try:
        tables = camelot.read_pdf(temp_path, pages='all', flavor='lattice')
    except Exception as e:
        st.error(f"解析失敗: {e}")
        return {}, year, month

    table_dictionary = {}
    
    for table in tables:
        df = table.df
        if df.empty: continue
        
        # 1. カレンダーの照合
        is_valid, _, work_place = verify_pdf_calendar(df, year, month)
        if not is_valid: continue

        # 2. ターゲットの検索（包含判定・逆転対応）
        found = False
        for i in range(len(df)):
            cell_text = str(df.iloc[i, 0])
            if is_name_match(target_staff, cell_text):
                # 発見：自分用2行、他人用は1行として抽出
                my_daily = df.iloc[i : i + 2, :].copy().reset_index(drop=True)
                others = df.drop([0, i, i+1] if i+1 < len(df) else [0, i]).copy().reset_index(drop=True)
                table_dictionary[work_place] = [my_daily, others]
                found = True
                break
        
        if found:
            st.success(f"👤 '{target_staff}' さんのデータを抽出しました。")
                
    return table_dictionary, year, month

def time_schedule_from_drive(service, spreadsheet_id):
    try:
        request = service.files().export_media(fileId=spreadsheet_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return pd.read_excel(fh, header=None, engine='openpyxl').fillna('')
    except:
        return pd.DataFrame()
