import streamlit as st
import camelot
import re
import calendar
import os

def get_year_month_from_filename(filename):
    year_match = re.search(r'20\d{2}', filename)
    month_match = re.search(r'(\d{1,2})月', filename)
    year = int(year_match.group(0)) if year_match else None
    month = int(month_match.group(1)) if month_match else None
    return year, month

def check_pdf_consistency(pdf_path, year, month):
    """
    第1関門：PDFのヘッダーから日付と曜日を抽出し、理論上のカレンダーと比較する
    """
    try:
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='stream')
        if not tables: return False, "テーブルが読み込めませんでした", None
        
        df = tables[0].df
        # 1. 最初の3行分を結合してヘッダー文字列を作成
        header_text = " ".join(df.iloc[0:3].astype(str).values.flatten())
        
        # 2. 数字と曜日のペアを抽出 (例: "1 木", "31 月")
        # ユニークな日付を確保するために辞書を使用
        matches = re.findall(r'(\d+)\s*([日月火水木金土])', header_text)
        
        # 日付をキーにして辞書化 (重複回避)
        day_map = {int(day): wd for day, wd in matches}
        sorted_days = sorted(day_map.keys())
        
        # 3. 期待されるデータとの比較
        _, last_day_expected = calendar.monthrange(year, month)
        
        # 検証：日数と最後の曜日
        is_valid = True
        error_msg = ""
        
        if len(sorted_days) != last_day_expected:
            is_valid = False
            error_msg = f"日数不一致: 期待{last_day_expected}日に対し、{len(sorted_days)}日分しか抽出できませんでした。"
        else:
            # 最後の曜日チェック
            last_day_found = sorted_days[-1]
            last_weekday_found = day_map[last_day_found]
            
            # 理論上の曜日を取得 (0:月, 6:日)
            theory_weekday_idx = calendar.weekday(year, month, last_day_found)
            jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
            
            if jp_weekdays[theory_weekday_idx] != last_weekday_found:
                is_valid = False
                error_msg = f"曜日不一致: {last_day_found}日の曜日がカレンダー上は{jp_weekdays[theory_weekday_idx]}ですが、PDFでは{last_weekday_found}となっています。"
        
        return is_valid, error_msg, df

    except Exception as e:
        return False, f"エラーが発生しました: {e}", None

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")
    
    if uploaded_file:
        year, month = get_year_month_from_filename(uploaded_file.name)
        if not year or not month:
            year = st.number_input("年を入力", value=2026)
            month = st.number_input("月を入力", value=1)
        
        if st.button("実行"):
            temp_path = "temp.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            is_valid, msg, df = check_pdf_consistency(temp_path, int(year), int(month))
            
            if is_valid:
                st.success("第1関門突破！整合性OKです。")
            else:
                st.error(f"【第1関門失敗】{msg}")
                st.write("--- 読み込んだ表のプレビュー ---")
                st.dataframe(df) # 不一致時に表を表示
            
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
