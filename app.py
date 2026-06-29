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

def get_pdf_info_b(pdf_file_path):
    """
    B: PDF内容から『日本語の曜日』のみを抽出し、その数をカウントする
    """
    try:
        tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
        if not tables: return 0, None, None
        
        all_text = "".join(tables[0].df.astype(str).values.flatten())
        weekdays_found = re.findall(r'[日月火水木金土]', all_text)
        
        count = len(weekdays_found)
        return count, weekdays_found, tables[0].df
    except Exception as e:
        st.error(f"PDF読み込みエラー: {e}")
        return 0, None, None

# --- メイン処理 ---

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    if uploaded_file is not None:
        st.write(f"ファイル名: {uploaded_file.name}")
        year_a, month_a = get_year_month_from_filename(uploaded_file.name)
        
        if year_a is None or month_a is None:
            st.warning("ファイル名から年月が抽出できませんでした。")
            year_a = st.number_input("年を入力してください", value=2026)
            month_a = st.number_input("月を入力してください", value=1)
        else:
            st.info(f"抽出年月: {year_a}年{month_a}月")

        if st.button("実行"):
            # 一時保存用のパス
            temp_path = "temp_shift.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # A: 期待される末日
            _, last_day_expected = calendar.monthrange(int(year_a), int(month_a))
            
            # B: PDFから取得
            last_day_b, found_list, df = get_pdf_info_b(temp_path)
            
            # 第1関門判定
            if last_day_expected == last_day_b:
                st.success(f"第1関門突破！ (日付: {last_day_b}日)")
            else:
                st.error(f"整合性エラー: 期待される日数 {last_day_expected} と、PDF内の曜日数 {last_day_b} が一致しません。")
                st.write("抽出された曜日リスト:", found_list)
                st.dataframe(df)
            
            # 処理後に一時ファイルを削除
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
