import streamlit as st
import pandas as pd
import camelot
import re
import calendar
from datetime import datetime

# --- [1] 時程表読込 (表示はしない) ---
# ※既存のload_and_process_data()関数を前提としています
# data_dict = load_and_process_data() を実行してデータを取得しておく

# --- [2] PDFシフト表読み込みと第1関門 ---
def run_first_gate(uploaded_file, data_dict):
    # (1) camelotを使用して読込
    tables = camelot.read_pdf(uploaded_file, pages='all')
    df = tables[0].df
    
    # (2) 第1関門
    valid_keys = list(data_dict.keys())
    
    # ① 0列目を検索してkeyを検索
    key_found = None
    for k in valid_keys:
        if df.iloc[:, 0].astype(str).str.contains(k).any():
            key_found = k
            break
    
    if not key_found:
        st.error(f"「{key_found}」が見当りません。シフト表ではないようです。ファイルを確認して下さい。")
        st.write(df)
        st.stop()
        
    # ② key行からA（最終日付と最終曜日）を抽出
    # ※シフト表の構造に応じて、key行以降から数字と曜日を正規表現で特定
    def extract_last_info(df, key):
        # keyが含まれる行のインデックス
        idx = df[df.iloc[:, 0].astype(str).str.contains(key)].index[0]
        row_data = " ".join(df.iloc[idx].astype(str))
        # 最終日付の抽出（例：行内の最大数字）
        dates = [int(n) for n in re.findall(r'\d+', row_data) if 1 <= int(n) <= 31]
        last_date = max(dates) if dates else 0
        # 曜日の抽出（簡易的に最後に出現するもの）
        days = re.findall(r'[月火水木金土日]', row_data)
        last_day = days[-1] if days else "不明"
        return last_date, last_day

    A_date, A_day = extract_last_info(df, key_found)
    
    # ③ ファイル名から年月を取得
    match = re.search(r'(\d{4}).*?(\d{1,2})月', uploaded_file.name)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
    else:
        # 取得できない場合は入力フォームを表示
        year = st.number_input("年を入力してください", value=2026)
        month = st.number_input("月を入力してください", value=1)
        
    # ④ B：取得した年月から最終日付と最終曜日を取得
    last_day_num = calendar.monthrange(year, month)[1]
    last_day_obj = datetime(year, month, last_day_num)
    days_list = ["月", "火", "水", "木", "金", "土", "日"]
    B_day = days_list[last_day_obj.weekday()]
    
    # ⑤ A=Bなら通過、⑥ A≠Bならエラー停止
    if A_date == last_day_num and A_day == B_day:
        st.success("ファイルチェックが完了しました。")
    else:
        st.error("エラー：ファイル名とシフト表内の日付・曜日が一致しません。")
        st.write(f"【PDF内（A）】{A_date}日、{A_day}曜日")
        st.write(f"【算出（B）】{last_day_num}日、{B_day}曜日")
        st.write(df)
        st.stop()

# --- メイン実行 ---
st.title("シフトカレンダー登録")
data_dict = load_and_process_data() # [1]の処理を実行
uploaded_file = st.file_uploader("PDFシフト表をアップロードして下さい", type="pdf")

if uploaded_file:
    run_first_gate(uploaded_file, data_dict)
