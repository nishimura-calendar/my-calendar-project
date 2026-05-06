import streamlit as st
import practice_0 as p0
import re
import fitz

# 画面を横幅いっぱいに使う設定
st.set_page_config(layout="wide")

SPREADSHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

# --- 1. 初期読込 (時程表) ---
if 'time_dic' not in st.session_state:
    try:
        service = p0.get_service()
        st.session_state.time_dic = p0.load_master_from_sheets(service, SPREADSHEET_ID)
    except Exception as e:
        st.error(f"時程表読込失敗: {e}"); st.stop()

# --- 2. アップロード ---
st.title("シフトデータ一括表示システム")
uploaded_file = st.file_uploader("PDFを選択してください", type="pdf", label_visibility="collapsed")

if uploaded_file:
    # ファイル名を全表示（コードブロックで折り返し対応）
    st.markdown("#### 📄 ファイル名")
    st.code(uploaded_file.name, language=None)
    
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
            st.success(f"拠点「{location}」の解析に成功しました。")
            
            # スタッフ選択
            target_staff = st.selectbox("カレンダーを作成するスタッフを選択してください", 
                                       options=["未選択"] + res['staff_list'])
            
            if target_staff != "未選択":
                df = res['df']
                idx = df[df[0] == target_staff].index[0]
                
                # --- ここから「全て表示」セクション ---
                st.divider()
                
                # ① my_daily_shift (本人データ)
                st.subheader(f"1. 【{target_staff}】個人のシフト (my_daily_shift)")
                my_shift = df.iloc[idx : idx+2, 0:]
                st.dataframe(my_shift, hide_index=True, use_container_width=True)

                # ② other_daily_shift (他全員データ)
                st.subheader("2. 他スタッフ全員の動静 (other_daily_shift)")
                # ヘッダーと自分を除いた「全て」を表示
                other_shift = df.drop([idx, idx+1]).iloc[2:, 0:]
                st.dataframe(other_shift, hide_index=True, use_container_width=True)

                # ③ time_schedule (拠点の全時程)
                st.subheader(f"3. 拠点「{location}」の全時程ルール (time_schedule)")
                if location in st.session_state.time_dic:
                    st.dataframe(st.session_state.time_dic[location], hide_index=True, use_container_width=True)
                else:
                    st.warning(f"時程表に {location} が見つかりません。")
                
                st.markdown("---")
                st.info("上記3種類のデータを全て表示しました。内容を確認してください。")
        else:
            st.error(msg)
