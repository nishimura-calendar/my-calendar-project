import streamlit as st
import pandas as pd
import io
import pdfplumber
import re
import calendar
import unicodedata
from googleapiclient.discovery import build
from streamlit_pdf_viewer import pdf_viewer
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from google.auth.transport.requests import Request

# --- [1] 時程表読み込み・整形 ---
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

@st.cache_data(ttl=600)
def load_and_process_data():
    creds_dict = st.secrets["google_oauth_credentials"]
    creds = Credentials(**creds_dict)
    
    # --- 認証切れ対策コード ---
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    # --------------------------
    
    service = build('drive', 'v3', credentials=creds)
    file_id = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    while not downloader.next_chunk()[1]: pass
    fh.seek(0)
    df = pd.read_excel(fh, header=None, engine='openpyxl', dtype=str)
    return process_data(df)

# --- [2] PDF表示関数 ---
def display_pdf(uploaded_file):
    uploaded_file.seek(0)
    pdf_bytes = uploaded_file.read()
    pdf_viewer(input=pdf_bytes, width=700)

import re

def extract_name_safely(full_text):
    """
    行全体のテキストから「人名」と思われる最初の部分だけを抜き出す
    """
    # 1. パイプ記号や不要な記号を除去
    clean_text = full_text.replace("|", " ").strip()
    
    # 2. 複数のスペースを1つのスペースに正規化
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    # 3. スペースで分割してパーツに分ける
    parts = clean_text.split(' ')
    
    # 4. 「最初のパーツ」が人名（姓）、「2番目のパーツ」が名（もしあれば）
    # 資格などの不要データは、3番目以降のパーツとして無視する
    if len(parts) >= 2:
        # スペースがあってもなくても、最初の2つのパーツを結合して返す
        # 例: ["水野", "順三", "資格"] -> "水野 順三"
        # 例: ["岸田", "貢", "資格"] -> "岸田 貢"
        return f"{parts[0]} {parts[1]}"
    
    # スペースがない場合（パーツが1つしかない場合）
    # 例: "岸田貢" -> "岸田貢"
    return parts[0]

def extract_staff_names_below_key(page, key_text):
    # (中略: candidate_wordsの抽出処理は以前と同じ)
    # ...
    
    staff_list = []
    for y, full_text in grouped.items():
        # 行全体のテキストから名前部分だけを抽出
        name = extract_name_safely(full_text)
        
        # 不要行（曜日・シフト記号行）の判定
        is_invalid = any(bl in name for bl in ["教育", "研修", "同伴", "資格", "本町"])
        
        # 抽出: 2文字以上かつKey以外ならリストに追加
        if len(name.replace(" ", "")) >= 2 and name != key_text and not is_invalid:
            if name not in staff_list:
                staff_list.append(name)
    return staff_list
    
# --- [3] メイン処理 ---
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
        display_pdf(uploaded_pdf)
        st.stop()
    
    # (2)②~⑤ 整合性データの抽出
    with pdfplumber.open(uploaded_pdf) as pdf:
        words = pdf.pages[0].extract_words()
        date_words = [w for w in words if re.match(r'^(0?[1-9]|[12][0-9]|3[01])$', w['text'])]
        day_words = [w for w in words if w['text'] in "日月火水木金土"]
        
        last_date_obj = sorted(date_words, key=lambda x: int(x['text']))[-1]
        A_date = int(last_date_obj['text'])
        candidates = [w for w in day_words if abs(w['x0'] - last_date_obj['x0']) < 15]
        A_day = candidates[0]['text'] if candidates else "不明"

    # 年月の確定
    filename = uploaded_pdf.name
    year_match = re.search(r'(\d{4})', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    
    if year_match and month_match:
        y, m = int(year_match.group(1)), int(month_match.group(1))
        label_b = "ファイル名から算出"
    else:
        # ご要望のメッセージを表示
        st.warning("シフト表の年月が確認できません。下記フォームに入力後、年月確定ボタンを押して下さい。")
        y = st.number_input("年", min_value=2000, max_value=2100, value=2026)
        m = st.number_input("月", min_value=1, max_value=12, value=3)
        label_b = "手動入力"
        if not st.button("年月確定"):
            st.stop()
            
    # (2)⑥⑦ 整合性判定
    _, last_day = calendar.monthrange(y, m)
    last_day_w = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(y, m, last_day)]
    
    if A_date == last_day and A_day == last_day_w:
        # ⑥ 整合時：無言通過（何も表示せず次の処理へ）
        pass
    else:
        # ⑦ 不整合時：エラー表示＋PDF表示＋停止
        st.write(f"A：抽出結果 ＝ {A_date}日({A_day}曜日)")
        st.write(f"B：{label_b} ＝ {last_day}日({last_day_w}曜日)")
        st.error("整合性が不一致です。")
        display_pdf(uploaded_pdf)
        st.stop()

    # ここまで通過すれば解析成功
    st.success("第2関門通過")
    with pdfplumber.open(uploaded_pdf) as pdf:
        page = pdf.pages[0]
        # 修正：定義した関数名に変更
        staff_list = extract_staff_names_below_key(page, found_key)
        
        # デバッグ：何が取れているか確認用
        if not staff_list:
            st.write("人名が見つかりません。PDFの構造を確認中...")
        
        st.write("次の中から、target_staff（あなた）を選んで下さい。")
        target_staff = st.selectbox("スタッフを選択", staff_list)
