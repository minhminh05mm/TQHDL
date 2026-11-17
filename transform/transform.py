from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd


COMBINED_COLUMNS_VI = {
    "source": "Nguồn",
    "listing_id": "Mã tin",
    "original_url": "Liên kết tin gốc",
    "title": "Tiêu đề",
    "legacy_district": "Quận/huyện cũ",
    "ward_mentioned": "Phường/xã được nêu",
    "current_ward": "Phường/xã mới",
    "address_match_status": "Trạng thái xác định phường/xã",
    "housing_type": "Loại chỗ ở",
    "rental_purpose": "Mục đích thuê",
    "area_m2": "Diện tích (m²)",
    "price_status": "Trạng thái giá",
    "area_status": "Trạng thái diện tích",
    "price_vnd_month": "Giá thuê (đồng/tháng)",
    "price_per_m2_vnd_month": "Giá thuê/m² (đồng/tháng)",
}


WARD_NAMES = """
An Khánh|Ba Đình|Bạch Đằng|Bạch Mai|Bách Khoa|Biên Giang|Bình Minh|Bồ Đề|
Cao Dương|Cầu Diễn|Cầu Giấy|Cổ Nhuế 2|Cửa Nam|Dịch Vọng Hậu|Dịch Vọng|
Đại Kim|Đại Mỗ|Định Công|Đồng Nhân|Đồng Nhân|Đồng Phú|Đồng Tâm|Đông Mỹ|
Đông Ngạc|Đống Đa|Đống Mác|Đức Thượng|Dương Nội|Gia Lâm|Giáp Bát|
Hạ Bằng|Hạ Đình|Hà Cầu|Hà Đông|Hàng Bài|Hàng Bột|Hai Bà Trưng|Hoàng Liệt|
Hoàng Văn Thụ|Hồng Hà|Hưng Đạo|Hữu Hòa|Kim Chung|Kim Giang|Kim Mã|Kim Sơn|
Khương Đình|Khương Mai|Khương Thượng|Khương Trung|Kiến Hưng|La Khê|
Láng Hạ|Láng Thượng|Liên Ninh|Liệp Tuyết|Long Biên|Mai Dịch|Mễ Trì|
Minh Khai|Mỗ Lao|Mỹ Đình 1|Mỹ Đình 2|Ngọc Hà|Ngọc Khánh|Ngọc Lâm|
Ngọc Thụy|Ngô Thì Nhậm|Ngũ Hiệp|Nghĩa Đô|Nghĩa Tân|Nguyễn Trãi|
Nhân Chính|Nhật Tân|Ô Chợ Dừa|Phú Diễn|Phú La|Phú Lãm|Phú Lương|
Phú Thượng|Phúc Diễn|Phúc Lợi|Phúc Xá|Phương Canh|Phương Liên|
Phương Liệt|Phương Mai|Quang Trung|Quan Hoa|Quỳnh Lôi|Sơn Tây|
Tam Hiệp|Tân Hòa|Tân Mai|Tân Triều|Tả Thanh Oai|Tây Hồ|Tây Mỗ|Tây Tựu|
Thạch Bàn|Thanh Liệt|Thanh Lương|Thanh Nhàn|Thanh Trì|Thanh Xuân Bắc|
Thanh Xuân Trung|Thanh Xuân|Thịnh Liệt|Thịnh Quang|Thư Lâm|Tiến Xuân|
Trung Hòa|Trung Liệt|Trung Văn|Trương Định|Tương Mai|Từ Liêm|
Vân Canh|Vạn Phúc|Văn Chương|Văn Miếu|Văn Quán|Việt Hưng|Vĩnh Hưng|
Vĩnh Ngọc|Vĩnh Tuy|Xuân Đỉnh|Xuân La|Xuân Phương|Yên Hòa|Yên Hoà|
Yên Mỹ|Yên Nghĩa|Yên Phụ
"""


def fold(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value)).lower().replace("đ", "d")
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


LEGACY_DISTRICTS = """Ba Đình|Bắc Từ Liêm|Cầu Giấy|Đống Đa|Hà Đông|Hai Bà Trưng|
Hoàn Kiếm|Hoàng Mai|Long Biên|Nam Từ Liêm|Tây Hồ|Thanh Xuân|Ba Vì|Chương Mỹ|
Đan Phượng|Đông Anh|Gia Lâm|Hoài Đức|Mê Linh|Mỹ Đức|Phú Xuyên|Phúc Thọ|
Quốc Oai|Sóc Sơn|Thạch Thất|Thanh Oai|Thanh Trì|Thường Tín|Ứng Hòa|Sơn Tây"""
DISTRICT_LOOKUP = {fold(name.strip()): name.strip() for name in LEGACY_DISTRICTS.split("|")}


def district_name(value: object) -> str:
    text = " ".join(fold(value).split())
    text = re.sub(r",?\s*(?:tp\.?\s*)?ha noi$", "", text).strip()
    text = re.sub(r"^(?:(?:quan|huyen|thi xa)\s+|(?:q\.|h\.|tx\.?)\s*)", "", text)
    if text not in DISTRICT_LOOKUP:
        raise ValueError(f"Tên quận/huyện chưa xác định: {value}")
    return DISTRICT_LOOKUP[text]


WARD_LOOKUP = {fold(name.strip()): name.strip() for name in WARD_NAMES.split("|") if name.strip()}
WARD_LOOKUP["yen hoa"] = "Yên Hòa"
WARD_LOOKUP["dong nhan"] = "Đồng Nhân"
CURRENT_UNITS = {
    ("Phường " if item.strip().startswith("P:") else "Xã ") + item.strip()[2:]
    for item in """
P:Hoàn Kiếm|P:Cửa Nam|P:Ba Đình|P:Ngọc Hà|P:Giảng Võ|P:Hai Bà Trưng|P:Vĩnh Tuy|P:Bạch Mai|P:Đống Đa|
P:Kim Liên|P:Văn Miếu - Quốc Tử Giám|P:Láng|P:Ô Chợ Dừa|P:Hồng Hà|P:Lĩnh Nam|P:Hoàng Mai|
P:Vĩnh Hưng|P:Tương Mai|P:Định Công|P:Hoàng Liệt|P:Yên Sở|P:Thanh Xuân|P:Khương Đình|P:Phương Liệt|
P:Cầu Giấy|P:Nghĩa Đô|P:Yên Hòa|P:Tây Hồ|P:Phú Thượng|P:Tây Tựu|P:Phú Diễn|P:Xuân Đỉnh|P:Đông Ngạc|
P:Thượng Cát|P:Từ Liêm|P:Xuân Phương|P:Tây Mỗ|P:Đại Mỗ|P:Long Biên|P:Bồ Đề|P:Việt Hưng|P:Phúc Lợi|
P:Hà Đông|P:Dương Nội|P:Yên Nghĩa|P:Phú Lương|P:Kiến Hưng|P:Thanh Liệt|P:Chương Mỹ|P:Sơn Tây|
P:Tùng Thiện|X:Thanh Trì|X:Đại Thanh|X:Nam Phù|X:Ngọc Hồi|X:Thượng Phúc|X:Thường Tín|X:Chương Dương|
X:Hồng Vân|X:Phú Xuyên|X:Phượng Dực|X:Chuyên Mỹ|X:Đại Xuyên|X:Thanh Oai|X:Bình Minh|X:Tam Hưng|
X:Dân Hòa|X:Vân Đình|X:Ứng Thiên|X:Hòa Xá|X:Ứng Hòa|X:Mỹ Đức|X:Hồng Sơn|X:Phúc Sơn|X:Hương Sơn|
X:Phú Nghĩa|X:Xuân Mai|X:Trần Phú|X:Hòa Phú|X:Quảng Bị|X:Minh Châu|X:Quảng Oai|X:Vật Lại|X:Cổ Đô|
X:Bất Bạt|X:Suối Hai|X:Ba Vì|X:Yên Bài|X:Đoài Phương|X:Phúc Thọ|X:Phúc Lộc|X:Hát Môn|X:Thạch Thất|
X:Hạ Bằng|X:Tây Phương|X:Hòa Lạc|X:Yên Xuân|X:Quốc Oai|X:Hưng Đạo|X:Kiều Phú|X:Phú Cát|X:Hoài Đức|
X:Dương Hòa|X:Sơn Đồng|X:An Khánh|X:Đan Phượng|X:Ô Diên|X:Liên Minh|X:Gia Lâm|X:Thuận An|
X:Bát Tràng|X:Phù Đổng|X:Thư Lâm|X:Đông Anh|X:Phúc Thịnh|X:Thiên Lộc|X:Vĩnh Thanh|X:Mê Linh|
X:Yên Lãng|X:Tiến Thắng|X:Quang Minh|X:Sóc Sơn|X:Đa Phúc|X:Nội Bài|X:Trung Giã|X:Kim Anh
    """.split("|") if item.strip()
}


SAFE_OLD_TO_NEW = {
    ("Phường Biên Giang", "Hà Đông"): ("Phường Chương Mỹ", 49),
    ("Phường Bách Khoa", "Hai Bà Trưng"): ("Phường Bạch Mai", 8),
    ("Phường Bạch Mai", "Hai Bà Trưng"): ("Phường Bạch Mai", 8),
    ("Phường Cầu Diễn", "Nam Từ Liêm"): ("Phường Từ Liêm", 35),
    ("Phường Hàng Bài", "Hoàn Kiếm"): ("Phường Cửa Nam", 2),
    ("Phường Khương Mai", "Thanh Xuân"): ("Phường Phương Liệt", 24),
    ("Phường Khương Thượng", "Đống Đa"): ("Phường Kim Liên", 10),
    ("Phường Láng Thượng", "Đống Đa"): ("Phường Láng", 12),
    ("Phường Nghĩa Tân", "Cầu Giấy"): ("Phường Nghĩa Đô", 26),
    ("Phường Ngọc Lâm", "Long Biên"): ("Phường Bồ Đề", 40),
    ("Phường Phú Diễn", "Bắc Từ Liêm"): ("Phường Phú Diễn", 31),
    ("Phường Phú Lãm", "Hà Đông"): ("Phường Phú Lương", 46),
    ("Phường Phương Canh", "Nam Từ Liêm"): ("Phường Xuân Phương", 36),
    ("Phường Thịnh Quang", "Đống Đa"): ("Phường Đống Đa", 9),
    ("Phường Văn Chương", "Đống Đa"): ("Phường Văn Miếu - Quốc Tử Giám", 11),
    ("Phường Xuân Phương", "Nam Từ Liêm"): ("Phường Xuân Phương", 36),
    ("Phường Đồng Nhân", "Hai Bà Trưng"): ("Phường Hai Bà Trưng", 6),
    ("Xã Bình Minh", "Thanh Oai"): ("Xã Bình Minh", 65),
    ("Xã Hưng Đạo", "Quốc Oai"): ("Xã Hưng Đạo", 99),
    ("Xã Đức Thượng", "Hoài Đức"): ("Xã Hoài Đức", 102),
}

DIRECT_NEW_NAMES = {
    "Phường Ba Đình", "Phường Cầu Giấy", "Phường Hà Đông",
    "Phường Hai Bà Trưng", "Phường Hồng Hà", "Phường Đống Đa",
    "Phường Thanh Liệt", "Phường Thanh Xuân", "Phường Tây Hồ",
    "Phường Từ Liêm",
}
assert all(target in CURRENT_UNITS for target, _ in SAFE_OLD_TO_NEW.values())
assert DIRECT_NEW_NAMES <= CURRENT_UNITS
WARD_PATTERN = re.compile(
    r"\b(phuong|xa)\s+(" + "|".join(re.escape(name) for name in sorted(WARD_LOOKUP, key=len, reverse=True)) + r")\b"
)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.\-]*\d){8,10}(?!\d)")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def clean_title(value: object) -> str:
    text = " ".join(str(value).split())
    return EMAIL_PATTERN.sub("[email]", PHONE_PATTERN.sub("[số điện thoại]", text))


def mentioned_ward(*texts: object) -> tuple[str | None, str]:
    labels = set()
    for text in texts:
        for kind, name in WARD_PATTERN.findall(fold(text)):
            labels.add(("Phường" if kind == "phuong" else "Xã") + " " + WARD_LOOKUP[name])
    if len(labels) == 1:
        return labels.pop(), "đã_nêu_rõ"
    if len(labels) > 1:
        return None, "nhiều_địa_danh"
    return None, "không_nêu"


def housing_type(title: object, source: str) -> str:
    text = fold(title)
    if re.search(r"\b(phong tro|nha tro|cho thue phong|phong cho thue|pass phong|phong khep kin|o ghep|homestay|giuong tang|phong studio)\b", text):
        return "phòng trọ"
    if source == "phongtro123" and re.search(r"\b(nhieu phong|phong moi|phong full)\b", text):
        return "phòng trọ"
    if re.search(r"\b(can ho|chung cu|ccmn|tap the|studio|penthouse|duplex|chdv)\b", text):
        return "căn hộ"
    if re.search(r"\b(biet thu|villa)\b", text):
        return "biệt thự"
    if re.search(r"\b(nguyen can|nha rieng|nha pho|cho thue nha|nha cho thue|lien ke)\b", text):
        return "nhà nguyên căn"
    if source == "phongtro123":
        return "phòng trọ"
    return "chưa rõ"


def purpose(title: object, source: str) -> str:
    text = fold(title)
    if re.search(r"\bbán\b", str(title), re.IGNORECASE):
        return "loại: tin bán/chuyển nhượng"
    if re.search(r"\b(sang nhuong|ban nha|ban can ho|ban chung cu|ban biet thu|ban dat|can ban|nha ban)\b", text):
        return "loại: tin bán/chuyển nhượng"
    if re.search(r"\b\d+(?:[.,]\d+)?\s*ty\b", text):
        return "loại: tin bán/chuyển nhượng"
    if re.search(r"\b(tien do thanh toan|ho tro lai suat|gia tri lai von|dong tien dau tu)\b", text):
        return "loại: tin bán/chuyển nhượng"
    mixed = bool(re.search(r"\b(vua o vua kinh doanh|o va kinh doanh|kinh doanh va o|o ket hop kinh doanh|o hoac kinh doanh|kinh doanh ket hop o)\b", text))
    explicit_business_use = bool(re.search(r"\b(cho thue quan|lam quan|quan bia|quan com|tiem lam dep|dich vu lam dep|thuong mai va dich vu|san thuong mai)\b", text))
    commercial = explicit_business_use or bool(re.search(r"\b(mat bang|mbkd|van phong|vpkd|vp|kho|xuong|cua hang|nha hang|showroom|shophouse|shop house|spa|khach san|nha nghi|kinh doanh|kdoanh|kd|cafe|coffee|building|cho thue toa nha|cho thue san|san van phong)\b", text))
    if mixed:
        return "ở và kinh doanh"
    if commercial:
        return "loại: chỉ kinh doanh"
    if source == "phongtro123":
        return "để ở"
    if re.search(r"\b(cho thue|thue|phong|tro|can ho|chung cu|ccmn|studio|tap the|o ghep|homestay|nha|biet thu)\b", text):
        return "để ở"
    return "chưa rõ"


def price(value: object, title: object, source: str) -> tuple[float | None, str]:
    if pd.isna(value):
        return None, "thiếu_gốc"
    amount = float(value)
    if amount <= 0:
        return None, "không_dương"
    text = fold(title)
    if re.search(r"(?:/|\bmỗi\s+|\bper\s+)(?:ngày|đêm|giờ)\b", str(title).lower()):
        return None, "không_rõ_giá_tháng"
    if re.search(r"/(?:ngay|dem|gio)\b", text):
        return None, "không_rõ_giá_tháng"
    if source == "catalyst" and amount >= 1000:

        candidates = [float(x.replace(",", ".")) for x in re.findall(r"\b(\d+(?:[.,]\d+)?)\s*(?:tr|trieu)\b", text)]
        if any(abs(candidate - amount / 1000) <= 0.05 for candidate in candidates) and amount / 1000 <= 500:
            return amount / 1000, "sửa_x1000_có_giá_trong_tiêu_đề"
        return None, "lệch_thang_đo_chưa_xác_minh"
    if amount < 0.5 or amount > 500:
        return None, "ngoài_khoảng_hợp_lý"
    return amount, "hợp_lệ"


def area(value: object) -> tuple[float | None, str]:
    if pd.isna(value):
        return None, "thiếu_gốc"
    amount = float(value)
    if amount < 5 or amount > 1000:
        return None, "ngoài_khoảng_hợp_lý"
    return amount, "hợp_lệ"


def raw_money(value: object) -> float | None:
    value = str(value)
    match = re.search(r"\d+(?:[.,]\d+)*", value)
    if not match:
        return None
    number = match.group(0)
    if "triệu" in value.casefold():
        return float(number.replace(",", ".")) * 1e6
    if any(unit in value.casefold() for unit in ["nghìn", "ngàn"]):
        return float(number.replace(",", ".")) * 1e3
    if "đồng" in value.casefold() or "đ/tháng" in value.casefold():
        return float(number.replace(".", "").replace(",", ""))
    return None


def clean_phongtro(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    counts = Counter(raw_rows=len(df))

    years = df["Thời gian danh sách (title)"].astype("string").str.extract(r"\d{2}/\d{2}/(\d{4})", expand=False)
    df = df.loc[years.isin(["2025", "2026"])].copy()
    counts["label_2025_2026_rows"] = len(df)
    counts["duplicate_id_removed"] = int(df.duplicated("Mã tin").sum())
    df = df.drop_duplicates("Mã tin")
    rows = []
    for row in df.to_dict("records"):
        title, location = str(row["Tiêu đề nguồn"]), str(row["Khu vực nguồn"])
        if "ha noi" not in fold(location + " " + str(row["Thành phố JSON-LD"])):
            counts["không_xác_nhận_Hà_Nội"] += 1
            continue
        try:
            district = district_name(location)
        except ValueError:
            counts["khu_vực_chưa_chuẩn_hóa"] += 1
            continue
        use = purpose(title, "phongtro123")
        if use.startswith("loại:"):
            counts[use] += 1
            continue
        price_text = str(row["Giá nguồn"])
        if re.search(r"(?:/|mỗi\s+)(?:người|giường)\b", title + " " + price_text, re.IGNORECASE):
            counts["giá_theo_người_giường"] += 1
            continue
        amount = raw_money(price_text)
        if amount is not None and "tháng" not in price_text.casefold():
            rent, price_status = None, "không_rõ_giá_tháng"
        else:
            rent, price_status = price(amount / 1e6 if amount is not None else None, title, "phongtro123")
        schema_price = pd.to_numeric(row["Giá JSON-LD (đồng)"], errors="coerce")
        if amount is not None and pd.notna(schema_price) and abs(amount - schema_price) > 1000:
            rent, price_status = None, "giá_HTML_JSON_không_khớp"
        match = re.search(r"\d+(?:[.,]\d+)?", str(row["Diện tích nguồn"]))
        raw_area = float(match.group(0).replace(",", ".")) if match else None
        clean_area, area_status = area(raw_area)
        ward, ward_status = mentioned_ward(row["Địa chỉ nguồn"])
        rows.append({
            "Mã_Tin": row["Mã tin"], "Liên_kết_tin_gốc": row["URL"],
            "Nhãn_thời_gian_danh_sách_gốc": row["Nhãn thời gian danh sách"],
            "Thời_gian_danh_sách_gốc": row["Thời gian danh sách (title)"],
            "Thời_điểm_crawl_gốc": row["Thời điểm crawl"],
            "Ngày_tạo_JSON_LD_gốc": row["Ngày tạo JSON-LD"],
            "Ngày_cập_nhật_JSON_LD_gốc": row["Ngày cập nhật JSON-LD"],
            "Ngày_đăng_bảng_chi_tiết_gốc": row["Ngày đăng bảng chi tiết"],
            "Ngày_hết_hạn_bảng_chi_tiết_gốc": row["Ngày hết hạn bảng chi tiết"],
            "Quận_Huyện_cũ": district, "Phường_Xã_được_nêu": ward,
            "Trạng_thái_phường_xã": ward_status,
            "Giá_gốc": price_text, "Giá_gốc_triệu": amount / 1e6 if amount is not None else None,
            "Giá_JSON_LD_đồng_gốc": schema_price,
            "Giá_thuê_triệu_tháng": rent, "Trạng_thái_giá": price_status,
            "Diện_tích_gốc": row["Diện tích nguồn"], "Diện_tích_gốc_m2": raw_area,
            "Diện_tích_sạch_m2": clean_area, "Trạng_thái_diện_tích": area_status,
            "Loại_chỗ_ở": housing_type(title, "phongtro123"),
            "Mục_đích_thuê": use, "Tiêu_đề": clean_title(title),
        })
    result = pd.DataFrame(rows).sort_values("Mã_Tin").reset_index(drop=True)
    counts["clean_rows"] = len(result)
    return result, dict(counts)


def clean_catalyst(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    counts = Counter()
    df = df.loc[df["location"].str.endswith(", Hà Nội", na=False)].copy()
    counts["raw_hanoi"] = len(df)
    counts["duplicate_id_removed"] = int(df.duplicated("id").sum())
    df = df.drop_duplicates("id")
    rows = []
    for row in df.itertuples(index=False):
        title = row.title
        use = purpose(title, "catalyst")
        if use.startswith("loại:"):
            counts[use] += 1
            continue
        ward, ward_status = mentioned_ward(title)
        clean_price, price_status = price(row.price_million_vnd, title, "catalyst")
        clean_area, area_status = area(row.area_m2)
        rows.append({
            "id": row.id,
            "detail_url": row.detail_url,
            "location_quận_huyện_cũ": row.location.removesuffix(", Hà Nội"),
            "ward_mentioned": ward,
            "ward_status": ward_status,
            "timeline_hours_gốc": row.timeline_hours,
            "price_million_vnd_gốc": row.price_million_vnd,
            "rent_million_month_clean": clean_price,
            "price_status": price_status,
            "area_m2_gốc": row.area_m2,
            "area_m2_clean": clean_area,
            "area_status": area_status,
            "housing_type": housing_type(title, "catalyst"),
            "rental_purpose": use,
            "bedrooms": row.bedrooms,
            "bathrooms": row.bathrooms,
            "floors": row.floors,
            "frontage": row.frontage,
            "title": clean_title(title),
        })
    result = pd.DataFrame(rows).sort_values("id").reset_index(drop=True)
    counts["clean_rows"] = len(result)
    return result, dict(counts)


def current_ward(mentioned: object, district: str, raw_text: str = "") -> tuple[str | None, str]:

    explicit = set()
    normalized = fold(raw_text)
    for match in WARD_PATTERN.finditer(normalized):
        before = normalized[max(0, match.start() - 35):match.start()]
        label = ("Phường " if match.group(1) == "phuong" else "Xã ") + WARD_LOOKUP[match.group(2)]
        if re.search(r"\b(nay la|hien la|sau sap nhap la)\s*$", before) and label in CURRENT_UNITS:
            explicit.add(label)
    if len(explicit) == 1:
        return explicit.pop(), "tin_xác_nhận_tên_mới"
    if len(explicit) > 1:
        return None, "mơ_hồ_nhiều_tên_mới"
    if pd.isna(mentioned):
        return None, "thiếu_phường_xã"
    label = str(mentioned)
    if label in DIRECT_NEW_NAMES:
        return label, "nêu_tên_mới"
    entry = SAFE_OLD_TO_NEW.get((label, district))
    if entry:
        return entry[0], "đối_chiếu_chắc_chắn"
    return None, "mơ_hồ_tên_cũ"


def combine(root: Path, phongtro=None, catalyst=None, phongtro_raw=None) -> tuple[pd.DataFrame, dict]:
    clean_dir = root / "transform"
    phongtro = pd.read_csv(clean_dir / "phongtro123_raw_clean.csv") if phongtro is None else phongtro.copy()
    catalyst = pd.read_csv(clean_dir / "house_rental_dec29th_2025_clean.csv") if catalyst is None else catalyst.copy()
    phongtro["Quận_Huyện_cũ"] = phongtro["Quận_Huyện_cũ"].map(district_name)
    catalyst["location_quận_huyện_cũ"] = catalyst["location_quận_huyện_cũ"].map(district_name)
    phongtro_raw = pd.read_csv(root / "raw" / "phongtro123_raw.csv") if phongtro_raw is None else phongtro_raw
    phongtro_raw = phongtro_raw.drop_duplicates("Mã tin").set_index("Mã tin")
    allowed = {"phòng trọ", "căn hộ", "nhà nguyên căn", "biệt thự"}
    purpose_allowed = {"để ở", "ở và kinh doanh"}
    phongtro_keep = phongtro.loc[phongtro["Loại_chỗ_ở"].isin(allowed) & phongtro["Mục_đích_thuê"].isin(purpose_allowed)]
    catalyst_keep = catalyst.loc[catalyst["housing_type"].isin(allowed) & catalyst["rental_purpose"].isin(purpose_allowed)]
    rows = []
    for r in phongtro_keep.itertuples(index=False):
        raw = phongtro_raw.loc[r.Mã_Tin]
        ward, status = current_ward(r.Phường_Xã_được_nêu, r.Quận_Huyện_cũ, str(raw["Địa chỉ nguồn"]))
        rows.append({
            "source": "Phongtro123", "listing_id": str(r.Mã_Tin), "original_url": r.Liên_kết_tin_gốc,
            "title": r.Tiêu_đề, "legacy_district": r.Quận_Huyện_cũ,
            "ward_mentioned": r.Phường_Xã_được_nêu, "current_ward": ward,
            "address_match_status": status, "housing_type": r.Loại_chỗ_ở,
            "rental_purpose": r.Mục_đích_thuê, "price_million_month": r.Giá_thuê_triệu_tháng,
            "area_m2": r.Diện_tích_sạch_m2, "price_status": r.Trạng_thái_giá,
            "area_status": r.Trạng_thái_diện_tích,
        })
    for r in catalyst_keep.itertuples(index=False):
        ward, status = current_ward(r.ward_mentioned, r.location_quận_huyện_cũ, r.title)
        rows.append({
            "source": "Catalyst", "listing_id": str(r.id), "original_url": r.detail_url,
            "title": r.title, "legacy_district": r.location_quận_huyện_cũ,
            "ward_mentioned": r.ward_mentioned, "current_ward": ward,
            "address_match_status": status, "housing_type": r.housing_type,
            "rental_purpose": r.rental_purpose, "price_million_month": r.rent_million_month_clean,
            "area_m2": r.area_m2_clean, "price_status": r.price_status,
            "area_status": r.area_status,
        })
    result = pd.DataFrame(rows)
    result["price_vnd_month"] = (result.pop("price_million_month") * 1_000_000).round().astype("Int64")
    result["price_per_m2_vnd_month"] = (result["price_vnd_month"] / result["area_m2"]).round().astype("Int64")
    result = result.sort_values(["source", "listing_id"]).reset_index(drop=True)
    assert not result.duplicated(["source", "listing_id"]).any()
    assert result["current_ward"].dropna().isin(CURRENT_UNITS).all()
    stats = {
        "phongtro123_clean": len(phongtro), "phongtro123_combined": len(phongtro_keep),
        "catalyst_clean": len(catalyst), "catalyst_combined": len(catalyst_keep),
        "combined_rows": len(result),
        "legacy_district_count": int(result["legacy_district"].nunique()),
        "legacy_district_missing": int(result["legacy_district"].isna().sum()),
        "address_match_status": result["address_match_status"].value_counts().to_dict(),
    }
    assert set(result.columns) == set(COMBINED_COLUMNS_VI)
    return result.rename(columns=COMBINED_COLUMNS_VI), stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["clean", "combine"], required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    out_dir = args.root / "transform"
    out_dir.mkdir(exist_ok=True)
    if args.stage == "clean":
        raw_dir = args.root / "raw"
        phongtro, phongtro_counts = clean_phongtro(pd.read_csv(raw_dir / "phongtro123_raw.csv"))
        catalyst, catalyst_counts = clean_catalyst(pd.read_csv(raw_dir / "house_rental_dec29th_2025.csv"))
        phongtro.to_csv(out_dir / "phongtro123_raw_clean.csv", index=False, encoding="utf-8-sig")
        catalyst.to_csv(out_dir / "house_rental_dec29th_2025_clean.csv", index=False, encoding="utf-8-sig")
        stats = {"phongtro123": phongtro_counts, "catalyst": catalyst_counts}
    else:
        combined, stats = combine(args.root)
        combined.to_csv(out_dir / "combined.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
