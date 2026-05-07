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

# 2. メインUI
st.title("シフト解析・カレンダー生成")
uploaded_file = st.file_uploader("PDFシフト表を選択してください", type="pdf")

if uploaded_file:
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
            
            target_staff = st.selectbox("スタッフを選択してください", options=["未選択"] + res['staff_list'])
            df = res['df']
            st.divider()

            if target_staff != "未選択":
                # --- ① 全表示セクション ---
                st.header(f"📊 {target_staff} さんの抽出データ")
                
                # my_daily_shift
                idx = df[df[0] == target_staff].index[0]
                st.subheader("1. my_daily_shift")
                st.dataframe(df.iloc[idx : idx+2, 0:], hide_index=True, use_container_width=True)

                # other_daily_shift (本人と拠点名を除去)
                st.subheader("2. other_daily_shift")
                other_df = df.drop([idx, idx+1]).iloc[2:, 0:]
                other_df_clean = other_df[other_df[0] != location]
                st.dataframe(other_df_clean, hide_index=True, use_container_width=True)

                # time_schedule
                st.subheader(f"3. time_schedule ({location})")
                if location in st.session_state.time_dic:
                    st.dataframe(st.session_state.time_dic[location], hide_index=True, use_container_width=True)

                # --- ② カレンダー生成セクション ---
                st.divider()
                st.header("📅 カレンダーデータ生成")
                if st.button(f"{target_staff} さんのCSVを作成"):
                    cal_df = p0.generate_calendar_data(target_staff, location, df, st.session_state.time_dic, y, m)
                    if cal_df is not None:
                        st.dataframe(cal_df, use_container_width=True, hide_index=True)
                        csv = cal_df.to_csv(index=False, encoding='utf_8_sig')
                        st.download_button("CSVをダウンロード", data=csv, file_name=f"{y}{m:02d}_{target_staff}.csv", mime="text/csv")
        else:
            st.error(msg)
            # 解析失敗時はPDFを表示
            doc = fitz.open("temp.pdf")
            img = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
            st.image(img, use_container_width=True)
