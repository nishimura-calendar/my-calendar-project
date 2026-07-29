import streamlit as st
import pandas as pd

st.title("シフト解析ダッシュボード")

# CSVまたはPDFをアップロード
uploaded_file = st.file_uploader("ファイルをアップロード", type=["csv", "pdf"])

def clean_data(df):
    """
    指示されたルールでデータをクリーニングする関数
    - /n (改行) があれば、そこでストップ（名前のみ抽出）
    - None (NaN) は空白（空文字）として扱う
    """
    # 0列目の名前処理
    if 0 in df.columns:
        df.iloc[:, 0] = df.iloc[:, 0].apply(
            lambda x: str(x).split('\n')[0] if pd.notnull(x) else ""
        )
    # NaNを空白に置き換え
    df = df.fillna("")
    return df

if uploaded_file:
    # 拡張子に合わせて読み込み
    if uploaded_file.name.endswith('.csv'):
        df_data = pd.read_csv(uploaded_file)
    else:
        # PDFの場合の処理（既存のpdfplumberロジック）
        import pdfplumber
        with pdfplumber.open(uploaded_file) as pdf:
            table = pdf.pages[0].extract_table()
            df_data = pd.DataFrame(table)

    # クリーニング適用
    df_clean = clean_data(df_data)

    # 表示
    st.write("### クリーニング後のデータ")
    st.dataframe(df_clean)

    # これ以降に my_daily_shift などの抽出処理を記述
