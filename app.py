def process_data(df):
    location_data = {}
    # A列が値を持つ行を「勤務地行」としてインデックスを取得
    location_indices = df[df.iloc[:, 0].notna()].index.tolist()
    
    for i, start_idx in enumerate(location_indices):
        key = str(df.iloc[start_idx, 0])
        
        # 範囲確定：次の勤務地行の手前までを正確に取得
        end_idx = location_indices[i+1] if i+1 < len(location_indices) else len(df)
        schedule = df.iloc[start_idx:end_idx].copy()
        
        # --- 列方向の処理 ---
        # 勤務地行(scheduleの0行目)のD列(index 3)以降を走査
        # 「数値である限り変換し、Noneや文字が現れたらその列以降を切り取る」
        
        target_cols_limit = schedule.shape[1] # デフォルトは全列
        
        for col_idx in range(3, schedule.shape[1]):
            val = schedule.iloc[0, col_idx]
            
            # None/NaN判定と数値判定
            if pd.isna(val):
                target_cols_limit = col_idx
                break
                
            try:
                # 数値であれば時刻に変換
                f_val = float(val)
                schedule.iloc[0, col_idx] = format_time(f_val)
            except (ValueError, TypeError):
                # 数値に変換できないもの（文字列等）が現れたら切り取り
                target_cols_limit = col_idx
                break
        
        # 確定した列数で切り取り（勤務地行およびその下の行すべてに適用）
        schedule = schedule.iloc[:, :target_cols_limit]
        
        location_data[key] = schedule
        
    return location_data
