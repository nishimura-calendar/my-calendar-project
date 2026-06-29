import streamlit as st
import pdfplumber
import calendar
import base64

def get_theoretical_info(year, month):
    _, last_day = calendar.monthrange(year, month)
    weekday_idx = calendar.weekday(year, month, last_day)
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, jp_weekdays[weekday_idx]

def extract_from_pdf(pdf_path, max_day):
    """
    構造に依存せず、PDF内の全ての数値と曜日を全スキャンし、
    末尾からペアを探す手法に切り替えました。
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text()
            
            # 数値（28-31）と曜日を検索
            found_dates = []
            
            # 全テキストの中から「数字」と「曜日」を探す
            # 正規表現で「数字」のリストと「曜日」のリストを作る
            import re
            
            # 日付（28〜31）を見つける
            for day in range(28, 32):
                if str(day) in text:
                    # その日付の近く（前後一定範囲）に曜日があるか確認
                    # 見つけた日付のインデックス周辺を検索
                    idx = text.find(str(day))
                    search_area = text[idx:idx+60] # 60文字程度で曜日を探す
                    
                    for wd in ["月", "火", "水", "木", "金", "土", "日"]:
                        if wd in search_area:
                            found_dates.append((day, wd))
            
            # 見つかった中で最も大きい日付を返す
            if found_dates:
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
