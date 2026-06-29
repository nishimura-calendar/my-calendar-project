import streamlit as st
import camelot
import re
import calendar
import os

# --- 関数定義 ---

def get_year_month_from_filename(filename):
    """ファイル名から年と月を抽出する"""
    year_match = re.search(r'20\d{2}', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    year = int(year_match.group(0)) if year_match else None
    month = int(month_match.group(1)) if month_match else None
    return year, month

import re

def get_b_from_pdf(pdf_file_path):
    """
    B: PDF内容から『日本語の曜日』のみを抽出し、その数をカウントする
    """
    try:
        tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
        if not tables: return 0
        
        # 全データを連結して文字列化
        all_text = "".join(tables[0].df.astype(str).values.flatten())
        
        # 正規表現で「日・月・火・水・木・金・土」という文字のみを検索してリスト化
        weekdays_found = re.findall(r'[日月火水木金土]', all_text)
        
        # 曜日が出現した数が、その月の「のべ日数」ではなく「日付の数」になるように考慮
        # 今回のPDFの場合、曜日が表のヘッダー等で重複している可能性があるため、
        # ユニークな出現をカウントする必要があるかもしれません。
        # まずは単純な個数で試します。
        count = len(weekdays_found)
        
        # デバッグ用：抽出されたリストを表示
        st.write(f"検出された曜日リスト({count}個):", weekdays_found)
        
        return count
    except Exception as e:
        st.error(f"PDF読み込みエラー: {e}")
        return 0
        
# --- メイン処理 ---

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    if uploaded_file:
        st.write(f"ファイル名: {uploaded_file.name}")
        year_a, month_a = get_year_month_from_filename(uploaded_file.name)
        
        # 抽出できない場合、ユーザーに入力を求める
if st.button("実行"):
            temp_path = "temp_shift.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # A: 期待される末日
            _, last_day_expected = calendar.monthrange(int(year_a), int(month_a))
            
            last_day_b = get_b_from_pdf(temp_path)
            
            # 第1関門判定
            if last_day_expected == last_day_b:
                st.success(f"第1関門突破！ (日付: {last_day_b}日)")
            else:
                st.error(f"整合性エラー: 期待される日数 {last_day_expected} と、PDF内の曜日数 {last_day_b} が一致しません。")
            
            if os.path.exists(temp_path):
                os.remove(temp_path)
if __name__ == "__main__":
    main()
