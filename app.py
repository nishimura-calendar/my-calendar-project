import streamlit as st
import practice_0 as p0
# (build, service_account等のインポートと認証部分は共通につき省略)

# サービスの準備・時程表読み込み
drive_service, sheets_service = p0.get_unified_services() # 統一認証関数
if sheets_service:
    time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)
    st.sidebar.success("✅ 時程表マスター準備完了")

# UIと実行
target_staff = st.sidebar.text_input("解析対象者名", value="西村 文宏")
uploaded_pdf = st.sidebar.file_uploader("勤務表PDF", type="pdf")

if st.sidebar.button("解析・照合実行"):
    results = p0.pdf_reader_with_logic_7(uploaded_pdf, target_staff, time_dic)
    
    if results:
        for res in results:
            st.divider()
            st.header(f"📍 通過資格確認：Key 「{res['key']}」")
            
            # 座標から取得した位置情報の確認
            with st.expander("PDF座標 [0,0], [0,1], [1,1] の取得値"):
                st.write(res['coords'])
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("① 自分のシフト")
                st.dataframe(res['my_data'])
            with col2:
                st.subheader("🕒 対応する時程(行列範囲)")
                st.dataframe(res['time_range'], use_container_width=True)
    else:
        st.error("第三関門：Keyの不一致により、通過資格が認められませんでした。")
