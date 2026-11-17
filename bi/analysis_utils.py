import re
import unicodedata

import pandas as pd


SOURCE = "Nguồn"
TITLE = "Tiêu đề"
DISTRICT = "Quận/huyện cũ"
KIND = "Loại chỗ ở"
PRICE = "Giá thuê (đồng/tháng)"
AREA = "Diện tích (m²)"
UNIT = "Giá thuê/m² (đồng/tháng)"
WARD = "Phường/xã mới"
ID = "Mã tin"
URL = "Liên kết tin gốc"


def normalized_title(value):
    text = unicodedata.normalize("NFD", str(value).lower().replace("đ", "d"))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def duplicate_candidates(df):
    columns = [SOURCE, ID, TITLE, DISTRICT, KIND, PRICE, AREA, URL]
    result = df.loc[df[PRICE].gt(0) & df[AREA].gt(0), columns].copy()
    result["Tiêu đề chuẩn hóa"] = result[TITLE].map(normalized_title)
    keys = ["Tiêu đề chuẩn hóa", DISTRICT, PRICE, AREA]
    result = result.loc[result.duplicated(keys, keep=False)].copy()
    if result.empty:
        return result.drop(columns="Tiêu đề chuẩn hóa").assign(**{"Nhóm nghi trùng": pd.Series(dtype="int64")})
    result["Nhóm nghi trùng"] = result.groupby(keys, sort=True).ngroup() + 1
    return result.sort_values(["Nhóm nghi trùng", SOURCE, ID]).drop(columns="Tiêu đề chuẩn hóa")


def district_comparison(df, left, right, kind, area_min, area_max, sources=None):
    mask = df[DISTRICT].isin([left, right]) & df[KIND].eq(kind)
    mask &= df[AREA].ge(area_min) & df[AREA].lt(area_max)
    mask &= df[PRICE].gt(0) & df[UNIT].gt(0)
    if sources is not None:
        mask &= df[SOURCE].isin(sources)
    subset = df.loc[mask].copy()
    if subset.empty:
        return pd.DataFrame(columns=["Khu vực", "Số tin", "Giá trung vị (triệu/tháng)", "Giá/m² trung vị (nghìn/tháng)", "Giá P25", "Giá P75"]), subset
    result = subset.groupby(DISTRICT, observed=True).agg(
        **{"Số tin": (PRICE, "size"), "Giá trung vị (triệu/tháng)": (PRICE, lambda s: s.median()/1e6),
           "Giá/m² trung vị (nghìn/tháng)": (UNIT, lambda s: s.median()/1e3),
           "Giá P25": (PRICE, lambda s: s.quantile(.25)/1e6),
           "Giá P75": (PRICE, lambda s: s.quantile(.75)/1e6)}
    ).reset_index().rename(columns={DISTRICT: "Khu vực"})
    return result, subset


def source_composition(df):
    return pd.crosstab(df[SOURCE], df[KIND]).reindex(columns=["phòng trọ", "căn hộ", "nhà nguyên căn", "biệt thự"], fill_value=0)


def completeness(df):
    fields = [PRICE, AREA, UNIT, WARD]
    return pd.DataFrame({
        "Trường dữ liệu": fields,
        "Số thiếu": [int(df[c].isna().sum()) for c in fields],
        "Tỷ lệ thiếu (%)": [round(df[c].isna().mean()*100, 2) for c in fields]
    })
