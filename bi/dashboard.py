from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import psycopg

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from analysis_utils import completeness, district_comparison, duplicate_candidates, source_composition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from db.client import connect, read_listings, version as database_version

SOURCE, ID, TITLE, URL = "Nguồn", "Mã tin", "Tiêu đề", "Liên kết tin gốc"
DISTRICT, WARD, KIND = "Quận/huyện cũ", "Phường/xã mới", "Loại chỗ ở"
PRICE, AREA, UNIT = "Giá thuê (đồng/tháng)", "Diện tích (m²)", "Giá thuê/m² (đồng/tháng)"
MILLION, THOUSAND = "Giá (triệu đồng/tháng)", "Giá/m² (nghìn đồng/tháng)"
KINDS = ["phòng trọ", "căn hộ", "nhà nguyên căn", "biệt thự"]
COLORS = dict(zip(KINDS, ["#138796", "#5376BC", "#9C6EB0", "#CB8A47"]))
FILTER_KEYS = ["districts", "kinds", "sources", "wards", "limit_price", "price_min",
               "price_max", "limit_area", "area_min", "area_max", "comparison"]

st.set_page_config(page_title="Giá thuê nhà ở Hà Nội", page_icon="🏠", layout="wide")
st.markdown("""<style>
.stApp {background: #F6F8FA;}
[data-testid="stSidebar"] {background: #FFFFFF;}
.block-container {padding-top: 2.2rem; padding-bottom: 3rem;}
[data-testid="stMetric"] {background: white; border: 1px solid #E0E8EB;
    border-radius: 12px; padding: 16px;}
[data-testid="stMetricValue"] {color: #117884;}
h1, h2, h3 {color: #18343F;}
[data-testid="stTabs"] button {font-weight: 600;}
</style>""", unsafe_allow_html=True)


def file_version():
    return database_version()


@st.cache_data(show_spinner=False, max_entries=3)
def load_data(run_id):
    df = read_listings(run_id=run_id)
    required = {SOURCE, ID, TITLE, URL, DISTRICT, WARD, KIND, PRICE, AREA, UNIT}
    if not required.issubset(df.columns):
        raise ValueError("File dữ liệu không có đủ các cột cần thiết.")
    for column in [PRICE, AREA, UNIT]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df[MILLION] = df[PRICE] / 1_000_000
    df[THOUSAND] = df[UNIT] / 1_000
    return df


@st.fragment(run_every=10)
def watch_data():
    try:
        version = file_version()
    except (psycopg.Error, ValueError):
        return
    if st.session_state.get("data_version") != version:
        st.session_state["data_version"] = version
        st.rerun()


def reset_filters():
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def count(value):
    return f"{int(value):,}".replace(",", ".")


def number(value, digits=1):
    return "—" if pd.isna(value) else f"{value:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def show_chart(fig, key):
    fig.update_layout(template="plotly_white", font=dict(family="Arial", size=13, color="#284552"),
                      margin=dict(l=10, r=20, t=45, b=20), paper_bgcolor="white",
                      colorway=list(COLORS.values()), legend_title_text="Loại chỗ ở")
    st.plotly_chart(fig, width="stretch", key=key, config={"displaylogo": False})


def group_prices(df, value, minimum):
    return (df.groupby(DISTRICT)[value].agg(["count", "median"])
            .query("count >= @minimum").sort_values("median").reset_index())


def median_bar(stats, label, key, unit="triệu đồng/tháng"):
    if stats.empty:
        st.info("Chưa đủ tin để so sánh khu vực với bộ lọc này.")
        return
    data = stats.copy()
    data["Nhãn"] = data.apply(lambda r: f"{number(r['median'], 2)} · n={int(r['count'])}", axis=1)
    fig = px.bar(data, x="median", y=DISTRICT, orientation="h", text="Nhãn",
                 labels={"median": label}, color_discrete_sequence=["#138796"],
                 custom_data=["count"])
    fig.update_traces(textposition="outside", cliponaxis=False,
                      hovertemplate="%{y}<br>Trung vị: %{x:.2f} " + unit + "<br>Số tin: %{customdata[0]}<extra></extra>")
    fig.update_layout(height=max(330, 35 * len(data) + 100), yaxis=dict(autorange="reversed"),
                      xaxis=dict(range=[0, data["median"].max() * 1.38]))
    show_chart(fig, key)
    low, high = data.iloc[0], data.iloc[-1]
    st.caption(f"{low[DISTRICT]}: {number(low['median'], 2)} {unit} (n={int(low['count'])}); "
               f"{high[DISTRICT]}: {number(high['median'], 2)} {unit} (n={int(high['count'])}).")


def recommend(df, budget, min_area, housing, order):
    matches = df.loc[df[KIND].eq(housing) & df[PRICE].gt(0) & df[PRICE].le(budget * 1e6)
                     & df[AREA].ge(min_area) & df[UNIT].gt(0)].copy()
    matches["Diện tích vượt yêu cầu"] = matches[AREA] - min_area
    if order == "Cân bằng giá và diện tích":
        price_range = matches[PRICE].max() - matches[PRICE].min()
        area_range = matches[AREA].max() - matches[AREA].min()
        cost_score = (matches[PRICE].max() - matches[PRICE]) / price_range if price_range else pd.Series(1.0, index=matches.index)
        space_score = (matches[AREA] - matches[AREA].min()) / area_range if area_range else pd.Series(1.0, index=matches.index)
        matches["Điểm phù hợp"] = (100 * (.6 * cost_score + .4 * space_score)).round(1)
        matches["Lý do xếp hạng"] = "60% chi phí thuê, 40% diện tích trong tập phù hợp"
        matches = matches.sort_values(["Điểm phù hợp", PRICE, SOURCE, ID], ascending=[False, True, True, True])
    else:
        priority = [UNIT, "Diện tích vượt yêu cầu"] if order == "Giá/m² thấp nhất" else ["Diện tích vượt yêu cầu", UNIT]
        matches = matches.sort_values(priority + [PRICE, SOURCE, ID])
    return matches.drop(columns="Diện tích vượt yêu cầu")


try:
    version = file_version()
    st.session_state["data_version"] = version
    watch_data()
    data = load_data(version[0])
except (OSError, ValueError, psycopg.Error) as error:
    st.error("Chưa đọc được PostgreSQL. Kiểm tra .env, khởi động PostgreSQL và chạy etl.py.")
    with st.expander("Chi tiết lỗi"):
        st.code(str(error))
    if st.button("Thử lại"):
        st.rerun()
    st.stop()

with st.sidebar:
    st.subheader("Phạm vi phân tích")
    st.caption("Các lựa chọn áp dụng cho biểu đồ và gợi ý thuê.")
    districts = st.multiselect("Khu vực quận/huyện cũ", sorted(data[DISTRICT].dropna().unique()),
                               placeholder="Tất cả khu vực", key="districts")
    kinds = st.multiselect("Loại chỗ ở", KINDS, default=KINDS, key="kinds")
    sources = st.multiselect("Nguồn dữ liệu", sorted(data[SOURCE].unique()),
                             default=sorted(data[SOURCE].unique()), key="sources")
    ward_data = data.loc[data[DISTRICT].isin(districts)] if districts else data
    ward_options = sorted(ward_data[WARD].dropna().unique())
    if "wards" in st.session_state:
        st.session_state["wards"] = [w for w in st.session_state["wards"] if w in ward_options]
    wards = st.multiselect("Phường/xã mới đã xác định", ward_options,
                           placeholder="Tất cả, kể cả tin chưa rõ phường", key="wards")
    st.divider()
    limit_price = st.checkbox("Giới hạn giá thuê", key="limit_price")
    c1, c2 = st.columns(2)
    lower_price = c1.number_input("Từ (triệu/tháng)", 0.0, 500.0, 0.0, 0.5, key="price_min", disabled=not limit_price)
    upper_price = c2.number_input("Đến (triệu/tháng)", 0.0, 500.0, 20.0, 0.5, key="price_max", disabled=not limit_price)
    limit_area = st.checkbox("Giới hạn diện tích", key="limit_area")
    c1, c2 = st.columns(2)
    lower_area = c1.number_input("Từ (m²)", 5.0, 1000.0, 5.0, 5.0, key="area_min", disabled=not limit_area)
    upper_area = c2.number_input("Đến (m²)", 5.0, 1000.0, 100.0, 5.0, key="area_max", disabled=not limit_area)
    st.button("Đặt lại bộ lọc", on_click=reset_filters, width="stretch")
    st.caption("Khu vực sử dụng tên quận/huyện trước sắp xếp. Phường/xã mới chỉ có ở tin xác định được.")

filtered = data.loc[data[KIND].isin(kinds) & data[SOURCE].isin(sources)].copy()
if districts:
    filtered = filtered.loc[filtered[DISTRICT].isin(districts)]
unknown_wards = int(filtered[WARD].isna().sum())
if wards:
    filtered = filtered.loc[filtered[WARD].isin(wards)]
if (limit_price and lower_price > upper_price) or (limit_area and lower_area > upper_area):
    st.warning("Giới hạn dưới cần nhỏ hơn hoặc bằng giới hạn trên.")
    st.stop()
if limit_price:
    filtered = filtered.loc[filtered[MILLION].between(lower_price, upper_price)]
if limit_area:
    filtered = filtered.loc[filtered[AREA].between(lower_area, upper_area)]

st.title("Giá thuê nhà ở Hà Nội")
st.caption(f"Nguồn vận hành: PostgreSQL · ETL #{version[0]}")
st.caption("So sánh khu vực, tìm khoảng giá phù hợp và lựa chọn chỗ ở theo nhu cầu.")
st.caption(f"Phongtro123 · Catalyst  |  {count(len(data))} tin trong bộ dữ liệu  |  "
           f"Cập nhật {datetime.fromisoformat(version[1]).astimezone(ZoneInfo('Asia/Ho_Chi_Minh')):%d/%m/%Y %H:%M}")
st.caption("Giá chào thuê từ tin đăng tham khảo; cần kiểm tra tin gốc để biết tình trạng cho thuê hiện tại.")
if wards:
    st.info(f"Bộ lọc phường/xã chỉ xét tin đã xác định được; {count(unknown_wards)} tin chưa rõ phường/xã trong phạm vi nguồn, loại và khu vực đã chọn.")
if filtered.empty:
    st.info("Không có tin phù hợp. Hãy nới khoảng giá, diện tích hoặc chọn thêm khu vực và loại chỗ ở.")
    st.stop()

priced = filtered.loc[filtered[PRICE].gt(0)]
paired = filtered.loc[filtered[PRICE].gt(0) & filtered[AREA].gt(0)]
metrics = st.columns(4)
metrics[0].metric("Tin trong phạm vi", count(len(filtered)))
metrics[1].metric("Giá trung vị", number(priced[MILLION].median()), help="Triệu đồng/tháng")
metrics[2].metric("Diện tích trung vị", number(filtered[AREA].median(), 0) + " m²")
metrics[3].metric("Khu vực", count(filtered[DISTRICT].nunique()))
st.caption(f"Giá trung vị (triệu đồng/tháng) từ {count(len(priced))} tin có giá; {count(len(paired))} tin đủ giá và diện tích. "
           "Khi chọn nhiều loại chỗ ở, trung vị chung phản ánh cơ cấu loại trong phạm vi đã chọn.")

compare_kinds = [k for k in KINDS if k in kinds]
comparison = st.selectbox("Loại chỗ ở để so sánh khu vực", compare_kinds, key="comparison")
focus = priced.loc[priced[KIND].eq(comparison)]
geo = group_prices(focus, MILLION, 20)
focus_geo = focus.loc[focus[DISTRICT].isin(geo[DISTRICT])]
tab_geo, tab_budget, tab_find, tab_compare, tab_quality = st.tabs([
    "Giá theo khu vực", "Ngân sách & diện tích", "Gợi ý thuê nhà",
    "So sánh khu vực", "Chất lượng dữ liệu"
])

with tab_geo:
    st.subheader("1. Phân bố giá theo loại chỗ ở")
    fig = make_subplots(rows=2, cols=2, subplot_titles=[k.title() for k in KINDS])
    summaries = []
    for i, housing in enumerate(KINDS):
        values = priced.loc[priced[KIND].eq(housing), MILLION]
        row, col = i // 2 + 1, i % 2 + 1
        if values.empty:
            continue
        visible = values.loc[values.le(values.quantile(.99))]
        fig.add_trace(go.Histogram(x=visible, nbinsx=min(24, max(6, int(np.sqrt(len(values))))),
                                   marker_color=COLORS[housing], name=housing,
                                   hovertemplate="Khoảng giá: %{x} triệu<br>Số tin: %{y}<extra></extra>"), row=row, col=col)
        fig.add_vline(x=values.median(), line_dash="dash", line_color="#B64942", row=row, col=col)
        fig.update_xaxes(title_text="Triệu đồng/tháng", row=row, col=col)
        fig.update_yaxes(title_text="Số tin", row=row, col=col)
        summaries.append(f"{housing.title()}: {number(values.median())} triệu (n={count(len(values))})")
    fig.update_layout(height=570, showlegend=False)
    show_chart(fig, "distribution")
    st.caption("; ".join(summaries) + ". Mỗi khung hiển thị đến phân vị 99%; trung vị tính từ toàn bộ tin có giá.")

    st.subheader(f"2. Giá {comparison} trung vị theo khu vực")
    median_bar(geo, "Trung vị giá thuê (triệu đồng/tháng)", "district_price")

    st.subheader("3. Giá theo khu vực và loại chỗ ở")
    pairs = priced.groupby([DISTRICT, KIND])[MILLION].agg(["count", "median"])
    medians = pairs["median"].where(pairs["count"].ge(10)).unstack().reindex(columns=kinds).dropna(how="all").dropna(axis=1, how="all")
    if medians.empty:
        st.info("Chưa có nhóm khu vực và loại chỗ ở đủ 10 tin có giá.")
    else:
        ns = pairs["count"].unstack().reindex(index=medians.index, columns=medians.columns)
        labels = np.array([["" if pd.isna(v) else f"{v:.1f}<br>n={int(ns.iloc[i,j])}" for j,v in enumerate(row)] for i,row in enumerate(medians.to_numpy())])
        fig = go.Figure(go.Heatmap(z=medians.to_numpy(), x=medians.columns, y=medians.index,
                                   text=labels, texttemplate="%{text}", colorscale="YlOrRd",
                                   customdata=ns.to_numpy(), colorbar=dict(title="Triệu/tháng"),
                                   hovertemplate="%{y}<br>%{x}: %{z:.2f} triệu/tháng<br>Số tin: %{customdata}<extra></extra>"))
        fig.update_layout(height=max(420, 38*len(medians)+100), yaxis=dict(autorange="reversed"))
        show_chart(fig, "district_type")

    st.subheader(f"4. Khoảng giá {comparison} theo khu vực")
    if focus_geo.empty:
        st.info("Chưa đủ tin cùng loại để thể hiện khoảng giá theo khu vực.")
    else:
        fig = px.box(focus_geo, x=MILLION, y=DISTRICT, points=False,
                     category_orders={DISTRICT:geo[DISTRICT].tolist()}, color_discrete_sequence=["#69A5B2"])
        fig.update_layout(height=max(360, 35*len(geo)+100))
        show_chart(fig, "price_spread")
        q = focus_geo.groupby(DISTRICT)[MILLION].quantile([.25,.75]).unstack()
        widest = (q[.75]-q[.25]).idxmax()
        st.caption(f"{widest}: khoảng giữa 50% tin từ {number(q.loc[widest,.25],2)} đến {number(q.loc[widest,.75],2)} triệu/tháng, rộng nhất trong các khu vực trên hình.")

    st.subheader(f"5. Giá {comparison} trên mỗi m²")
    unit_geo = group_prices(focus.loc[focus[UNIT].gt(0)], THOUSAND, 20)
    median_bar(unit_geo, "Trung vị nghìn đồng/m²/tháng", "district_unit", "nghìn đồng/m²/tháng")

    st.subheader(f"6. So sánh {comparison} cùng nhóm diện tích 20–<30 m²")
    same_area = focus.loc[focus[AREA].ge(20) & focus[AREA].lt(30)]
    median_bar(group_prices(same_area, MILLION, 10), "Trung vị giá thuê (triệu đồng/tháng)", "same_area")
    st.caption("Biểu đồ giá khu vực dùng tối thiểu 20 tin có giá; nhóm 20–<30 m² dùng tối thiểu 10 tin.")

with tab_budget:
    st.subheader(f"7. Tỷ lệ {comparison} đáp ứng ngân sách")
    budget = st.number_input("Ngân sách tham khảo (triệu đồng/tháng)", .5, 500.0, 3.0, .5, key="chart_budget")
    if focus_geo.empty:
        st.info("Chưa đủ tin cùng loại để so sánh ngân sách theo khu vực.")
    else:
        shares = focus_geo.groupby(DISTRICT)[MILLION].apply(lambda x:100*x.le(budget).mean()).sort_values().reset_index(name="Tỷ lệ (%)")
        shares["Số tin"] = shares[DISTRICT].map(focus_geo.groupby(DISTRICT).size())
        fig = px.bar(shares, x="Tỷ lệ (%)", y=DISTRICT, orientation="h", text="Tỷ lệ (%)",
                     custom_data=["Số tin"], color_discrete_sequence=["#138796"])
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}<br>Đáp ứng: %{x:.1f}%<br>Tổng tin có giá: %{customdata[0]}<extra></extra>")
        fig.update_layout(height=max(340,35*len(shares)+100), xaxis=dict(range=[0,115]))
        show_chart(fig, "affordability")
        best = shares.iloc[-1]
        st.caption(f"Ngân sách {number(budget)} triệu: {best[DISTRICT]} có tỷ lệ đáp ứng cao nhất ({number(best['Tỷ lệ (%)'])}%, n={int(best['Số tin'])}).")

    st.subheader(f"8. Số tin {comparison} theo từng khoảng ngân sách")
    if not focus_geo.empty:
        counts = pd.DataFrame(index=geo[DISTRICT])
        for label, low, high in [("2–<3 triệu",2,3),("3–<5 triệu",3,5),("5–7 triệu",5,7)]:
            values = focus_geo[MILLION]
            mask = values.ge(low) & (values.le(high) if high==7 else values.lt(high))
            counts[label] = focus_geo.loc[mask].groupby(DISTRICT).size().reindex(counts.index, fill_value=0)
        counts = counts.loc[counts.sum(axis=1).sort_values(ascending=False).index]
        fig = go.Figure(go.Heatmap(z=counts.to_numpy(), x=counts.columns, y=counts.index,
                                   text=counts.to_numpy(), texttemplate="%{text}", colorscale="YlGnBu",
                                   colorbar=dict(title="Số tin"), hovertemplate="%{y}<br>%{x}: %{z} tin<extra></extra>"))
        fig.update_layout(height=max(340,35*len(counts)+100), yaxis=dict(autorange="reversed"))
        show_chart(fig, "budget_counts")
        best = counts["3–<5 triệu"].idxmax()
        st.caption(f"Khoảng 3–<5 triệu/tháng: {best} có {int(counts.loc[best,'3–<5 triệu'])} tin, nhiều nhất trong các khu vực trên hình.")

    st.subheader("9. Diện tích và giá thuê")
    if paired.empty:
        st.info("Chưa có tin đủ giá và diện tích với bộ lọc này.")
    else:
        visible = paired.loc[paired[AREA].le(paired[AREA].quantile(.99)) & paired[MILLION].le(paired[MILLION].quantile(.99))]
        fig = px.scatter(visible, x=AREA, y=MILLION, color=KIND, color_discrete_map=COLORS,
                         hover_data={DISTRICT:True, THOUSAND:":.0f"}, opacity=.55)
        fig.update_layout(height=460)
        show_chart(fig, "area_price")
        st.caption(f"Hiển thị {count(len(visible))}/{count(len(paired))} tin đủ giá và diện tích trong khung phân vị 99% của hai trục.")

    st.subheader(f"10. Giá {comparison} theo nhóm diện tích")
    groups = focus.loc[focus[AREA].gt(0)].copy()
    groups["Nhóm diện tích (m²)"] = pd.cut(groups[AREA], [5,15,20,25,30,40,60,np.inf], right=False,
                                            labels=["5–<15","15–<20","20–<25","25–<30","30–<40","40–<60","Từ 60"])
    stats = groups.groupby("Nhóm diện tích (m²)", observed=True)[MILLION].agg(["count","median"]).query("count>=20").reset_index()
    if stats.empty:
        st.info("Chưa có nhóm diện tích đủ 20 tin có giá.")
    else:
        stats["Nhãn"] = stats.apply(lambda r:f"{number(r['median'])} · n={int(r['count'])}",axis=1)
        fig = px.bar(stats, x="Nhóm diện tích (m²)", y="median", text="Nhãn",
                     labels={"median":"Trung vị triệu đồng/tháng"}, color_discrete_sequence=["#138796"])
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(height=370, yaxis=dict(range=[0,stats["median"].max()*1.3]))
        show_chart(fig, "area_groups")

with tab_find:
    st.subheader("Tìm chỗ ở phù hợp với bạn")
    st.caption("Chọn khu vực, nguồn và phường/xã ở thanh bên. Các yêu cầu dưới đây được áp dụng thêm cho gợi ý thuê.")
    c1,c2,c3 = st.columns(3)
    rental_budget = c1.number_input("Ngân sách tối đa (triệu/tháng)", .5, 500.0, 5.0, .5, key="rental_budget")
    rental_area = c2.number_input("Diện tích tối thiểu (m²)", 5.0, 1000.0, 20.0, 5.0, key="rental_area")
    rental_kind = c3.selectbox("Loại chỗ ở cần tìm", compare_kinds, key="rental_kind")
    rental_order = st.radio("Ưu tiên lựa chọn", ["Giá/m² thấp nhất","Diện tích sát yêu cầu","Cân bằng giá và diện tích"], horizontal=True, key="rental_order")
    st.caption("Chưa có thông tin tiện ích được xác nhận để làm bộ lọc.")
    matches = recommend(filtered, rental_budget, rental_area, rental_kind, rental_order)
    st.metric("Tin đáp ứng yêu cầu", count(len(matches)))
    if matches.empty:
        st.info("Chưa có lựa chọn phù hợp. Thử tăng ngân sách, giảm diện tích tối thiểu hoặc mở rộng khu vực ở thanh bên.")
    else:
        if rental_order == "Cân bằng giá và diện tích":
            st.caption("Điểm quy tắc 0–100, ưu tiên 60% tổng giá thuê thấp và 40% diện tích lớn trong các tin đã lọc. Điểm thay đổi theo tập được lọc, không phải dự đoán AI.")
        else:
            st.caption("Ưu tiên giá/m² thấp, sau đó diện tích gần mức tối thiểu." if rental_order=="Giá/m² thấp nhất"
                       else "Ưu tiên diện tích gần mức tối thiểu, sau đó giá/m² thấp.")
        table_columns = [TITLE, MILLION, AREA, THOUSAND, DISTRICT, WARD, SOURCE, URL]
        if "Điểm phù hợp" in matches:
            table_columns.insert(1, "Điểm phù hợp")
            table_columns.insert(2, "Lý do xếp hạng")
        table = matches[table_columns].head(50)
        st.dataframe(table, hide_index=True, width="stretch", column_config={
            MILLION:st.column_config.NumberColumn("Giá (triệu/tháng)",format="%.2f"),
            AREA:st.column_config.NumberColumn("Diện tích (m²)",format="%.0f"),
            THOUSAND:st.column_config.NumberColumn("Giá/m² (nghìn/tháng)",format="%.0f"),
            URL:st.column_config.LinkColumn("Tin gốc",display_text="Xem tin"),
        })
        st.caption(f"Hiển thị tối đa 50 trong {count(len(matches))} tin phù hợp. Tin thiếu giá hoặc diện tích không được xếp hạng.")
        export_columns = [SOURCE,ID,TITLE,DISTRICT,WARD,KIND,PRICE,AREA,UNIT,URL]
        if "Điểm phù hợp" in matches:
            export_columns += ["Điểm phù hợp", "Lý do xếp hạng"]
        st.download_button("Tải toàn bộ gợi ý (CSV)", matches[export_columns].to_csv(index=False).encode("utf-8-sig"),
                           file_name="goi_y_thue_nha.csv", mime="text/csv", key="download_matches")

with st.expander("Xem tin trong phạm vi đang chọn"):
    columns = [SOURCE,ID,TITLE,DISTRICT,WARD,KIND,AREA,PRICE,UNIT,URL]
    st.dataframe(filtered[columns], hide_index=True, width="stretch", column_config={
        URL:st.column_config.LinkColumn("Tin gốc",display_text="Xem tin"),
        PRICE:st.column_config.NumberColumn(PRICE,format="%.0f"),
        UNIT:st.column_config.NumberColumn("Giá thuê/m² (đồng/m²/tháng)",format="%.0f"),
    })
    st.download_button("Tải dữ liệu đang chọn (CSV)", filtered[columns].to_csv(index=False).encode("utf-8-sig"),
                       file_name="nha_thue_ha_noi_da_loc.csv", mime="text/csv", key="download_filtered")


with tab_compare:
    st.subheader("So sánh giá thuê giữa hai khu vực")
    st.caption("Giữ cùng loại nhà, nhóm diện tích và nguồn dữ liệu để hạn chế sai lệch khi so sánh.")
    options = sorted(filtered[DISTRICT].dropna().unique().tolist())
    if len(options) < 2:
        st.info("Cần ít nhất hai khu vực trong bộ lọc hiện tại.")
    else:
        col1, col2 = st.columns(2)
        left = col1.selectbox("Khu vực thứ nhất", options, index=0, key="compare_left")
        right = col2.selectbox("Khu vực thứ hai", options, index=1, key="compare_right")
        col3, col4, col5 = st.columns(3)
        kind_choice = col3.selectbox("Loại chỗ ở", compare_kinds, key="compare_kind")
        interval = col4.selectbox("Khoảng diện tích (m²)", ["15–<20", "20–<30", "30–<40", "40–<60", "60–<100", "100–<300"], index=1, key="compare_area")
        min_sample = col5.selectbox("Ngưỡng tin tối thiểu", [5, 10, 20], index=1, key="compare_minimum")
        low_text, high_text = interval.split("–<")
        comparison_stats, comparison_rows = district_comparison(filtered, left, right, kind_choice, float(low_text), float(high_text))
        if left == right:
            st.warning("Hãy chọn hai khu vực khác nhau.")
        elif comparison_stats.empty:
            st.info("Chưa có tin đủ giá và diện tích ở hai khu vực đã chọn.")
        else:
            comparison_stats = comparison_stats.set_index("Khu vực").reindex([left, right]).reset_index()
            st.dataframe(comparison_stats, hide_index=True, width="stretch", column_config={
                "Giá trung vị (triệu/tháng)": st.column_config.NumberColumn(format="%.2f"),
                "Giá/m² trung vị (nghìn/tháng)": st.column_config.NumberColumn(format="%.1f"),
                "Giá P25": st.column_config.NumberColumn(format="%.2f"),
                "Giá P75": st.column_config.NumberColumn(format="%.2f"),
            })
            insufficient = comparison_stats["Số tin"].fillna(0).lt(min_sample)
            if insufficient.any():
                st.warning("Có khu vực dưới ngưỡng số tin tối thiểu; chỉ xem kết quả như thông tin tham khảo, chưa đủ cơ sở kết luận.")
            else:
                fig = px.box(comparison_rows, x=DISTRICT, y=MILLION, points=False,
                             category_orders={DISTRICT: [left, right]}, color=DISTRICT,
                             labels={MILLION: "Giá thuê (triệu đồng/tháng)"})
                fig.update_layout(height=420, showlegend=False)
                show_chart(fig, "comparison_box")
                first, second = comparison_stats.iloc[0], comparison_stats.iloc[1]
                difference = second["Giá trung vị (triệu/tháng)"] - first["Giá trung vị (triệu/tháng)"]
                st.caption(f"Trung vị {right} chênh {number(difference, 2)} triệu đồng/tháng so với {left} trong nhóm đã chọn. Đây là so sánh mô tả trên mẫu tin đăng, không phản ánh toàn bộ thị trường.")
            st.download_button("Tải kết quả so sánh (CSV)", comparison_stats.to_csv(index=False).encode("utf-8-sig"),
                               file_name="so_sanh_hai_khu_vuc.csv", mime="text/csv", key="download_comparison")

with tab_quality:
    st.subheader("Kết quả ETL và chất lượng dữ liệu")
    with connect() as connection:
        etl_summary = connection.execute(
            "SELECT source_name AS nguồn, raw_rows AS đầu_vào, clean_rows AS sau_làm_sạch, "
            "loaded_rows AS vào_dashboard, excluded_rows AS loại_khỏi_phạm_vi "
            "FROM rentals.v_etl_summary WHERE run_id=%s ORDER BY source_name", (version[0],)
        ).fetchall()
    st.dataframe(pd.DataFrame(etl_summary), hide_index=True, width="stretch")
    st.caption("Các phép kiểm tra dựa trên dữ liệu trong tập hiện tại. Tin nghi trùng chỉ được đánh dấu, không tự động loại.")
    miss = completeness(data)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tổng tin", count(len(data)))
    c2.metric("Thiếu giá", count(data[PRICE].isna().sum()))
    c3.metric("Thiếu diện tích", count(data[AREA].isna().sum()))
    c4.metric("Chưa xác định phường/xã", count(data[WARD].isna().sum()))
    left_col, right_col = st.columns(2)
    with left_col:
        st.markdown("**Độ đầy đủ dữ liệu**")
        st.dataframe(miss, hide_index=True, width="stretch")
    with right_col:
        st.markdown("**Cơ cấu nguồn và loại nhà**")
        comp = source_composition(data)
        st.dataframe(comp, width="stretch")
    mix = source_composition(data).reset_index().melt(id_vars=SOURCE, var_name=KIND, value_name="Số tin")
    fig = px.bar(mix, x=SOURCE, y="Số tin", color=KIND, barmode="group", color_discrete_map=COLORS)
    fig.update_layout(height=390)
    show_chart(fig, "quality_source_mix")
    suspects = duplicate_candidates(data)
    st.markdown(f"**Các tin nghi trùng: {count(len(suspects))} tin thuộc {count(suspects['Nhóm nghi trùng'].nunique())} nhóm**")
    st.caption("Tiêu chí: tiêu đề sau chuẩn hóa, khu vực, giá và diện tích giống nhau. Có thể là các phòng khác nhau trong cùng một nhà; cần kiểm tra thủ công trước khi loại.")
    if suspects.empty:
        st.info("Không phát hiện nhóm nghi trùng theo quy tắc đang sử dụng.")
    else:
        st.dataframe(suspects, hide_index=True, width="stretch", column_config={
            URL: st.column_config.LinkColumn("Tin gốc", display_text="Xem tin"),
        })
        st.download_button("Tải danh sách nghi trùng (CSV)", suspects.to_csv(index=False).encode("utf-8-sig"),
                           file_name="tin_nghi_trung.csv", mime="text/csv", key="download_suspects")
    st.caption("Tỷ lệ thiếu phường/xã cao có thể làm giảm độ bao phủ của phân tích theo đơn vị hành chính hiện hành.")
