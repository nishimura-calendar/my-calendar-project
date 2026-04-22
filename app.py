# 1. PDFの解析と整合性チェック
        pdf_results, year, month, consistency_report = p0.pdf_reader(uploaded_pdf, target_staff, uploaded_pdf.name)
        
        # 整合性エラーがある場合の表示
        if consistency_report:
            for place, report in consistency_report.items():
                st.error(f"⚠️ {place} のデータ整合性チェックに失敗しました。")
                st.warning(f"理由: {report['reason']}")
                with st.expander("PDFから抽出された生データを確認する"):
                    st.dataframe(report['df'])
            st.info("ファイル名またはPDFの内容が正しいか確認してください。")
            # 一致していなければここで停止
            if not pdf_results:
                st.stop()

        # 2. 時程表の取得
        time_dic = p0.time_schedule_from_drive(service, sheet_id)

        # 3. 紐付け確認用の表示 (デバッグ中のみ)
        if pdf_results:
            st.success(f"✅ 解析対象: {year}年{month}月")
            for place, data in pdf_results.items():
                st.divider()
                st.subheader(f"📍 勤務地: {place}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("🟢 **my_daily_shift**")
                    st.dataframe(data[0], use_container_width=True)
                with col2:
                    st.write("👥 **other_daily_shift**")
                    st.dataframe(data[1], use_container_width=True)
                
                if place in time_dic:
                    st.write(f"🕒 **time_schedule ({place})**")
                    st.dataframe(time_dic[place], use_container_width=True)
                else:
                    st.error(f"時程表に '{place}' というシートが見つかりません。")

        # 4. 直接解析へ進む
        # (pdf_results があり、エラーがなければ自動的に後続のCSV生成ロジックが走る)
