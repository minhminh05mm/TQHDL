import pandas as pd
from psycopg import sql
from psycopg.types.json import Jsonb


def dimension(connection, table, field, id_field, values):
    statement = sql.SQL("INSERT INTO rentals.{} ({}) VALUES (%s) ON CONFLICT DO NOTHING").format(
        sql.Identifier(table), sql.Identifier(field)
    )
    with connection.cursor() as cursor:
        cursor.executemany(statement, [(v,) for v in sorted({v for v in values if pd.notna(v)})])
        cursor.execute(sql.SQL("SELECT {},{} FROM rentals.{}").format(
            sql.Identifier(field), sql.Identifier(id_field), sql.Identifier(table)
        ))
        return {r[field]: r[id_field] for r in cursor.fetchall()}


def stage(connection, run_id, inputs):
    raw_ids = {}
    for item in inputs:
        source_id = connection.execute(
            "INSERT INTO rentals.sources(source_name,source_url) VALUES (%s,%s) "
            "ON CONFLICT(source_name) DO UPDATE SET source_url=EXCLUDED.source_url RETURNING source_id",
            (item["source"], item["url"]),
        ).fetchone()["source_id"]
        file_id = connection.execute(
            "INSERT INTO rentals.input_files(run_id,source_id,filename,sha256,row_count,metadata) "
            "VALUES(%s,%s,%s,%s,%s,%s) RETURNING file_id",
            (run_id, source_id, item["filename"], item["sha256"], len(item["rows"]), Jsonb(item["metadata"])),
        ).fetchone()["file_id"]
        with connection.cursor().copy(
            "COPY rentals.raw_listings(run_id,file_id,row_number,source_listing_id,payload) FROM STDIN"
        ) as copy:
            for number, row in enumerate(item["rows"], 1):
                copy.write_row((run_id, file_id, number, row[item["id_column"]] or None, Jsonb(row)))
        rows = connection.execute(
            "SELECT row_number,raw_id FROM rentals.raw_listings WHERE file_id=%s", (file_id,)
        ).fetchall()
        raw_ids[item["source"]] = {r["row_number"]: r["raw_id"] for r in rows}
    return raw_ids


def nullable(value, cast=None):
    if pd.isna(value):
        return None
    return cast(value) if cast else value


def load(connection, run_id, combined, decisions, raw_ids):
    source_ids = {r["source_name"]: r["source_id"] for r in connection.execute("SELECT * FROM rentals.sources")}
    districts = dimension(connection, "districts", "old_district_name", "district_id", combined["Quận/huyện cũ"])
    wards = dimension(connection, "wards", "current_ward_name", "ward_id", combined["Phường/xã mới"])
    housing = dimension(connection, "housing_types", "housing_type_name", "housing_type_id", combined["Loại chỗ ở"])
    accepted = {(d["source"], d["id"]): raw_ids[d["source"]][d["row_number"]]
                for d in decisions if d["decision"] == "loaded"}
    values = []
    for position, row in enumerate(combined.to_dict("records"), 1):
        source, identifier = row["Nguồn"], str(row["Mã tin"])
        values.append((
            run_id, accepted[(source,identifier)], position, source_ids[source], identifier,
            row["Liên kết tin gốc"], row["Tiêu đề"], districts[row["Quận/huyện cũ"]],
            nullable(row["Phường/xã được nêu"]), wards.get(row["Phường/xã mới"]),
            row["Trạng thái xác định phường/xã"], housing[row["Loại chỗ ở"]], row["Mục đích thuê"],
            nullable(row["Diện tích (m²)"],float), row["Trạng thái giá"], row["Trạng thái diện tích"],
            nullable(row["Giá thuê (đồng/tháng)"],int), nullable(row["Giá thuê/m² (đồng/tháng)"],int),
        ))
    with connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO rentals.rental_listings(run_id,raw_id,import_position,source_id,source_listing_id,"
            "source_url,title,district_id,mentioned_ward,ward_id,ward_resolution_status,housing_type_id,"
            "rental_purpose,area_m2,price_status,area_status,monthly_price_vnd,unit_price_vnd_m2) "
            "VALUES(" + ",".join(["%s"]*18) + ")", values,
        )
    listing_ids = {r["raw_id"]:r["listing_id"] for r in connection.execute(
        "SELECT raw_id,listing_id FROM rentals.rental_listings WHERE run_id=%s", (run_id,)
    )}
    with connection.cursor().copy(
        "COPY rentals.etl_row_results(run_id,raw_id,decision,stage,reason_code,cleaned,quality,listing_id) FROM STDIN"
    ) as copy:
        for d in decisions:
            raw_id = raw_ids[d["source"]][d["row_number"]]
            copy.write_row((run_id,raw_id,d["decision"],d["stage"],d["reason"],d["cleaned"],
                            Jsonb(d["quality"]),listing_ids.get(raw_id)))


def validate(connection, run_id, combined):
    summaries = connection.execute("SELECT * FROM rentals.v_etl_summary WHERE run_id=%s", (run_id,)).fetchall()
    if not summaries or any(r["raw_rows"] != r["processed_rows"] or
                            r["raw_rows"] != r["loaded_rows"] + r["excluded_rows"] for r in summaries):
        raise ValueError("Số dòng raw và kết quả từng dòng không khớp.")
    rows = connection.execute(
        "SELECT * FROM rentals.v_all_listings WHERE etl_run_id=%s ORDER BY import_position", (run_id,)
    ).fetchall()
    actual = pd.DataFrame(rows).drop(columns=["etl_run_id", "import_position"])
    numeric = ["Giá thuê (đồng/tháng)","Giá thuê/m² (đồng/tháng)","Diện tích (m²)"]
    reference = combined.copy()
    actual["Mã tin"] = actual["Mã tin"].astype(str)
    reference["Mã tin"] = reference["Mã tin"].astype(str)
    for column in numeric:
        actual[column] = pd.to_numeric(actual[column], errors="coerce").astype(float)
        reference[column] = pd.to_numeric(reference[column], errors="coerce").astype(float)
    actual = actual.mask(actual.isna(),None)
    reference = reference.mask(reference.isna(),None)
    pd.testing.assert_frame_equal(actual,reference,check_dtype=False,check_exact=False,rtol=1e-10,atol=1e-6)
    return {
        "sources":summaries,
        "raw_rows":sum(r["raw_rows"] for r in summaries),
        "loaded_rows":len(combined),
        "missing_price":int(combined["Giá thuê (đồng/tháng)"].isna().sum()),
        "missing_area":int(combined["Diện tích (m²)"].isna().sum()),
        "missing_unit_price":int(combined["Giá thuê/m² (đồng/tháng)"].isna().sum()),
        "complete_price_area":int(combined[["Giá thuê (đồng/tháng)","Diện tích (m²)"]].notna().all(axis=1).sum()),
    }
