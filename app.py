import streamlit as st
import practice_0 as p0
import re
import fitz
import os

SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(layout="wide")

# 1. 時程表の事前読込 (practice_0内のget_serviceを使用)
if 'time_dic' not in st.session_state:
    try:
        service = p0.get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

# 2. PDFアップロード
st.markdown("### 1. PDFシフト表のアップロード")
uploaded_file = st.file_uploader("PDFを選択してください", type="pdf", label_visibility="collapsed")

if uploaded_file:
    # --- ファイル名の全表示エリア ---
    st.markdown("#### 📄 読み込み中のファイル名:")
    st.code(uploaded_file.name, language=None) # これで長い名前も全表示・コピー可能になります
    
    # 一時保存[cite: 8]
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getvalue())

    # 年月抽出
    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y is None or m is None:
        st.warning("ファイル名に年月が見つかりません。")
        col1, col2 = st.columns(2)
        y = col1.number_input("年", value=2026)
        m = col2.number_input("月", min_value=1, max_value=12)
        is_ready = st.button("この年月で解析開始")
    else: 
        is_ready = True

    if is_ready:
        # 解析実行[cite: 5, 7]
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        
        if res is None:
            st.error(msg)
            # PDFプレビュー表示
            doc = fitz.open("temp.pdf")
            img = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
            st.image(img, caption="PDFプレビュー", use_container_width=True)
            st.stop()

        location = res['location']
        
        # 拠点照合
        if location not in st.session_state.time_dic:
            st.error(f"拠点名【{location}】は時程表に登録されていません。")
            st.stop()
        
        # スタッフ選択 (リストから T1 は除外済み)
        st.success(f"拠点「{location}」の解析に成功しました。")
        target_staff = st.selectbox("カレンダーを作成するスタッフを選択してください", 
                                   options=["該当なし"] + res['staff_list'])
        
        if target_staff != "該当なし":
            df = res['df']
            idx = df[df[0] == target_staff].index[0]
            
            st.write(f"### {target_staff} さんの抽出データ")
            # 氏名列を含む全データを表示[cite: 5]
            st.dataframe(df.iloc[idx : idx+2, 0:], hide_index=True)
