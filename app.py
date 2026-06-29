import streamlit as st
import camelot
import re
import calendar
import os

# 解析用関数（そのまま維持）
def check_pdf_consistency_with_anchors(pdf_path, year, month):
    try:
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='stream')
        full_text = " ".join([cell for table in tables for row in table.df.values for cell in row])
        # 数字と曜日を抽出
        pattern = r'(\d{1,2})\s*([日月火水木金土])'
        matches = re.findall(pattern, full_text)
        day_map = {int(day): wd for day, wd in matches}
        sorted_days = sorted(day_map.keys())
        
        _, last_day_expected = calendar.monthrange(year, month)
        
        if len(sorted_days) < last_day_expected:
            return False, f"抽出失敗: {len(sorted_days)}日しか特定できませんでした。", None

        last_day = sorted_days[-1]
        found_weekday = day_map[last_day]
        theory_weekday_idx = calendar.weekday(year, month, last_day)
        jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        
        if jp_weekdays[theory_weekday_idx] != found_weekday:
            return False, f"曜日不一致: 最終日{last_day}はカレンダー上{jp_weekdays[theory_weekday_idx]}ですが、PDFでは{found_weekday}でした。", None
        
        return True, "第1関門突破！整合性OKです。", day_map
    except Exception as e:
        return False, f"解析エラー: {e}", None

def main():
    st.title("シフトカレンダー作成システム")
    
    # アップロード
    uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")
    
    # 年月の入力
    year = st.number_input("年", value=2026)
    month = st.number_input("月", value=1)
    
    if uploaded_file is not None:
        st.write(f"ファイル名: {uploaded_file.name}")
        
        # 【重要】ここに実行ボタンを追加
        if st.button("シフト表を解析する"):
            # 一時ファイルとして保存して解析
            temp_path = "temp.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # 解析実行
            is_success, msg, data = check_pdf_consistency_with_anchors(temp_path, int(year), int(month))
            
            if is_success:
                st.success(msg)
            else:
                st.error(msg)
            
            # 終了後にファイルを削除
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
