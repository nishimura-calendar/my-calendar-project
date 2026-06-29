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
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            # ページ内の全ての文字を、座標情報付きで抽出
            words = page.extract_words()
            
            target_date = str(last_day_A)
            jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
            
            # 1. まず「31」という文字を探す
            for word in words:
                if target_date in word['text']:
                    # 2. 「31」の近く（座標的に上下左右が近い）にある曜日を探す
                    # 同じページ内にある「曜日」文字を全てリストアップ
                    for w in words:
                        if w['text'] in jp_weekdays:
                            # 31と曜日の距離が近いもの（座標差が小さいもの）を特定
                            x_diff = abs(w['x0'] - word['x0'])
                            y_diff = abs(w['top'] - word['top'])
                            
                            # 距離が近い（同じブロックにあると判断できる）場合、それを抽出
                            if x_diff < 50 and y_diff < 50: 
                                return last_day_A, w['text']
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
