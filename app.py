import streamlit as st
import re
import calendar
import camelot

def get_pdf_info(pdf_file_path):
    """PDFから曜日文字列の数を数え、最終日付と曜日を抽出する"""
    tables = camelot.read_pdf(pdf_file_path, pages='1', flavor='stream')
    if not tables: return 0, None, None
    
    all_text = " ".join(tables[0].df.astype(str).values.flatten())
    # 曜日をカウント（日〜土）
    weekdays = re.findall(r'[日月火水木金土]', all_text)
    count = len(weekdays)
    
    # 最終日（一番大きい数字）を抽出
    numbers = [int(n) for n in re.findall(r'\b([123]?\d)\b', all_text) if 1 <= int(n) <= 31]
    last_day = max(numbers) if numbers else 0
    last_weekday = weekdays[-1] if weekdays else None
    
    return count, last_day, last_weekday, tables[0].df

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフトファイルを開いてください。", type="pdf")
    
    if uploaded_file:
        # ファイル名から年月取得（既存ロジック）
        # ... (省略) ...
        year_a, month_a = 2026, 1 # テスト用仮置き
        _, last_day_a = calendar.monthrange(year_a, month_a)
        
        if st.button("実行"):
            temp_path = "temp.pdf"
            with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())
            
            count_b, last_day_b, last_weekday_b, df = get_pdf_info(temp_path)
            
            # 判定ロジック
            if count_b == last_day_a:
                st.success(f"第1関門突破！ (PDF内の曜日数: {count_b})")
            else:
                st.error(f"整合性エラー: 期待される日数 {last_day_a} と、PDF内の曜日数 {count_b} が一致しません。")
                st.write("--- アップロードされたPDFの内容 ---")
                st.dataframe(df) # 加工なしで表示
                st.stop()

if __name__ == "__main__":
    main()
