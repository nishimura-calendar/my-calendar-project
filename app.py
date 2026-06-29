import streamlit as st
import camelot
import calendar
import base64

# --- ロジック関数 ---
def get_theoretical_info(year, month):
    """A: 理論値を取得"""
    _, last_day = calendar.monthrange(year, month)
    weekday_idx = calendar.weekday(year, month, last_day)
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, jp_weekdays[weekday_idx]

def extract_from_pdf(pdf_path, last_day_A):
    """B: PDFから末尾情報（31, 30...の順）を抽出"""
    try:
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
        jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        
        # 探索する日付（末日から4日分遡る）
        dates_to_check = range(last_day_A, last_day_A - 4, -1)
        
        for table in tables:
            # 表を末尾行から遡って走査
            for i in range(len(table.df) - 1, -1, -1):
                row_text = " ".join([str(cell) for cell in table.df.iloc[i]])
                
                for day in dates_to_check:
                    if str(day) in row_text:
                        for wd in jp_weekdays:
                            if wd in row_text:
                                return day, wd
        return None, None
    except Exception:
        return None, None

def display_error_and_stop(pdf_path, reason):
    st.error(f"【解析停止】データに不一致が検出されました。")
    st.write(f"**理由**: {reason}")
    
    with open(pdf_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    st.markdown(f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="500"></iframe>', unsafe_allow_html=True)
    st.stop()

# --- メインUI ---
def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

    if uploaded_file:
        temp_path = "temp.pdf"
        with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())

        year, month = 2026, 1 
        
        if st.button("解析開始"):
            A_day, A_wd = get_theoretical_info(year, month)
            B_day, B_wd = extract_from_pdf(temp_path, A_day)
            
            # A=B の判定
            if B_day == A_day and B_wd == A_wd:
                st.success(f"成功: 末日{B_day}日は{B_wd}曜日で整合性が確認されました。")
                st.session_state.ready_to_save = True
            else:
                reason = f"理論値は{A_day}日({A_wd}曜日)ですが、PDFからは'{B_day}日({B_wd}曜日)'が検出されました。"
                display_error_and_stop(temp_path, reason)

        if st.session_state.get("ready_to_save", False):
            if st.button("この内容でカレンダーを更新（保存）する"):
                st.success("カレンダーを更新しました！")
                st.session_state.ready_to_save = False

if __name__ == "__main__":
    main()
