import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="時程表設定確認", layout="wide")
st.title("🕒 時程表マスター構成の確認")

drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    # データの読み込み（この時点で拠点ごとにD列以降をスキャンして範囲確定）
    with st.spinner("各拠点の時間列範囲を計算中..."):
        time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)

    st.header("1. 拠点別・時間軸抽出結果の確認")
    st.info("D列以降で『最初の数字』から『最後の数字』までを自動抽出しています。")

    # 読み込まれた全拠点の構成を表示
    for key, df in time_dic.items():
        with st.expander(f"📍 勤務地Key: {key}", expanded=True):
            st.write(f"抽出された列数: {len(df.columns)} (A-C列 + 時間軸 {len(df.columns)-3}列)")
            st.dataframe(df, use_container_width=True)

    st.divider()
    
    # ここで一度止めるためのフラグ
    confirmed = st.checkbox("全ての勤務地で時間列が正しく抽出されていることを確認しました")

    if confirmed:
        st.success("確認完了。PDF解析メニューを表示します。")
        target_staff = st.sidebar.text_input("スタフ名", value="西村 文宏")
        uploaded_pdf = st.sidebar.file_uploader("PDFアップロード", type="pdf")
        
        if st.sidebar.button("解析実行"):
            # ここで p0.pdf_reader_final を呼び出し
            pass
    else:
        st.warning("⚠️ 上記の表を確認し、チェックボックスをオンにしてください。")
