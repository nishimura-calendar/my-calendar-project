import streamlit as st
import practice_0 as p0
import pandas as pd
import base64

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"
st.set_page_config(page_title="PDF照合システム", layout="wide")

if 'time_dic' not in st.session_state:
    st.session_state.time_dic = None

# APIサービス取得
drive, sheets = p0.get_unified_services()
if sheets and st.session_state.time_dic is None:
    try:
        st.session_state.time_dic = p0.load_time_schedule(sheets, SHEET_ID)
    except:
        st.error("マスターデータの読み込みに失敗しました。")

uploaded_file = st.file_uploader("PDFファイルをアップロード", type="pdf")

if uploaded_file:
    # 解析実行
    res, msg = p0.analyze_pdf_structural(uploaded_file, st.session_state.time_dic.keys() if st.session_state.time_dic else [], uploaded_file.name)

    # --- ① 不一致（解析失敗）時の表示 ---
    if res is None:
        st.error(f"⚠️ 解析エラー: {msg}")
        # PDFをBase64で表示
        uploaded_file.seek(0)
        base64_pdf = base64.b64encode(uploaded_file.read()).decode('utf-8')
        pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">'
        st.markdown(pdf_display, unsafe_allow_html=True)
        st.stop() # ここで確実に止める

    # --- ② 解析成功後の操作 ---
    st.success(f"✅ {res['year']}年{res['month']}月 / 拠点: {res['location']}")
    
    # 氏名選択（Enterで確定）
    target_staff = st.selectbox(
        "スタッフを選択してEnterを押してください",
        options=["該当なし"] + res['staff_list'],
        index=0
    )

    if target_staff != "該当なし":
        df = res['df']
        loc_key = p0.normalize_text(res['location'])
        
        try:
            # データ抽出
            idx = df[df[0] == target_staff].index[0]
            my_daily_shift = df.iloc[idx : idx+2, :]
            
            other_indices = []
            for i in range(2, len(df), 2):
                row_name = str(df.iloc[i, 0]).strip()
                if row_name != target_staff and p0.normalize_text(row_name) != loc_key:
                    other_indices.append(i)
            other_daily_staff = df.iloc[other_indices, :]

            # 表示
            st.divider()
            st.subheader(f"📅 {target_staff} の個人シフト")
            st.dataframe(my_daily_shift, hide_index=True, use_container_width=True)

            st.subheader("👥 他スタッフの勤務状況")
            st.dataframe(other_daily_staff, hide_index=True, use_container_width=True)
            
            if loc_key in st.session_state.time_dic:
                st.subheader(f"⏰ 拠点時程表: {res['location']}")
                st.dataframe(st.session_state.time_dic[loc_key], hide_index=True, use_container_width=True)

        except Exception as e:
            st.error(f"表示処理中にエラーが発生しました: {e}")
    else:
        st.info("スタッフ名を選択すると詳細が表示されます。")
