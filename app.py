import streamlit as st
import camelot
import re
import calendar
import os

def check_pdf_consistency(pdf_path, year, month):
    try:
        # streamモードで読み込み
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='stream')
        if not tables:
            return False, "PDFからテーブルが抽出できませんでした。", None

        # 全てのセルからテキストを取得し、結合して単一の文字列にする
        # 重要な前処理：バラバラになった数字（例：3 1）を結合（31）する
        full_text = ""
        for table in tables:
            for row in table.df.values:
                for cell in row:
                    full_text += str(cell) + " "
        
        # 1. 離れた数字を結合する (例: "3 1" -> "31")
        full_text = re.sub(r'(\d)\s+(\d)', r'\1\2', full_text)
        
        # 2. 「1〜31」の数字と「曜日」のペアを抽出
        # 間にスペースや改行がいくらあっても許容するパターン
        pattern = r'(3[0-1]|[1-2]?[0-9])[\s\S]*?([日月火水木金土])'
        matches = re.findall(pattern, full_text)
        
        # 辞書化して重複を排除（日付をキーにする）
        day_map = {int(day): wd for day, wd in matches}
        sorted_days = sorted(day_map.keys())
        
        # 期待される月末日
        _, last_day_expected = calendar.monthrange(year, month)
        
        # --- 検証 ---
        if len(sorted_days) < last_day_expected:
            return False, f"日数不一致: 期待{last_day_expected}日に対し、{len(sorted_days)}日しか特定できませんでした。", tables[0].df

        # 最後の曜日チェック
        last_day_found = sorted_days[-1]
        last_wd_found = day_map[last_day_found]
        
        # 理論上の曜日を取得
        theory_wd_idx = calendar.weekday(year, month, last_day_found)
        jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        
        if jp_weekdays[theory_wd_idx] != last_wd_found:
            return False, f"最終曜日不一致: {last_day_found}日はカレンダー上{jp_weekdays[theory_wd_idx]}ですが、PDFでは{last_wd_found}です。", tables[0].df
        
        return True, "第1関門突破！整合性OKです。", tables[0].df

    except Exception as e:
        return False, f"解析エラー: {e}", None

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロードしてください", type="pdf")
    
    if uploaded_file:
        year = st.number_input("年", value=2026)
        month = st.number_input("月", value=1)
        
        if st.button("実行"):
            temp_path = "temp.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            is_valid, msg, df = check_pdf_consistency(temp_path, int(year), int(month))
            
            if is_valid:
                st.success(msg)
            else:
                st.error(f"【第1関門失敗】{msg}")
                st.write("--- デバッグ情報：読み込んだデータ（最初の5行） ---")
                st.dataframe(df.head(5))
            
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    main()
