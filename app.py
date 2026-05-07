import streamlit as st
import practice_0 as p0
import re
import fitz

st.set_page_config(layout="wide")
SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

# 1. 時程表の事前読込
if 'time_dic' not in st.session_state:
    try:
        service = p0.get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

# 2. PDFアップロード
st.title("シフト解析・全データ表示システム")
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
    # ファイル名全表示
    st.info(f"📄 対象ファイル: {uploaded_file.name}")
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
            st.success(f"拠点「{location}」を照合しました。")
            
            # スタッフ選択
            target_staff = st.selectbox("スタッフを選択してください", options=["未選択"] + res['staff_list'])
            
            if target_staff != "未選択":
                df = res['df']
                idx = df[df[0] == target_staff].index[0]
                
                st.divider()
                st.header(f"📊 {target_staff} さんの全データ表示")

                # ① 個人のシフト (my_daily_shift)
                st.subheader("1. my_daily_shift (個人の勤務時間)")
                st.dataframe(df.iloc[idx : idx+2, 0:], hide_index=True, use_container_width=True)

                # ② 他全員のシフト (other_daily_shift)
                st.subheader("2. other_daily_shift (他スタッフの勤務状況)")
                # 自分を除去
                other_df = df.drop([idx, idx+1]).iloc[2:, 0:]
                # ★ 途中の拠点名(location)行を完全に排除
                other_df_clean = other_df[other_df[0] != location]
                st.dataframe(other_df_clean, hide_index=True, use_container_width=True)

                # ③ 拠点マスタ (time_schedule)
                st.subheader(f"3. time_schedule (拠点「{location}」の時程)")
                if location in st.session_state.time_dic:
                    st.dataframe(st.session_state.time_dic[location], hide_index=True, use_container_width=True)
                else:
                    st.warning(f"時程表に {location} が見つかりません。")

                st.info("全てのデータを正常に表示しました。")
        else:
            st.error(msg)
