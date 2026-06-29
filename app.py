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
    31日(直下)、30日(直下)...の順に検索し、ヒットした時点で抽出する
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            # テキストを抽出
            text = page.extract_text()
            # 行ごとに分割
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            # 31から28まで遡って検索
            for day in range(last_day_A, last_day_A - 4, -1):
                day_str = str(day)
                
                # 行リストを走査
                for i in range(len(lines)):
                    # 日付が含まれる行を発見
                    if day_str == lines[i]: # 完全一致で判定
                        # 次の行（直下）が存在するか確認
                        if i + 1 < len(lines):
                            target_wd = lines[i + 1]
                            # それが曜日であるか確認
                            if target_wd in ["月", "火", "水", "木", "金", "土", "日"]:
                                return day, target_wd
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
