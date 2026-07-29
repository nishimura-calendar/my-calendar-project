import pandas as pd

def find_key_position(df):
    """
    DataFrameの中から 'T1' または 'T2' を探し、その行番号(row)と列番号(col)を返す
    """
    for row_idx in range(df.shape[0]):
        for col_idx in range(df.shape[1]):
            val = str(df.iloc[row_idx, col_idx])
            # T1 または T2 を検索（部分一致）
            if "T1" in val or "T2" in val:
                return row_idx, col_idx
    return None, None

# 使用例:
# row, col = find_key_position(df_pdf)
# if row is not None:
#     st.write(f"キーが見つかりました: {row}行目, {col}列目")
#     found_key = df_pdf.iloc[row, col]
