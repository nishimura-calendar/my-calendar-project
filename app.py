import streamlit as st
import camelot
import pandas as pd
import re
import calendar

# [1] 時程表読み込み（関数化）
@st.cache_data
def load_time_schedule():
    # 実際にはここにCSV読み込み処理が入ります
    return {"T1": "データ...", "T2": "データ..."}

# ユーティリティ: 文字列の正規化（全角半角・空白除去）
def normalize_str(s):
    if not isinstance(s, str): s = str(s)
    s = s.replace(' ', '').replace(' ', '')
    return s.lower()

# [2] PDF読み込みと関門処理
st.title("シフト表読み込み")

uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

if uploaded_file:
    # (1) Camelotで読込
    tables = camelot.read_pdf(uploaded_file, pages='1', flavor='lattice')
    df = tables[0].df
    
    # [1] で登録したkeyを取得
    time_schedule = load_time_schedule()
    keys = list(time_schedule.keys())
    
    # (2) 第1関門: key検索
    found_key = None
    key_idx = -1
    for i, row in df.iterrows():
        cell_val = normalize_str(row[0])
        for k in keys:
            if normalize_str(k) in cell_val:
                found_key = k
                key_idx = i
                break
        if found_key: break
            
    if not found_key:
        st.error(f"「{keys}」が見当りません。シフト表ではないようです。ファイルを確認して下さい。")
        st.dataframe(df)
        st.stop()
    
    # (3) 第2関門
    # ② Key行より上の行を検索範囲とする
    search_df = df.iloc[:key_idx + 1]
    
    # 検索範囲を結合して文字列化
    full_text = " ".join(search_df.stack().astype(str))
    
    # A: 最大日付と最終曜日を抽出
    dates = [int(n) for n in re.findall(r'\d+', full_text) if 1 <= int(n) <= 31]
    A_date = max(dates) if dates else 0
    
    days = re.findall(r'[月火水木金土日]', full_text)
    A_day = days[-1] if days else ""
    
    # ③ ファイル名から年月取得
    file_name = uploaded_file.name
    year_match = re.search(r'20\d{2}', file_name)
    month_match = re.search(r'(\d+)月', file_name)
    
    if year_match and month_match:
        year, month = int(year_match.group()), int(month_match.group(1))
    else:
        # 取得できない場合は入力
        year = st.number_input("年を入力", value=2026)
        month = st.number_input("月を入力", value=1)
        
    # ④ B: 取得した年月から最終日付と曜日を取得
    last_day_num = calendar.monthrange(year, month)[1]
    last_day_weekday = calendar.weekday(year, month, last_day_num)
    weekday_map = ["月", "火", "水", "木", "金", "土", "日"]
    B_day = weekday_map[last_day_weekday]
    
    # ⑤⑥⑦ 判定
    if A_date == last_day_num and A_day == B_day:
        st.success("第②関門通過しました。")
    else:
        st.error(f"判定エラー: A({A_date}日 {A_day}) ≠ B({last_day_num}日 {B_day})")
        st.dataframe(df)
        st.stop()
