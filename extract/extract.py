import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
USER_AGENT = "Hanoi-rental-viz/1.0"
PHONGTRO_URL = "https://phongtro123.com/tinh-thanh/ha-noi"
CATALYST_URL = (
    "https://www.kaggle.com/api/v1/datasets/download/"
    "cresht2606/vietnam-real-estate-datasets-catalyst?datasetVersionNumber=1"
)


def fetch(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read()



RAW_FIELDS = [
    "Nguồn", "Mã tin", "URL", "Tiêu đề nguồn", "Giá nguồn", "Giá JSON-LD (đồng)",
    "Diện tích nguồn", "Khu vực nguồn", "Địa chỉ nguồn", "Thành phố JSON-LD",
    "Nhãn thời gian danh sách", "Thời gian danh sách (title)", "Trang danh sách",
    "Thời điểm crawl", "Ngày tạo JSON-LD", "Ngày cập nhật JSON-LD",
    "Ngày đăng bảng chi tiết", "Ngày hết hạn bảng chi tiết", "Trang chi tiết HTTP",
]


def text(node):
    return " ".join(" ".join(node.itertext()).split())


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def json_objects(tree):
    for script in tree.xpath("//script[@type='application/ld+json']"):
        try:
            obj = json.loads(script.text or "")
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            yield obj
        elif isinstance(obj, list):
            yield from (item for item in obj if isinstance(item, dict))


def listing_id(url):
    match = re.search(r"-pr(\d+)\.html", url)
    return match.group(1) if match else None


def parse_list(body, page_url, retrieved_at):
    tree = html.fromstring(body)
    structured = {listing_id(obj.get("url", "")): obj for obj in json_objects(tree)
                  if obj.get("@type") in {"Hostel", "Apartment", "House", "Accommodation"}}
    rows = []
    for card in tree.xpath("//ul[contains(@class,'post__listing')]/li"):
        links = card.xpath(".//h3/a[contains(@href,'-pr')]")
        if not links:
            continue
        link = links[0]
        url = urljoin(page_url, link.get("href"))
        identifier = listing_id(url)
        obj = structured.get(identifier, {})
        address = obj.get("address", {})
        if not isinstance(address, dict):
            address = {}
        price_nodes = card.xpath(".//span[contains(@class,'text-green')]")
        area_texts = [text(span) for span in card.xpath(".//span")
                      if re.fullmatch(r"\d+(?:[.,]\d+)?\s*m\s*[²2]", text(span))]
        locations = card.xpath(".//a[contains(@href,'/tinh-thanh/ha-noi/')]")
        times = card.xpath(".//time")
        rows.append({
            "Nguồn": "Phongtro123", "Mã tin": identifier, "URL": url,
            "Tiêu đề nguồn": text(link),
            "Giá nguồn": text(price_nodes[0]) if price_nodes else "",
            "Giá JSON-LD (đồng)": obj.get("priceRange", ""),
            "Diện tích nguồn": area_texts[0] if area_texts else "",
            "Khu vực nguồn": text(locations[0]) if locations else "",
            "Địa chỉ nguồn": address.get("streetAddress", ""),
            "Thành phố JSON-LD": address.get("addressLocality", ""),
            "Nhãn thời gian danh sách": text(times[0]) if times else "",
            "Thời gian danh sách (title)": times[0].get("title", "") if times else "",
            "Trang danh sách": page_url, "Thời điểm crawl": retrieved_at,
        })
    return rows, tree


def parse_detail(body):
    tree = html.fromstring(body)
    result = {}
    for obj in json_objects(tree):
        if obj.get("@type") == "WebPage":
            result["Ngày tạo JSON-LD"] = obj.get("datePublished", "")
            result["Ngày cập nhật JSON-LD"] = obj.get("dateModified", "")
    for row in tree.xpath("//table//tr"):
        values = row.xpath("./td|./th")
        if len(values) < 2:
            continue
        label, value = text(values[0]).strip(":"), text(values[1])
        if label == "Ngày đăng":
            result["Ngày đăng bảng chi tiết"] = value
        elif label == "Ngày hết hạn":
            result["Ngày hết hạn bảng chi tiết"] = value
    return result

def crawl_phongtro(pages, details, pause):
    rules = RobotFileParser()
    try:
        rules.parse(fetch(urljoin(PHONGTRO_URL, "/robots.txt")).decode("utf-8").splitlines())
    except HTTPError as error:
        if error.code != 404:
            raise
        rules.parse([])
    if not rules.can_fetch(USER_AGENT, PHONGTRO_URL):
        raise ValueError("Không được phép truy cập trang danh sách.")
    pause = max(1.0, pause, rules.crawl_delay(USER_AGENT) or 0)
    raw_path = RAW / "phongtro123_raw.csv"
    previous = {}
    if raw_path.exists():
        with raw_path.open(encoding="utf-8-sig", newline="") as stream:
            previous = {row["Mã tin"]: row for row in csv.DictReader(stream)}
    records = {}
    interrupted = False
    for page in range(1, pages + 1):
        url = PHONGTRO_URL + (f"?page={page}" if page > 1 else "")
        if not rules.can_fetch(USER_AGENT, url):
            interrupted = True
            break
        time.sleep(pause)
        try:
            body = fetch(url).decode("utf-8", errors="replace")
        except HTTPError as error:
            if error.code in {403, 429}:
                interrupted = True
                break
            raise
        rows, _ = parse_list(body, url, datetime.now(timezone.utc).isoformat())
        new = 0
        for row in rows:
            identifier = row["Mã tin"]
            if identifier and identifier not in records:
                row.update({key: previous.get(identifier, {}).get(key, "") for key in RAW_FIELDS[-5:]})
                records[identifier] = row
                new += 1
        print(f"Trang {page}: {len(records)} tin")
        if not rows or new == 0:
            break
    rows = list(records.values())
    if not rows:
        raise ValueError("Không thu thập được tin; giữ nguyên file dữ liệu hiện có.")
    details = min(details, len(rows))
    sample = sorted({round(i * (len(rows)-1) / max(1, details-1)) for i in range(details)})
    for index in sample:
        row = rows[index]
        if not rules.can_fetch(USER_AGENT, row["URL"]):
            continue
        time.sleep(pause)
        try:
            row.update(parse_detail(fetch(row["URL"]).decode("utf-8", errors="replace")))
            row["Trang chi tiết HTTP"] = 200
        except HTTPError as error:
            row["Trang chi tiết HTTP"] = error.code
            if error.code in {403, 429}:
                interrupted = True
                break
            if error.code != 404:
                raise
    if interrupted:
        raise RuntimeError("Đợt crawl bị gián đoạn. File dữ liệu gốc được giữ nguyên.")
    if previous and len(rows) < len(previous):
        raise RuntimeError("Số tin crawl mới ít hơn dữ liệu hiện có. Giữ nguyên file gốc để tránh mất tin.")
    temporary = raw_path.with_suffix(".tmp")
    write_csv(temporary, rows, RAW_FIELDS)
    temporary.replace(raw_path)


def download_catalyst():
    data = fetch(CATALYST_URL)
    if data.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            data = archive.read("house_rental_dec29th_2025.csv")
    expected = "07259269e300e233c06de2fb39d261b736995b38c98b443dcbae9cce9f09be9a"
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("File tải về không khớp dữ liệu Catalyst phiên bản 1.")
    (RAW / "house_rental_dec29th_2025.csv").write_bytes(data)


def inspect(path, city_column):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    hanoi = sum((row.get(city_column) or "").strip() == "Hà Nội" or
                (row.get(city_column) or "").strip().endswith(", Hà Nội") for row in rows)
    print(f"{path.name}: {len(rows)} tin, {hanoi} tin Hà Nội, {len(reader.fieldnames)} cột")
    print("SHA-256:", hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description="Thu thập dữ liệu thuê nhà ở Hà Nội.")
    parser.add_argument("--crawl", action="store_true")
    parser.add_argument("--pages", type=int, default=150)
    parser.add_argument("--details", type=int, default=100)
    parser.add_argument("--pause", type=float, default=1.0)
    args = parser.parse_args()
    if args.pages < 1 or args.details < 0:
        parser.error("Số trang phải >= 1, số trang chi tiết phải >= 0.")
    RAW.mkdir(exist_ok=True)
    if args.crawl:
        crawl_phongtro(args.pages, args.details, args.pause)
    if not (RAW / "house_rental_dec29th_2025.csv").exists():
        download_catalyst()
    if not (RAW / "phongtro123_raw.csv").exists():
        raise FileNotFoundError("Thiếu raw/phongtro123_raw.csv; tham số --crawl dùng để thu thập dữ liệu.")
    inspect(RAW / "phongtro123_raw.csv", "Khu vực nguồn")
    inspect(RAW / "house_rental_dec29th_2025.csv", "location")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
