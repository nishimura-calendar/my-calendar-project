import streamlit as st
import camelot
import calendar
import os
import base64

# --- 共通関数 ---
def check_pdf_consistency(pdf_path, year, month):
    """A(理論値)とB(PDF抽出値)の整合性をチェック"""
    _, last_day_A = calendar.monthrange(year, month)
    weekday_idx_A = calendar.weekday(year, month, last_day_A)
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_A = jp_weekdays[weekday_idx_A]

    # B: PDFから末尾の情報を抽出 (簡易実装)
    tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
    found_day, found_weekday = None, None
    for table in tables:
        # 表の右端列を探索
        last_col = table.df.iloc[:, -1].astype(str)
        for cell in last_col:
            if str(last_day) in cell:
                found_day = last_day
                for wd in jp_weekdays:
                    if wd in cell:
                        found_weekday = wd
    
    return (last_day_A, weekday_A), (found_day, found_weekday)

def display_error_and_stop(pdf_path, reason):
    st.error(f"【解析停止】データに不一致が検出されました。")
    st.write(f"**不一致の理由**: {reason}")
    with open(pdf_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    st.markdown(f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="700" height="500"></iframe>', unsafe_allow_html=True)
    st.stop()

# --- メイン処理 ---
def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")

    if uploaded_file:
        temp_path = "temp.pdf"
        with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())

        # 年月判定
        year, month = 2026, 1 # 仮設定
        
        if st.button("解析開始"):
            # AとBの比較
            (A_day, A_wd), (B_day, B_wd) = check_pdf_consistency(temp_path, year, month)
            
            if A_day == B_day and A_wd == B_wd:
                st.success(f"解析成功: {year}年{month}月は整合しています。")
                # セッションに結果を保持
                st.session_state.ready_to_save = True
            else:
                display_error_and_stop(temp_path, f"理論値:{A_wd}曜日 vs PDF値:{B_wd}曜日")

        # 上書き確認のステップ
        if st.session_state.get("ready_to_save", False):
            st.warning("この内容でカレンダーを更新（上書き）しますか？")
            if st.button("保存・更新を実行"):
                st.success("カレンダーを更新しました！")
                st.session_state.ready_to_save = False # リセット
            if st.button("キャンセル"):
                st.session_state.ready_to_save = False

if __name__ == "__main__":
    main()
