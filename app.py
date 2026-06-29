import streamlit as st
import camelot
import re
import calendar
import os

def check_pdf_consistency_with_reverse_search(pdf_path, year, month):
    try:
        # 1. 罫線認識能力が高い 'lattice' モードで読み込み
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
        
        # 全セルからテキストを回収
        full_text = " ".join([cell for table in tables for row in table.df.values for cell in row])
        
        # 2. 31から28まで、逆順に「数字＋曜日」のペアを探す
        last_day, last_wd = None, None
        for day in range(31, 27, -1):
            # 日付の後に続く曜日を探索（改行やスペースがあっても許容）
            pattern = fr'{day}\s*[\s\S]*?([日月火水木金土])'
            match = re.search(pattern, full_text)
            if match:
                last_day = day
                last_wd = match.group(1)
                break # ヒットした時点で終了
        
        if last_day is None:
            return False, "抽出失敗: 最終日（28〜31日）が見つかりませんでした。", None

        # 3. 理論値との照合
        theory_wd_idx = calendar.weekday(year, month, last_day)
        jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        
        if jp_weekdays[theory_wd_idx] != last_wd:
            return False, f"最終日不一致: PDF上の{last_day}日は「{last_wd}」ですが、カレンダー上は「{jp_weekdays[theory_wd_idx]}」です。", None
        
        return True, f"第1関門突破！最終日は{last_day}日（{last_wd}曜日）で整合性が取れました。", None

    except Exception as e:
        return False, f"解析エラー: {e}", None

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")
    year = st.number_input("年", value=2026)
    month = st.number_input("月", value=1)
    
    if uploaded_file is not None:
        if st.button("シフト表を解析する"):
            temp_path = "temp.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            is_success, msg, _ = check_pdf_consistency_with_reverse_search(temp_path, int(year), int(month))
            
            if is_success:
                st.success(msg)
            else:
                st.error(msg)
            
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
