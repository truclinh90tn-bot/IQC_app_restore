import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

import qc_core as qc
from export.export_so_gn_dg_word import export_so_gn_dg
from export.word_reports import ReportMeta


qc.apply_page_config()
qc.inject_global_css()

# (NEW) login + lưu dữ liệu theo PXN
qc.require_login()

cfg = qc.render_sidebar()

sigma_cat, active_rules = qc.get_sigma_category_and_rules(
    cfg["sigma_value"], cfg["num_levels"]
)

qc.render_global_header()
qc.render_top_info_cards(cfg, sigma_cat, active_rules)

st.subheader("2️⃣ ✏️ Ghi nhận kết quả nội kiểm & đánh giá Westgard")

cur_state = qc.get_current_analyte_state()
qc_stats = cur_state.get("qc_stats")
num_levels = cfg["num_levels"]

if qc_stats is None or qc_stats.empty:
    st.warning("Chưa có dữ liệu thống kê QC ở trang 1. Vui lòng thiết lập trước.")
else:
    st.markdown("### 🔧 Chọn SD dùng để tính z-score")

    sd_mode = st.radio(
        "SD dùng để tính z-score",
        ["SD thực nghiệm", "SD theo CVh"],
        index=1,
        horizontal=True,
    )

    mean_dict = {}
    sd_dict = {}
    for _, row in qc_stats.iterrows():
        ctrl = row["Control"]
        mean_dict[ctrl] = row["Mean_X"]
        if sd_mode == "SD thực nghiệm":
            sd_dict[ctrl] = row["SD_empirical"]
        else:
            sd_dict[ctrl] = row["SD_from_CVh"]

    st.write("**Giá trị Mean & SD đang dùng:**")
    for ctrl in [f"Ctrl {i}" for i in range(1, num_levels + 1)]:
        m = mean_dict.get(ctrl, np.nan)
        s = sd_dict.get(ctrl, np.nan)
        if not np.isnan(m) and not np.isnan(s):
            st.write(f"- {ctrl}: Mean = `{m:.4g}`; SD = `{s:.4g}`")
        else:
            st.write(f"- {ctrl}: _chưa đủ thông tin (thiếu Mean/SD)_")

    sigma_cat_preview, active_rules_preview = qc.get_sigma_category_and_rules(
        cfg["sigma_value"], num_levels
    )
    st.markdown(
        f"**Sigma: {cfg['sigma_value']:.2f} → nhóm {sigma_cat_preview}-sigma.**  \n"
        f"Quy tắc loại bỏ: `{', '.join(sorted(active_rules_preview))}` "
        "(ngoài ra luôn có 1_2s là quy tắc cảnh báo)."
    )

    st.markdown("### 📋 Nhập kết quả nội kiểm hằng ngày")

    daily_df = cur_state.get("daily_df")
    if daily_df is None:
        data = {"Ngày/Lần": list(range(1, 21))}
        for ctrl in [f"Ctrl {i}" for i in range(1, num_levels + 1)]:
            data[ctrl] = [None] * 20
        daily_df = pd.DataFrame(data)


    # Đồng bộ cột theo số mức QC (tránh lỗi khi đổi 2↔3 mức: thiếu/ thừa cột Ctrl)
    required_cols = ["Ngày/Lần"] + [f"Ctrl {i}" for i in range(1, num_levels + 1)]
    # Thêm cột còn thiếu
    for c in required_cols:
        if c not in daily_df.columns:
            daily_df[c] = np.nan
    # Bỏ các cột Ctrl thừa nếu trước đó nhập 3 mức rồi chuyển về 2 mức
    extra_ctrl_cols = [c for c in daily_df.columns if c.startswith("Ctrl ") and c not in required_cols]
    if extra_ctrl_cols:
        daily_df = daily_df.drop(columns=extra_ctrl_cols)
    # Sắp xếp lại thứ tự cột cho đẹp
    daily_df = daily_df[required_cols]

    daily_df = st.data_editor(
        daily_df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"daily_editor_{num_levels}_{cfg['test_name']}",
        column_config={
            "Ngày/Lần": st.column_config.NumberColumn("Ngày/Lần", disabled=True),
            **{
                f"Ctrl {i}": st.column_config.NumberColumn(f"Ctrl {i}")
                for i in range(1, num_levels + 1)
            },
        },
    )
    qc.update_current_analyte_state(daily_df=daily_df)

    # Tính z-score
    zscore_cols = {}
    for lvl in range(1, num_levels + 1):
        ctrl = f"Ctrl {lvl}"
        mean = mean_dict.get(ctrl, np.nan)
        sd = sd_dict.get(ctrl, np.nan)
        z_col = f"z_Ctrl {lvl}"
        zscore_cols[z_col] = [
            qc.compute_zscore(v, mean, sd) if v not in (None, "") else np.nan
            for v in daily_df.get(ctrl, pd.Series([np.nan]*len(daily_df))).tolist()
        ]

    z_df = pd.DataFrame({"Ngày/Lần": daily_df["Ngày/Lần"], **zscore_cols})

    st.markdown("### 📈 Bảng z-score")
    st.dataframe(z_df, use_container_width=True)
    qc.update_current_analyte_state(z_df=z_df)

    if not z_df.drop(columns=["Ngày/Lần"]).isna().all().all():
        sigma_cat2, active_rules2, summary_df, point_df = qc.evaluate_westgard(
            z_df, num_levels=num_levels, sigma=cfg["sigma_value"]
        )

        st.markdown("### ✅ Đánh giá theo quy tắc Westgard (theo sigma)")
        st.write(
            f"Nhóm sigma đang áp dụng: **{sigma_cat2}-sigma**  "
            f"→ Quy tắc loại bỏ: `{', '.join(sorted(active_rules2))}` "
            "(ngoài ra luôn có 1_2s là quy tắc cảnh báo)."
        )

        st.dataframe(summary_df, use_container_width=True)

        # Cho phép nhập 'Người thực hiện' theo từng ngày (trước khi xuất Word/Excel)
        st.markdown("#### ✍️ Người thực hiện theo ngày")
        edit_people = summary_df[["Ngày/Lần", "Người thực hiện"]].copy()
        edit_people = st.data_editor(
            edit_people,
            use_container_width=True,
            num_rows="fixed",
            hide_index=True,
            column_config={
                "Ngày/Lần": st.column_config.TextColumn("Ngày/Lần", disabled=True),
                "Người thực hiện": st.column_config.TextColumn("Người thực hiện"),
            },
            key="people_editor",
        )
        # Ghi lại vào summary_df
        summary_df = summary_df.drop(columns=["Người thực hiện"]).merge(edit_people, on="Ngày/Lần", how="left")
        qc.update_current_analyte_state(summary_df=summary_df, point_df=point_df)

        st.info(
            "• **Đạt**: không vi phạm quy tắc loại bỏ.\n"
            "• **Cảnh báo (1_2s)**: chỉ vi phạm 1_2s.\n"
            "• **Không đạt (Reject QC)**: vi phạm ≥1 quy tắc loại bỏ theo bộ quy tắc sigma.\n"
            "• Cột **'Vi phạm loại bỏ'** gộp cả cảnh báo và loại bỏ.\n"
            "• **'Người thực hiện'** để ghi tay sau khi xuất Excel."
        )

        # Chuẩn bị dữ liệu xuất sổ theo dõi
        export_df = daily_df.copy()
        for col in z_df.columns:
            if col != "Ngày/Lần":
                export_df[col] = z_df[col]
        export_df = export_df.merge(summary_df, on="Ngày/Lần", how="left")

        ctrl_cols = [
            f"Ctrl {i}"
            for i in range(1, num_levels + 1)
            if f"Ctrl {i}" in export_df.columns
        ]
        z_cols_out = [
            f"z_Ctrl {i}"
            for i in range(1, num_levels + 1)
            if f"z_Ctrl {i}" in export_df.columns
        ]
        tail_cols = [
            c
            for c in ["Trạng thái", "Vi phạm loại bỏ", "Người thực hiện"]
            if c in export_df.columns
        ]
        ordered_cols = ["Ngày/Lần"] + ctrl_cols + z_cols_out + tail_cols
        export_df = export_df[ordered_cols]

        st.markdown("### 📤 Xuất Excel 'Sổ theo dõi KQ NK'")

        file_name = (
            f"So_theo_doi_KQ_NK_{cfg['test_name'] if cfg['test_name'] else 'Xet_nghiem'}.xlsx"
        )
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, sheet_name="So theo doi KQ NK", index=False)
        buffer.seek(0)

        st.download_button(
            label="⬇️ Tải file Excel 'Sổ theo dõi KQ NK'",
            data=buffer,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        qc.update_current_analyte_state(export_df=export_df)
    else:
        st.warning(
            "Chưa có giá trị z-score nào (tất cả đang trống). Hãy nhập kết quả nội kiểm."
        )


# Xuất Word A4: Sổ ghi nhận & đánh giá (2/3 mức) + biểu đồ Levey–Jennings (giống app)
st.markdown("### 🖨️ Xuất Word A4 (Sổ ghi nhận & đánh giá)")
st.caption("Thông tin biểu mẫu được lấy từ sidebar (không nhập lặp lại).")
ten_xn = cfg.get("test_name","")
thiet_bi_pp = f'{cfg.get("device","")} / {cfg.get("method","")}'.strip(" /")
lo_qc_hd = f'Lô: {cfg.get("qc_lot","")}  |  HSD: {cfg.get("qc_expiry","")}'.strip()
thang_nam = cfg.get("report_period","")
meta = ReportMeta(
    don_vi=cfg.get("don_vi","") or "{DON_VI}",
    phien_ban=(f'Phiên bản: {cfg.get("phien_ban","")}' if cfg.get("phien_ban","") else "Phiên bản: {PHIEN_BAN}"),
    ngay_hieu_luc=(f'Ngày hiệu lực: {cfg.get("ngay_hieu_luc","")}' if cfg.get("ngay_hieu_luc","") else "Ngày hiệu lực: {NGAY_HIEU_LUC}"),
    ten_xet_nghiem=ten_xn,
    thiet_bi_phuong_phap=thiet_bi_pp,
    lo_qc_han_dung=lo_qc_hd,
    thang_nam=thang_nam,
)


if st.button("📄 Tạo file Word A4 (Sổ ghi nhận & đánh giá)"):
    try:
        z_df_state = qc.get_current_analyte_state().get("z_df")
        point_df_state = qc.get_current_analyte_state().get("point_df")

        # Dùng summary_df làm bảng xuất (ổn định nhất)
        base_df = summary_df.copy()

        # (tuỳ chọn) đảm bảo cột "Người thực hiện" tồn tại
        if "Người thực hiện" not in base_df.columns:
            base_df["Người thực hiện"] = ""

        docx_buf = export_so_gn_dg(
            meta=meta,
            export_df=base_df,
            z_df=z_df_state,
            point_df=point_df_state,
            num_levels=int(cfg.get("num_levels", 3)),
        )

        st.download_button(
            label=f"⬇️ Tải file Word A4 'Sổ ghi nhận & đánh giá ({cfg.get('num_levels',3)} mức)'",
            data=docx_buf,
            file_name=f"So_ghi_nhan_danh_gia_{cfg.get('num_levels',3)}muc_{ten_xn or 'IQC'}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except Exception as e:
        st.error(f"Không thể xuất Word: {e}")
