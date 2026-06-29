import streamlit as st
import camelot
import calendar
import os
import base64

# --- ロジック関数 ---
def get_theoretical_info(year, month):
    """A: 理論値を取得"""
    _, last_day = calendar.monthrange(year, month)
    weekday_idx = calendar.weekday(year, month, last_day)
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, jp_weekdays[weekday_idx]

def extract_from_pdf(pdf_path, last_day_A):
    """B: PDFから実データを抽出"""
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    
    for table in tables:
        # 右端の列を探索
        last_col = table.df.iloc[:, -1].astype(str)
        for cell in last_col:
            if str(last_day_A) in cell:
                for wd in jp_weekdays:
                    if wd in cell:
                        return last_day_A, wd
    return None, None

# --- UIと分岐処理 ---
def display_error_and_stop(pdf_path, reason):
    st.error(f"【解析停止】データに不一致が検出されました。")
    st.write(f"**不一致の理由**: {reason}")
    
    with open(pdf_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    st.markdown(f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="500"></iframe>', unsafe_allow_html=True)
    st.stop()

def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

    if uploaded_file:
        temp_path = "temp.pdf"
        with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())

        # 年月はファイル名から簡易抽出（必要に応じて正規表現を強化してください）
        year, month = 2026, 1 
        
        if st.button("解析開始"):
            # Aの取得
            A_day, A_wd = get_theoretical_info(year, month)
            # Bの取得
            B_day, B_wd = extract_from_pdf(temp_path, A_day)
            
            # 分岐：一致なら⑤へ、不一致なら⑥へ
            if B_day is not None and A_wd == B_wd:
                st.success(f"成功: {year}年{month}月の末日は{B_wd}曜日で一致しました。")
                st.session_state.ready_to_save = True
            else:
                reason = f"理論上は{A_wd}曜日ですが、PDFからは'{B_wd}'として検出されました。"
                display_error_and_stop(temp_path, reason)

        # 保存確認ステップ
        if st.session_state.get("ready_to_save", False):
            if st.button("この内容でカレンダーを更新（保存）する"):
                st.success("カレンダーを更新しました！")
                st.session_state.ready_to_save = False

if __name__ == "__main__":
    main()
