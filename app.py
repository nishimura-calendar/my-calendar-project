import streamlit as st
import camelot
import re
import calendar
import os

def get_correct_last_day(filename, year, month):
    """ファイル名と入力値から正しい月末日を算出する"""
    # 1. カレンダーモジュールでその月の末日を取得
    _, last_day = calendar.monthrange(year, month)
    return last_day

def check_pdf_consistency_fixed(pdf_path, year, month):
    try:
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
        full_text = " ".join([cell for table in tables for row in table.df.values for cell in row])
        
        # 1. 数字と曜日のリストを個別に抽出
        all_numbers = [int(n) for n in re.findall(r'\b([12]?[0-9]|3[01])\b', full_text)]
        all_weekdays = re.findall(r'([日月火水木金土])', full_text)
        
        # 2. 末日を算出
        last_day_expected = get_correct_last_day("dummy", year, month)
        
        # 3. 逆順で末日を探す
        last_idx = -1
        for i in range(len(all_numbers) - 1, -1, -1):
            if all_numbers[i] == last_day_expected:
                last_idx = i
                break
        
        if last_idx == -1:
            return False, f"抽出失敗: {last_day_expected}日が見つかりませんでした。", None
            
        found_weekday = all_weekdays[-(len(all_numbers) - last_idx)]
        jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        theory_wd = jp_weekdays[calendar.weekday(year, month, last_day_expected)]
        
        if found_weekday != theory_wd:
            return False, f"不一致: PDFの末日{last_day_expected}日は「{found_weekday}」ですが、理論上は「{theory_wd}」です。", None
            
        return True, f"突破！{year}年{month}月の末日{last_day_expected}日は{found_weekday}曜日で整合性OKです。", None

    except Exception as e:
        return False, f"解析エラー: {e}", None

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")
    
    # 年月の入力
    year = st.number_input("年", value=2026)
    month = st.number_input("月", value=1)
    
    if uploaded_file is not None:
        if st.button("シフト表を解析する"):
            temp_path = "temp.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # 解析実行
            is_success, msg, _ = check_pdf_consistency_fixed(temp_path, int(year), int(month))
            
            if is_success:
                st.success(msg)
            else:
                st.error(msg)
            
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
