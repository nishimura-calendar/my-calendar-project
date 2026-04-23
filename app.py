import streamlit as st
import practice_0 as p0

# --- 事前準備: 時程表を辞書化 ---
# time_dic = {"t1": df_t1, "t2": df_t2} (スプレッドシートから生成)

if st.button("21時の最終解析実行"):
    # PDFを読み込み (Camelot等の処理)
    # df = tables[0].df 
    
    # 解析実行
    loc_key, my_df, other_df = p0.pdf_reader(uploaded_file.name, df, target_staff)
    
    # 辞書キーによる「ガッチャンコ」の確認
    if loc_key in time_dic:
        st.success(f"✅ 勤務地 '{loc_key.upper()}' の紐付けに成功しました")
        
        # 三表の一括表示
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🟢 my_daily_shift")
            st.dataframe(my_df)
        with col2:
            st.subheader("👥 other_daily_shift")
            st.dataframe(other_df)
            
        st.subheader(f"🕒 time_schedule ({loc_key.upper()})")
        st.dataframe(time_dic[loc_key])
    else:
        st.error(f"⚠️ 紐付け失敗: PDFから見つかった '{loc_key}' は時程表にありません。")
        st.stop()
