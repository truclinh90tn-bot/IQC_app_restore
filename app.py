import streamlit as st
import os
import pandas as pd

import qc_core as qc


qc.apply_page_config()
qc.inject_global_css()

# (NEW) Login + phân quyền + lưu dữ liệu theo PXN (Supabase)
qc.require_login()

cfg = qc.render_sidebar()

sigma_cat, active_rules = qc.get_sigma_category_and_rules(
    cfg["sigma_value"], cfg["num_levels"]
)

qc.render_global_header()
qc.render_top_info_cards(cfg, sigma_cat, active_rules)


st.markdown("### ⚡ Quick actions")

qa_col1, qa_col2, qa_col3, qa_col4 = st.columns(4)
with qa_col1:
    st.page_link(
        "pages/1_Thiet_lap_chi_so_thong_ke.py",
        label="Thiết lập chỉ số",
        icon="🧮",
    )
with qa_col2:
    st.page_link(
        "pages/2_Ghi_nhan_va_danh_gia.py",
        label="Ghi nhận & đánh giá",
        icon="✏️",
    )
with qa_col3:
    st.page_link(
        "pages/3_Bieu_do_Levey_Jennings.py",
        label="Biểu đồ LJ",
        icon="📊",
    )
with qa_col4:
    st.page_link(
        "pages/4_Huong_dan_va_About.py",
        label="Hướng dẫn",
        icon="📘",
    )

st.markdown("### 📊 Dashboard nội kiểm – Tổng quan")

col1, col2 = st.columns([2, 3])

cur_state = qc.get_current_analyte_state()

with col1:
    st.markdown("#### 📈 Tiến độ nhập dữ liệu IQC")
    daily_df = cur_state.get("daily_df")
    if isinstance(daily_df, pd.DataFrame) and not daily_df.empty:
        total_rows = len(daily_df)
        filled_rows = (
            daily_df[[c for c in daily_df.columns if c.startswith("Ctrl")]]
            .dropna(how="all")
            .shape[0]
        )
        st.metric("Số dòng đã nhập", f"{filled_rows}/{total_rows}")
    else:
        st.info(
            "Chưa có dữ liệu nội kiểm cho xét nghiệm này. "
            "Vào trang **2_Ghi_nhan_va_danh_gia** để nhập."
        )

    st.markdown("#### 🧮 Tóm tắt chỉ số thống kê")
    stats_df = cur_state.get("qc_stats")
    if isinstance(stats_df, pd.DataFrame) and not stats_df.empty:
        st.dataframe(stats_df, use_container_width=True, height=230)
    else:
        st.caption(
            "Chưa thiết lập chỉ số thống kê cho xét nghiệm này. "
            "Vào trang **1_Thiet_lap_chi_so_thong_ke**."
        )

with col2:
    st.markdown("#### 🧷 Tình trạng QC gần đây")
    summary_df = cur_state.get("summary_df")
    if isinstance(summary_df, pd.DataFrame) and not summary_df.empty:
        st.dataframe(summary_df.tail(10), use_container_width=True, height=260)
    else:
        st.caption(
            "Chưa có đánh giá Westgard cho xét nghiệm này. "
            "Vào trang **2_Ghi_nhan_va_danh_gia** để tính."
        )

    st.markdown("#### 🧭 Gợi ý thao tác tiếp theo")
    st.markdown(
        """
        - Nếu **chưa có Mean, SD, CV%** → vào trang **1 – Thiết lập chỉ số thống kê**.  
        - Nếu đã có Mean & SD → vào trang **2 – Ghi nhận & đánh giá** để nhập IQC hằng ngày.  
        - Muốn xem biểu đồ trực quan → trang **3 – Biểu đồ Levey–Jennings**.  
        - Xem hướng dẫn chi tiết → trang **4 – Hướng dẫn & About**.
        """
    )
