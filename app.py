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
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            # ページ内の文字データを座標付きで取得
            chars = page.chars
            
            # 「28, 29, 30, 31」という文字列が連続して出現する場所（最初の塊）を探す
            # 座標(top)が近いものをグループ化し、最初のグループを採用する
            groups = []
            for char in chars:
                if char['text'] in "28293031":
                    # top座標(y座標)が近いものを同じグループとする
                    found = False
                    for g in groups:
                        if abs(g[0]['top'] - char['top']) < 5:
                            g.append(char)
                            found = True
                            break
                    if not found:
                        groups.append([char])
            
            # 最初のグループ（塊）を取り出す
            if not groups: return None, None
            first_group = sorted(groups[0], key=lambda x: x['x0'])
            
            # その塊の下にある曜日を探す
            # 塊に含まれる数値から、対応する曜日を特定
            for day in range(max_day, max_day - 4, -1):
                day_str = str(day)
                # 該当する数値の座標を探す
                for char in first_group:
                    if char['text'] == day_str[0]: # 数値の最初の桁で判定
                        # この座標の「すぐ下」にある曜日を探す
                        for c in chars:
                            if abs(c['x0'] - char['x0']) < 10 and \
                               c['top'] > char['bottom'] and c['top'] < char['bottom'] + 20:
                                if c['text'] in ["月", "火", "水", "木", "金", "土", "日"]:
                                    return day, c['text']
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
