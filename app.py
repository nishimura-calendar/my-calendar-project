import streamlit as st
from pypdf import PdfReader
import re

# [1] 時程表読込 (マスタデータ取得のシミュレーション)
def get_valid_keys():
    """
    スプレッドシートやマスタファイルからKeyの一覧を取得する関数
    ※現在はデモ用にT1を返します
    """
    return ["T1"]

# [2] PDFシフト表ファイル読込
def process_shift_data(pdf_file, valid_keys):
    # (1) PDF読込: pypdfを使用しテキストを全抽出
    reader = PdfReader(pdf_file)
    full_text = "\n".join([page.extract_text() for page in reader.pages])
    
    # (2) 第1関門: Key検索
    found_key = None
    for key in valid_keys:
        if re.search(rf"\b{re.escape(key)}\b", full_text):
            found_key = key
            break
            
    if not found_key:
        st.error("エラー: シフト表のKeyが見つかりませんでした。ファイルを確認してください。")
        st.stop()
    
    # (3) 第2関門: 日付と曜日の紐付け
    # 行単位で分割し、日付と曜日のパターンを探す
    lines = full_text.split('\n')
    date_line = None
    day_line = None
    
    for line in lines:
        # 日付行の判定: 数字が15個以上並んでいる行を探す
        if len(re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', line)) >= 15:
            date_line = line
        # 曜日行の判定: 曜日文字が15個以上並んでいる行を探す
        if len(re.findall(r'[日月火水木金土]', line)) >= 15:
            day_line = line
            
    if not date_line or not day_line:
        st.error("エラー: 日付行または曜日行が正しく抽出できませんでした。")
        st.stop()
        
    # リスト化
    dates = [int(d) for d in re.findall(r'\b([1-9]|[12][0-9]|3[01])\b', date_line)]
    days = re.findall(r'[日月火水木金土]', day_line)
    
    # 最終日付と曜日の特定
    if not dates or not days:
        st.error("エラー: データ抽出に失敗しました。")
        st.stop()
        
    last_date = dates[-1]
    last_day = days[-1]
    
    return {"key": found_key, "last_date": last_date, "last_day": last_day}

# --- Streamlit UI ---
st.title("シフト表自動読込プログラム")
uploaded_file = st.file_uploader("PDFシフト表ファイルをアップロード", type="pdf")

if uploaded_file:
    keys = get_valid_keys()
    result = process_shift_data(uploaded_file, keys)
    
    if result:
        st.success(f"成功: Key[{result['key']}] を検出しました。")
        st.write(f"最終日付: {result['last_date']}日")
        st.write(f"最終曜日: {result['last_day']}曜日")
