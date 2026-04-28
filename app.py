import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="時程表マスター構成確認", layout="wide")
st.title("🕒 時程表マスター構成の確認")

# API接続
drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    try:
        # 全拠点の時間列を動的にスキャンして読み込み
        with st.spinner("スプレッドシートから各拠点の時間列を特定中..."):
            time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)

        st.header("1. 拠点別・抽出範囲の確認")
        st.info("D列以降で『数値』が始まってから終わるまでを時間軸として切り出しています。")

        # 各拠点のデータを一覧表示
        for key, df in time_dic.items():
            with st.expander(f"📍 拠点: {key}", expanded=True):
                # 抽出された列数の詳細を表示
                st.write(f"抽出列: {len(df.columns)}列（時間軸は {len(df.columns)-3}列分）")
                # 最後まで表示されるよう、コンテナ幅いっぱいに表示
                st.dataframe(df, use_container_width=True)

        st.divider()

        # ユーザーが全件確認するまで停止させる
        confirmed = st.checkbox("上記全ての時程表で、時間列が最後まで正しく抽出されていることを確認しました。")

        if not confirmed:
            st.warning("⚠️ 全ての拠点データを確認し、チェックボックスをオンにしてください。")
            st.stop()

        st.success("確認完了。PDF解析メニューへ進みます。")
        # (この後にPDFアップロード等の解析処理を記述)

    except Exception as e:
        st.error(f"読み込みエラー: {e}")
