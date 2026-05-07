import streamlit as st
import practice_0 as p0
import re

st.set_page_config(layout="wide")
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

# --- 1. 時程表の読込 ---
if 'time_dic' not in st.session_state:
    try:
        service = p0.get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

# --- 2. 画面構成 ---
st.title("シフト管理システム - 全データ表示")

uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    # ファイル名の全表示
    st.info(f"📄 処理中のファイル: {uploaded_file.name}")
    
    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getvalue())

    # 年月抽出
    fname = uploaded_file.name
    match_y, match_m = re.search(r'(\d{4})', fname), re.search(r'(\d{1,2})', fname)
    y, m = (int(match_y.group(1)), int(match_m.group(1))) if (match_y and match_m) else (None, None)
    
    if y and m:
        res, msg = p0.analyze_pdf_structure("temp.pdf", y, m)
        if res:
            location = res['location']
            st.success(f"拠点「{location}」の解析が完了しました。")
            
            target_staff = st.selectbox("スタッフを選択してください", 
                                       options=["未選択"] + res['staff_list'])
            
            if target_staff != "未選択":
                df = res['df']
                idx = df[df[0] == target_staff].index[0]
                
                st.divider()
                st.header(f"📊 {target_staff} さんの全関連データ")

                # ① my_daily_shift (個人の2行)
                st.subheader("1. my_daily_shift")
                my_shift = df.iloc[idx : idx+2, 0:]
                st.dataframe(my_shift, hide_index=True, use_container_width=True)

                # ② other_daily_shift (他スタッフ全員 & 拠点名行の除外)
                st.subheader("2. other_daily_shift")
                # 自分の2行を除去
                other_df = df.drop([idx, idx+1]).iloc[2:, 0:]
                # ★ 拠点名(location)と一致する行を、列0から完全に排除して「全表示」
                other_df_clean = other_df[other_df[0] != location]
                st.dataframe(other_df_clean, hide_index=True, use_container_width=True)

                # ③ time_schedule (スプレッドシートマスタ)
                st.subheader(f"3. time_schedule ({location})")
                if location in st.session_state.time_dic:
                    st.dataframe(st.session_state.time_dic[location], hide_index=True, use_container_width=True)
                else:
                    st.warning(f"時程表に {location} が見つかりません。")

                st.markdown("---")
                st.caption("全てのデータ（個人・全体・マスタ）を表示しました。")
