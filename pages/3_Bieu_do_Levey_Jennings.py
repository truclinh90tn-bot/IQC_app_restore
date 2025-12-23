import streamlit as st
import pandas as pd
import os

import qc_core as qc


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

st.subheader("3️⃣ 📊 Biểu đồ Levey–Jennings (z-score)")

cur_state = qc.get_current_analyte_state()
z_df = cur_state.get("z_df")
point_df = cur_state.get("point_df")
num_levels = cfg["num_levels"]

if z_df is None or z_df.empty:
    st.warning(
        "Chưa có dữ liệu z-score cho xét nghiệm này. "
        "Vào trang **2 – Ghi nhận & đánh giá** để tính trước."
    )
else:
    if point_df is None or point_df.empty:
        _, _, _, point_df = qc.evaluate_westgard(
            z_df, num_levels=num_levels, sigma=cfg["sigma_value"]
        )
        qc.update_current_analyte_state(point_df=point_df)

    point_idx = point_df.set_index(["Ngày/Lần", "Control"])

    runs = z_df["Ngày/Lần"].tolist()
    z_cols = [c for c in z_df.columns if c.startswith("z_Ctrl")]
    z_cols = sorted(z_cols, key=lambda x: int(x.split("Ctrl ")[1]))

    df_long_rows = []
    for idx, run in enumerate(runs):
        for lvl, z_col in enumerate(z_cols, start=1):
            z_val = z_df.loc[idx, z_col]
            if pd.isna(z_val):
                continue
            ctrl_name = f"Ctrl {lvl}"
            key = (run, ctrl_name)
            if key in point_idx.index:
                row = point_idx.loc[key]
                p_status = row["point_status"]
                r_codes = row["rule_codes"]
            else:
                p_status = "Đạt"
                r_codes = ""
            short = qc.extract_rule_short(r_codes)
            df_long_rows.append(
                {
                    "Run": int(run),
                    "Control": ctrl_name,
                    "z_score": float(z_val),
                    "point_status": p_status,
                    "rule_codes": r_codes,
                    "rule_short": short,
                }
            )

    df_long = pd.DataFrame(df_long_rows)

    if df_long.empty:
        st.warning("Không có điểm z-score hợp lệ để vẽ biểu đồ.")
    else:
        chart_col, info_col = st.columns([3, 2])

        with chart_col:
            chart = qc.create_levey_jennings_chart(
                df_long,
                title=f"Biểu đồ Levey–Jennings – {cfg['test_name'] or 'Xét nghiệm'}",
            )
            if chart is not None:
                st.altair_chart(chart, use_container_width=True)

        with info_col:
            st.markdown("#### 🧭 Cách đọc nhanh")
            st.markdown(
                "- **Đường 0**: giá trị trung tâm (Mean).\n"
                "- **±1SD (xanh)**: vùng tốt.\n"
                "- **±2SD (cam)**: vùng cảnh báo.\n"
                "- **±3SD (đỏ)**: vùng loại bỏ.\n"
                "- Điểm **vuông**: |z| > 3, đặt trên line ±3SD.\n"
                "- Điểm có **vòng đỏ + mã quy tắc**: vi phạm Westgard."
            )

            lj_demo_path = "assets/levey_jennings_demo.png"
            if os.path.exists(lj_demo_path):
                st.image(
                    lj_demo_path,
                    caption="Minh hoạ biểu đồ Levey–Jennings (chị có thể thay bằng hình của labo).",
                    use_container_width=True,
                )
            else:
                st.caption(
                    "📌 Thêm hình minh hoạ vào `assets/levey_jennings_demo.png` để hiển thị tại đây."
                )

        st.markdown("### 🔎 Dữ liệu đang dùng để vẽ")
        st.dataframe(df_long, use_container_width=True)

        st.success(
            "• Điểm bình thường: dấu tròn tại z-score.\n"
            "• |z| > 3: dấu vuông nằm trên đường ±3SD, tooltip vẫn hiển thị z-score thật.\n"
            "• Control vi phạm: khoanh đỏ + mã quy tắc (1_3s, 2_2s, 10x...)."
        )
