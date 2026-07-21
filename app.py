import streamlit as st
import pandas as pd
import camelot
import re
import calendar
from datetime import datetime

def get_pdf_metadata(file_path, file_name):
    """
    T1/T2ブロックを検出し、その配下の日付・曜日行のみを抽出して最大日付を算出する
    """
    # PDF全体のテーブルを読み込み
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    full_df = pd.concat([t.df for t in tables], ignore_index=True)
    
    # 抽出用変数
    all_dates = []
    in_block = False
    
    # 判定用パターン
    weekday_pattern = re.compile(r'[月火水木金土日]')
    date_num_pattern = re.compile(r'\b([12]?\d|3[01])\b')
    
    for _, row in full_df.iterrows():
        # 行の結合と整形
        row_str = " ".join([str(v) for v in row]).replace('\n', ' ').strip()
        if not row_str: continue
        
        # 1. key行(T1/T2)の検知 -> ブロック開始
        if re.search(r'T[12]', row_str):
            in_block = True
            continue
            
        # 2. ブロック内での処理
        if in_block:
            # 日付行かどうかを判定（数字または曜日が含まれる行）
            is_data_row = bool(date_num_pattern.search(row_str)) or bool(weekday_pattern.search(row_str))
            
            if is_data_row:
                # 日付パターンに合致する数字をリストに追加
                nums = date_num_pattern.findall(row_str)
                all_dates.extend([int(n) for n in nums])
            else:
                # 曜日も日付もない行＝名前行などに到達 -> ブロック終了
                in_block = False
    
    # 3. 最大日付の特定
    max_date = max(all_dates) if all_dates else 0
    
    # 4. 最終曜日の算出
    # ファイル名から年月を抽出（例: 2026年1月度）
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month
    
    last_weekday = "不明"
    if max_date > 0:
        try:
            # calendar.weekdayは月曜=0, 日曜=6
            weekday_idx = calendar.weekday(year, month, max_date)
            last_weekday = ["月", "火", "水", "木", "金", "土", "日"][weekday_idx]
        except:
            last_weekday = "算出不可"
            
    return max_date, last_weekday

# --- Streamlit UI ---
def main():
    st.title("シフト整合性チェックシステム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file is not None:
        # 一時保存して解析
        temp_path = "temp_shift.pdf"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        try:
            with st.spinner('PDFを解析中...'):
                max_date, last_weekday = get_pdf_metadata(temp_path, uploaded_file.name)
            
            st.success("解析完了")
            st.write(f"### 解析結果")
            st.write(f"- 最大日付: **{max_date}日**")
            st.write(f"- 最終曜日: **{last_weekday}曜日**")
            
        except Exception as e:
            st.error(f"解析中にエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
