import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from psycopg.types.json import Jsonb

from db.client import ROOT, connect, create_database, current_run, initialize
from db.load import load, stage, validate
from transform.transform import clean_catalyst, clean_phongtro, combine, fold, purpose


INPUTS = [
    ("Phongtro123","phongtro123_raw.csv","Mã tin","https://phongtro123.com/tinh-thanh/ha-noi"),
    ("Catalyst","house_rental_dec29th_2025.csv","id", "https://www.kaggle.com/datasets/cresht2606/vietnam-real-estate-datasets-catalyst"),
]


def read_inputs():
    inputs = []
    for source,filename,id_column,url in INPUTS:
        data = (ROOT/"raw"/filename).read_bytes()
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        rows = list(reader)
        if not rows or not reader.fieldnames or id_column not in reader.fieldnames:
            raise ValueError(f"File raw không có dữ liệu hoặc sai cấu trúc: {filename}")
        metadata = {"columns":reader.fieldnames}
        if source == "Catalyst":
            metadata["snapshot_date"] = "2025-12-29"
        else:
            dates = sorted(r["Thời điểm crawl"] for r in rows if r.get("Thời điểm crawl"))
            metadata["collected_at_range"] = [dates[0], dates[-1]] if dates else []
        inputs.append(dict(source=source,filename=filename,id_column=id_column,url=url,rows=rows,
                           data=data,sha256=hashlib.sha256(data).hexdigest(),metadata=metadata))
    return inputs


def fingerprint(inputs):
    paths = ["etl.py","db/schema.sql","db/load.py","transform/transform.py","extract/extract.py"]
    rules = hashlib.sha256(b"".join((ROOT/p).read_bytes() for p in paths)).hexdigest()
    inputs_hash = hashlib.sha256(json.dumps([i["sha256"] for i in inputs]+[rules]).encode()).hexdigest()
    return inputs_hash, rules


def trace_rows(inputs, phongtro, catalyst, combined):
    cleaned = {
        "Phongtro123":{str(r["Mã_Tin"]):r for r in phongtro.to_dict("records")},
        "Catalyst":{str(r["id"]):r for r in catalyst.to_dict("records")},
    }
    loaded = {(r["Nguồn"],str(r["Mã tin"])):r for r in combined.to_dict("records")}
    decisions = []
    for item in inputs:
        source, seen = item["source"], set()
        for number,row in enumerate(item["rows"],1):
            identifier = row[item["id_column"]]
            d = dict(source=source,id=identifier,row_number=number,decision="excluded",
                     stage="scope",reason="",cleaned=False,quality={})
            if source=="Phongtro123":
                match = re.search(r"\d{2}/\d{2}/(\d{4})",row["Thời gian danh sách (title)"])
                if not match or match.group(1) not in {"2025","2026"}:
                    d["reason"]="outside_time_label"
            elif not row["location"].endswith(", Hà Nội"):
                d["reason"]="outside_hanoi"
            if not d["reason"]:
                if identifier in seen:
                    d.update(stage="clean",reason="duplicate_source_id")
                else:
                    seen.add(identifier)
                    clean = cleaned[source].get(identifier)
                    if clean is None:
                        title=row["Tiêu đề nguồn"] if source=="Phongtro123" else row["title"]
                        use=purpose(title,"phongtro123" if source=="Phongtro123" else "catalyst")
                        if use.startswith("loại:"):
                            reason="sale" if "bán" in use else "business_only"
                        elif source=="Phongtro123" and re.search(r"(?:/|mỗi\s+)(?:người|giường)\b",title+" "+row["Giá nguồn"],re.I):
                            reason="per_person_or_bed"
                        elif source=="Phongtro123" and "ha noi" not in fold(row["Khu vực nguồn"]+" "+row["Thành phố JSON-LD"]):
                            reason="hanoi_unconfirmed"
                        else:
                            raise ValueError(f"Chưa giải thích được dòng bị loại: {source}, dòng {number}")
                        d.update(stage="clean",reason=reason)
                    else:
                        d["cleaned"]=True
                        if source=="Phongtro123":
                            d["quality"]={"price_status":clean["Trạng_thái_giá"],"area_status":clean["Trạng_thái_diện_tích"]}
                        else:
                            d["quality"]={"price_status":clean["price_status"],"area_status":clean["area_status"]}
                        target=loaded.get((source,identifier))
                        if target:
                            d.update(decision="loaded",stage="load",reason="accepted")
                            d["quality"]["ward_status"]=target["Trạng thái xác định phường/xã"]
                        else:
                            d.update(stage="combine",reason="unresolved_housing_or_purpose")
            decisions.append(d)
    return decisions


def transform(inputs):
    frames={i["source"]:pd.read_csv(io.BytesIO(i["data"])) for i in inputs}
    phongtro,_=clean_phongtro(frames["Phongtro123"])
    catalyst,_=clean_catalyst(frames["Catalyst"])
    combined,_=combine(ROOT,phongtro,catalyst,frames["Phongtro123"])
    if combined.empty:
        raise ValueError("Không có tin phù hợp; giữ lần ETL thành công trước.")
    if combined.duplicated(["Nguồn","Mã tin"]).any():
        raise ValueError("Trùng khóa nguồn và mã tin.")
    decisions=trace_rows(inputs,phongtro,catalyst,combined)
    return phongtro,catalyst,combined,decisions


def export_csv(phongtro,catalyst,combined):
    for filename,data in [("phongtro123_raw_clean.csv",phongtro),
                          ("house_rental_dec29th_2025_clean.csv",catalyst),("combined.csv",combined)]:
        path=ROOT/"transform"/filename
        temporary=path.with_suffix(".tmp")
        data.to_csv(temporary,index=False,encoding="utf-8-sig")
        temporary.replace(path)


def run(force=False, fail_after_load=False):
    inputs=read_inputs()
    input_hash,rules=fingerprint(inputs)
    with connect(autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(62301855)")
        try:
            initialize(connection)
            previous=current_run(connection)
            if previous and previous["input_fingerprint"]==input_hash and not force:
                phongtro,catalyst,combined,_=transform(inputs)
                export_csv(phongtro,catalyst,combined)
                print(f"Dữ liệu và quy tắc không đổi. Dùng lại ETL #{previous['run_id']}.")
                return {"run_id":previous["run_id"],"skipped":True}
            run_id=connection.execute(
                "INSERT INTO rentals.etl_runs(input_fingerprint,rules_version) VALUES(%s,%s) RETURNING run_id",
                (input_hash,rules),
            ).fetchone()["run_id"]
            try:
                with connection.transaction():
                    raw_ids=stage(connection,run_id,inputs)
                phongtro,catalyst,combined,decisions=transform(inputs)
                with connection.transaction():
                    load(connection,run_id,combined,decisions,raw_ids)
                    summary=validate(connection,run_id,combined)
                    if fail_after_load:
                        raise RuntimeError("Lỗi giả lập để kiểm tra rollback")
                    connection.execute(
                        "UPDATE rentals.etl_runs SET status='success',finished_at=clock_timestamp(),summary=%s WHERE run_id=%s",
                        (Jsonb(summary),run_id),
                    )
            except BaseException as error:
                connection.execute(
                    "UPDATE rentals.etl_runs SET status='failed',finished_at=clock_timestamp(),error_message=%s WHERE run_id=%s",
                    (f"{type(error).__name__}: {error}"[:2000],run_id),
                )
                raise
        finally:
            connection.execute("SELECT pg_advisory_unlock(62301855)")
    export_csv(phongtro,catalyst,combined)
    print(json.dumps({"run_id":run_id,**summary},ensure_ascii=False,indent=2))
    return {"run_id":run_id,"skipped":False,**summary}


def main():
    parser=argparse.ArgumentParser(description="Extract, Transform và Load dữ liệu nhà thuê vào PostgreSQL")
    parser.add_argument("--crawl",action="store_true")
    parser.add_argument("--create-database",action="store_true")
    parser.add_argument("--force",action="store_true")
    args=parser.parse_args()
    command=[sys.executable,str(ROOT/"extract/extract.py")]
    if args.crawl:
        command.append("--crawl")
    subprocess.run(command,check=True,env=os.environ | {"PYTHONIOENCODING":"utf-8"})
    if args.create_database:
        create_database()
    run(force=args.force)


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
