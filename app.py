import streamlit as st
import practice_0 as p0

SHEET_ID = "1HR8gkT2ZbshHYenyQEEepTo8BjnB1gFkHgFYS_Tk4ZE"

st.set_page_config(page_title="時程表マスター構成確認", layout="wide")
st.title("🕒 時程表マスター構成の確認")

# API接続
drive_service, sheets_service = p0.get_unified_services()

if sheets_service:
    try:
        # まず全ての時程データを読み込む（ここで各拠点のD列以降がスキャンされる）
        with st.spinner("スプレッドシートから各拠点の時間列を特定中..."):
            time_dic = p0.time_schedule_from_drive(sheets_service, SHEET_ID)

        st.header("1. 拠点別・抽出範囲の確認")
        st.info("D列以降で『数値』が始まってから終わるまでを自動で時間軸として切り出しています。")

        # 各拠点のデータを一覧表示
        for key, df in time_dic.items():
            with st.expander(f"📍 拠点: {key}", expanded=True):
                st.write(f"抽出列: {len(df.columns)}列（時間軸は {len(df.columns)-3}列分）")
                st.dataframe(df, use_container_width=True)

        st.divider()

        # ここで処理を一度止める（ユーザーの確認を待つ）
        confirmed = st.checkbox("上記全ての時程表の範囲と時間表記（6:15等）が正しいことを確認しました。")

        if not confirmed:
            st.warning("⚠️ 上記のデータを確認し、チェックボックスをオンにしてください。解析メニューが表示されます。")
            st.stop() # ここでプログラムの進行を一時停止

        # --- 確認後の解析メニュー ---
        st.success("確認ありがとうございます。PDFをアップロードしてください。")
        # ここにPDFアップローダーなどのコードを続けます...

    except Exception as e:
        st.error(f"読み込みエラーが発生しました: {e}")
