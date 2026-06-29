import streamlit as st
import re
import calendar
import camelot
import os

# --- 関数定義 ---

def get_year_month_from_filename(filename):
    year_match = re.search(r'20\d{2}', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    year = int(year_match.group(0)) if year_match else None
    month = int(month_match.group(1)) if month_match else None
    return year, month

def get_last_day_and_weekday_from_pdf(pdf_file_path):
    """PDFから最終日付と、その日の曜日を抽出する"""
    try:
        tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
        if not tables: return 0, None
        
        all_data = tables[0].df.astype(str).values.flatten()
        days = []
        # 日付と曜日のペアを探す（単純化のため数字と曜日の出現順から特定）
        for v in all_data:
            clean_v = v.strip().replace('.0', '')
            if clean_v.isdigit():
                num = int(clean_v)
                if 1 <= num <= 31: days.append(num)
        
        last_day = max(days) if days else 0
        
        # 最終日の曜日抽出（PDF内から最終日の数字の近くにある曜日を探す簡易ロジック）
        full_text = " ".join(all_data)
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        found_weekday = None
        # 最終日の数字のあとに続く曜日を探す簡易的な探索
        match = re.search(rf"{last_day}\s*([月火水木金土日])", full_text)
        if match:
            found_weekday = match.group(1)
            
        return last_day, found_weekday
    except:
        return 0, None

# --- メイン処理 ---

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("読み込むpdfシフトファイルを開いてください。", type="pdf")
    
    if uploaded_file:
        year_a, month_a = get_year_month_from_filename(uploaded_file.name)
        if year_a is None:
            year_a = st.number_input("年", value=2026)
            month_a = st.number_input("月", value=1)

        if st.button("実行"):
            temp_path = "temp_shift.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # 期待値計算
            last_day_a, _ = calendar.monthrange(int(year_a), int(month_a))
            weekday_idx = calendar.weekday(int(year_a), int(month_a), last_day_a)
            weekday_a = ["月", "火", "水", "木", "金", "土", "日"][weekday_idx]
            
            # PDF解析
            last_day_b, weekday_b = get_last_day_and_weekday_from_pdf(temp_path)
            
            # 整合性判定
            if last_day_a == last_day_b and weekday_a == weekday_b:
                st.success(f"第1関門突破: {year_a}年{month_a}月 ({last_day_a}日 {weekday_a}曜日) 確認完了。")
            else:
                st.error(f"整合性エラー: 期待値 {last_day_a}日({weekday_a})に対し、PDFは {last_day_b}日({weekday_b}) です。")
                st.write("【PDF内容の表示】")
                tables = camelot.read_pdf(temp_path, pages='1', flavor='stream')
                st.dataframe(tables[0].df)
                st.stop()
            
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
