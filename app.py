import streamlit as st
import pdfplumber
import calendar
import base64
import re

# --- 1. 理論値取得 ---
def get_theoretical_info(year, month):
    """A: カレンダー計算による理論値を取得"""
    _, last_day = calendar.monthrange(year, month)
    weekday_idx = calendar.weekday(year, month, last_day)
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return last_day, jp_weekdays[weekday_idx]

# --- 2. PDF解析（パターン検索方式） ---
def extract_from_pdf(pdf_path, max_day):
    """
    B: 「数字 + 改行 + 曜日」のパターンを末尾から検索して抽出
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # ページ全体のテキストを取得
            page = pdf.pages[0]
            text = page.extract_text()
            
            # 31から28まで遡って検索
            for day in range(max_day, max_day - 4, -1):
                day_str = str(day)
                for wd in ["月", "火", "水", "木", "金", "土", "日"]:
                    # パターン: 日付 + 1つ以上の改行 + 曜日
                    # re.escapeで特殊文字を無効化、\s+で改行や空白を吸収
                    pattern = f"{day_str}.*?\n\s*{wd}"
                    if re.search(pattern, text, re.DOTALL):
                        return day, wd
        return None, None
    except Exception as e:
        st.error(f"解析中にエラーが発生しました: {e}")
        return None, None

# --- 3. UIと分岐処理 ---
def main():
    st.title("シフトカレンダー作成システム")
    uploaded_file = st.file_uploader("PDFシフト表をアップロード", type="pdf")
    
    if uploaded_file:
        temp_path = "temp.pdf"
        with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())

        # 年月はファイル名から「2026」と「1」を想定（必要に応じて調整）
        year, month = 2026, 1
        
        if st.button("解析実行"):
            A_day, A_wd = get_theoretical_info(year, month)
            B_day, B_wd = extract_from_pdf(temp_path, A_day)
            
            # 整合性チェック
            if B_day == A_day and B_wd == A_wd:
                st.success(f"成功: 理論値とPDFの末日が一致しました（{B_day}日 {B_wd}曜日）。")
                st.session_state.ready_to_save = True
            else:
                # ⑥：不一致時の処理（停止）
                reason = f"理論値は{A_day}日({A_wd}曜日)ですが、PDFからは'{B_day}日({B_wd}曜日)'が検出されました。"
                st.error(f"【解析停止】データに不一致が検出されました。")
                st.write(f"**理由**: {reason}")
                
                # PDFを表示して確認させる
                with open(temp_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="500"></iframe>', unsafe_allow_html=True)
                st.stop()

        # ⑤：成功時のみ表示する保存ボタン
        if st.session_state.get("ready_to_save", False):
            if st.button("この内容でカレンダーを更新する"):
                st.success("カレンダーを更新しました！")
                st.session_state.ready_to_save = False

if __name__ == "__main__":
    main()
