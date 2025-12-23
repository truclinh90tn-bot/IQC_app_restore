import streamlit as st
import pandas as pd
import numpy as np

import qc_core as qc

from export.export_cstk_word import export_cstk
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

st.subheader("1️⃣ 🧮 Thiết lập chỉ số thống kê (X, SD, CV, CVh)")

st.markdown(
    "Nhập dữ liệu thiết lập CSTK cho từng mức QC."
)

num_levels = cfg["num_levels"]
default_rows = 20
cols = [f"Ctrl {i}" for i in range(1, num_levels + 1)]

cur_state = qc.get_current_analyte_state()

baseline_df = cur_state.get("baseline_df")
if baseline_df is None or list(baseline_df.columns) != cols:
    baseline_df = pd.DataFrame({c: [None] * default_rows for c in cols})

st.markdown("#### 📥 Bảng dữ liệu thiết lập ban đầu")

baseline_df = st.data_editor(
    baseline_df,
    num_rows="dynamic",
    use_container_width=True,
    key=f"baseline_editor_{num_levels}_{cfg['test_name']}",
    column_config={c: st.column_config.NumberColumn(c) for c in cols},
)
qc.update_current_analyte_state(baseline_df=baseline_df)

st.markdown("### 📌 Kết quả thống kê")

stats_rows = []
cvh_inputs = {}
sd_from_cvh = {}

col_stats = st.columns(num_levels)

for i, ctrl in enumerate(cols):
    with col_stats[i]:
        values = baseline_df[ctrl].tolist()
        mean, sd, cv = qc.compute_stats(values)

        st.markdown(f"**🧪 {ctrl}**")
        st.write(
            f"- X (Mean): `{mean:.4g}`" if not np.isnan(mean) else "- X (Mean): _chưa đủ dữ liệu_"
        )
        st.write(
            f"- SD: `{sd:.4g}`" if not np.isnan(sd) else "- SD: _chưa đủ dữ liệu_"
        )
        st.write(
            f"- CV% thực nghiệm: `{cv:.4g}`"
            if not np.isnan(cv)
            else "- CV% thực nghiệm: _chưa đủ dữ liệu_"
        )

        cvh = st.number_input(
            f"CV% mục tiêu (CVh) cho {ctrl}",
            min_value=0.0,
            value=float(cv) if not np.isnan(cv) else 0.0,
            step=0.1,
            key=f"cvh_{ctrl}_{cfg['test_name']}",
        )
        cvh_inputs[ctrl] = cvh

        if not np.isnan(mean):
            sd_cvh = mean * cvh / 100.0
        else:
            sd_cvh = np.nan
        sd_from_cvh[ctrl] = sd_cvh

        if not np.isnan(sd_cvh):
            st.write(f"- SD theo CVh: `{sd_cvh:.4g}`")
        else:
            st.write("- SD theo CVh: _chưa tính được_")

    stats_rows.append(
        {
            "Control": ctrl,
            "Mean_X": mean,
            "SD_empirical": sd,
            "CV_empirical_%": cv,
            "CVh_target_%": cvh_inputs[ctrl],
            "SD_from_CVh": sd_from_cvh[ctrl],
        }
    )

stats_df = pd.DataFrame(stats_rows)
st.markdown("#### 🧾 Bảng tổng hợp chỉ số thống kê")
st.dataframe(stats_df, use_container_width=True)

st.info(
    "Các giá trị Mean (X) và SD (thực nghiệm hoặc theo CVh) sẽ được dùng để tính z-score "
    "và đánh giá Westgard ở trang **2 – Ghi nhận & đánh giá**."
)

qc.update_current_analyte_state(qc_stats=stats_df)


st.markdown("---")
st.markdown("### 🖨️ Xuất Phiếu thiết lập CSTK (Word – A4)")

try:
    meta = ReportMeta(
        ten_xet_nghiem=cfg.get("test_name",""),
        thiet_bi_phuong_phap=f'{cfg.get("device","")} / {cfg.get("method","")}'.strip(" /"),
        lo_qc_han_dung=f'Lô: {cfg.get("qc_lot","")}  |  HSD: {cfg.get("qc_expiry","")}'.strip(),
    )
    # Header/footer theo mẫu Excel (chị có thể chỉnh nội dung trực tiếp trong template sau)
    meta.don_vi = cfg.get("don_vi","") or "{{DON_VI}}"
    meta.phien_ban = (f"Phiên bản: {cfg.get('phien_ban','')}" if cfg.get("phien_ban","") else "Phiên bản: {{PHIEN_BAN}}")
    meta.ngay_hieu_luc = (f"Ngày hiệu lực: {cfg.get('ngay_hieu_luc','')}" if cfg.get("ngay_hieu_luc","") else "Ngày hiệu lực: {{NGAY_HIEU_LUC}}")

    docx_buf = export_cstk(meta=meta, stats_df=stats_df, raw_df=None, num_levels=cfg.get('num_levels',3))

    st.download_button(
        f"📄 Tải Phiếu thiết lập CSTK ({cfg.get('num_levels',3)} mức) – .docx",
        data=docx_buf.getvalue(),
        file_name=f"Phieu_thiet_lap_CSTK_{cfg.get('test_name','') or 'Xet_nghiem'}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
except Exception as e:
    st.error(f"Không thể xuất CSTK: {e}")
