import streamlit as st
import pdfplumber
import calendar
import base64

def get_theoretical_info(year, month):
    _, last_day = calendar.monthrange(year, month)
    weekday_idx = calendar.weekday(year, month, last_day)
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, jp_weekdays[weekday_idx]

def extract_from_pdf(pdf_path, last_day_A):
    """
    構造に依存せず、PDF内の全ての数値と曜日を抽出し、
    末尾から順にペアを探す堅牢なロジック
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text()
            # 曜日をリスト化
            weekdays = ["月", "火", "水", "木", "金", "土", "日"]
            
            # テキストを行ごとに分解し、数値と曜日が含まれるか判定
            lines = text.split('\n')
            
            found_dates = []
            for line in lines:
                # 28〜31の数字が含まれる行を特定
                for d in range(28, 32):
                    if str(d) in line:
                        # 曜日が含まれるか
                        for wd in weekdays:
                            if wd in line:
                                found_dates.append((d, wd))
            
            # 見つかったペアのうち、最大の日付を優先して返す
            if found_dates:
                # 日付順にソートして一番大きいものを返す
                found_dates.sort(key=lambda x: x[0], reverse=True)
                return found_dates[0]
                
        return None, None
    except Exception:
        return None, None

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        temp_path = "temp.pdf"
        with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())

        year, month = 2026, 1
        
        if st.button("解析実行"):
            A_day, A_wd = get_theoretical_info(year, month)
            B_day, B_wd = extract_from_pdf(temp_path, A_day)
            
            if B_day == A_day and B_wd == A_wd:
                st.success(f"成功: {B_day}日は{B_wd}曜日で一致しました。")
                st.session_state.ready_to_save = True
            else:
                st.error(f"【解析停止】データ不一致")
                st.write(f"理論値: {A_day}日({A_wd}) / 抽出値: {B_day}日({B_wd})")
                st.stop()

if __name__ == "__main__":
    main()
