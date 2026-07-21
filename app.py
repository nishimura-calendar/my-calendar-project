import streamlit as st
import pandas as pd
import camelot
import re
import calendar
from datetime import datetime

def get_pdf_metadata(file_path, file_name):
    """
    [解析ロジック]
    1. 最初のkey（T1/T2）が出現した行を起点とする。
    2. それ以降の行を順次走査し、日付数値または曜日が含まれる行のみを抽出。
    3. 日付・曜日以外の文字（人名など）がメインの行に到達した時点で抽出終了。
    """
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    full_df = pd.concat([t.df for t in tables], ignore_index=True)
    
    max_date = 0
    in_block = False
    block_data = []
    
    # 曜日パターン
    weekday_pattern = re.compile(r'[月火水木金土日]')
    # 日付数値パターン（1-31）
    date_num_pattern = re.compile(r'\b([12]?\d|3[01])\b')
    
    for _, row in full_df.iterrows():
        # 行内の全セルを結合し、改行をスペースに置換
        row_str = " ".join([str(v) for v in row]).replace('\n', ' ').strip()
        if not row_str: continue
        
        # 1. 最初のkeyが出現したら解析開始フラグを立てる
        if not in_block and re.search(r'T[12]', row_str):
            in_block = True
            continue
            
        # 2. 解析開始後の範囲判定
        if in_block:
            # 「日付」または「曜日」が含まれているか
            has_date = bool(date_num_pattern.search(row_str))
            has_weekday = bool(weekday_pattern.search(row_str))
            
            # 日付か曜日の情報がある場合は抽出対象
            if has_date or has_weekday:
                block_data.append(row_str)
            else:
                # 日付・曜日情報がない行（＝人名やシフト記号のみの行）が出たら終了
                # ただし、T1/T2自体が再出現した場合は継続、あるいは終了とみなすか要件による
                # ここでは「データ部以外の情報が出たら終了」というルールを適用
                in_block = False
    
    # 3. 最大日付の算出
    all_nums = [int(n) for line in block_data for n in date_num_pattern.findall(line)]
    max_date = max(all_nums) if all_nums else 0
    
    # 4. 最終曜日の算出
    # ファイル名から年月を取得（例: 2026年1月度）
    match = re.search(r'(\d{4})年?(\d{1,2})月', file_name)
    year = int(match.group(1)) if match else datetime.now().year
    month = int(match.group(2)) if match else datetime.now().month
    
    last_weekday = "不明"
    if max_date > 0:
        try:
            last_weekday = ["月", "火", "水", "木", "金", "土", "日"][calendar.weekday(year, month, max_date)]
        except:
            last_weekday = "算出不可"
    
    return max_date, last_weekday

# --- Streamlit UI部 ---
def main():
    st.title("シフト整合性チェックシステム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file is not None:
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        try:
            max_date, last_weekday = get_pdf_metadata("temp.pdf", uploaded_file.name)
            st.write(f"### 解析結果")
            st.write(f"- 最大日付: **{max_date}日**")
            st.write(f"- 最終曜日: **{last_weekday}曜日**")
        except Exception as e:
            st.error(f"解析エラー: {e}")

if __name__ == "__main__":
    main()
