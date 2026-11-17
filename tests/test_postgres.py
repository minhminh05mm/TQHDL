import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import psycopg
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"bi"))
from db.client import connect, read_listings, version
from etl import run


class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first=run()

    def test_01_csv_and_database(self):
        actual=read_listings()
        expected=pd.read_csv(ROOT/"transform/combined.csv")
        actual["Mã tin"]=actual["Mã tin"].astype(str)
        expected["Mã tin"]=expected["Mã tin"].astype(str)
        pd.testing.assert_frame_equal(actual,expected,check_dtype=False,check_exact=False)
        self.assertEqual(actual.shape,(3027,15))

    def test_02_lineage_and_quality(self):
        with connect() as connection:
            stats=connection.execute("SELECT * FROM rentals.v_etl_summary WHERE run_id=(SELECT run_id FROM rentals.v_current_run)").fetchall()
            quality=connection.execute("SELECT * FROM rentals.v_data_quality_summary").fetchone()
        self.assertEqual(sum(r["raw_rows"] for r in stats),7791)
        self.assertEqual(sum(r["loaded_rows"] for r in stats),3027)
        self.assertEqual(sum(r["excluded_rows"] for r in stats),4764)
        self.assertTrue(all(r["raw_rows"]==r["processed_rows"] for r in stats))
        self.assertEqual(quality["missing_price"],51)
        self.assertEqual(quality["missing_area"],166)
        self.assertEqual(quality["complete_price_area"],2834)

    def test_03_idempotence(self):
        before=version()[0]
        result=run()
        self.assertTrue(result["skipped"])
        self.assertEqual(version()[0],before)

    def test_04_failed_load_keeps_previous_run(self):
        before=version()[0]
        with self.assertRaisesRegex(RuntimeError,"giả lập"):
            run(force=True,fail_after_load=True)
        self.assertEqual(version()[0],before)
        with connect() as connection:
            failed=connection.execute("SELECT * FROM rentals.etl_runs ORDER BY run_id DESC LIMIT 1").fetchone()
            rows=connection.execute("SELECT count(*) AS n FROM rentals.rental_listings WHERE run_id=%s",(failed["run_id"],)).fetchone()["n"]
        self.assertEqual(failed["status"],"failed")
        self.assertEqual(rows,0)

    def test_05_constraints(self):
        with connect() as connection:
            identifier=connection.execute("SELECT listing_id FROM rentals.rental_listings ORDER BY listing_id LIMIT 1").fetchone()["listing_id"]
            statements=[
                ("UPDATE rentals.rental_listings SET monthly_price_vnd='bad' WHERE listing_id=%s",psycopg.errors.InvalidTextRepresentation),
                ("UPDATE rentals.rental_listings SET unit_price_vnd_m2=1 WHERE listing_id=%s",psycopg.errors.CheckViolation),
                ("UPDATE rentals.rental_listings SET source_url='' WHERE listing_id=%s",psycopg.errors.CheckViolation),
                ("UPDATE rentals.rental_listings SET district_id=-1 WHERE listing_id=%s",psycopg.errors.ForeignKeyViolation),
            ]
            for statement,error in statements:
                with self.assertRaises(error),connection.transaction():
                    connection.execute(statement,(identifier,))

    def test_06_dashboard_and_refresh(self):
        app=AppTest.from_file(str(ROOT/"bi/dashboard.py"),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value,"3.027")
        self.assertEqual(app.metric[4].value,"1.309")
        self.assertEqual(len(app.get("plotly_chart")),12)
        before=version()[0]
        result=run(force=True)
        self.assertGreater(result["run_id"],before)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["data_version"][0],result["run_id"])
        app.multiselect(key="sources").set_value(["Phongtro123"]).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value,"1.859")

    def test_07_dashboard_does_not_read_csv(self):
        with patch("pandas.read_csv",side_effect=AssertionError("Dashboard không được đọc CSV")):
            app=AppTest.from_file(str(ROOT/"bi/dashboard.py"),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value,"3.027")


if __name__=="__main__":
    unittest.main(verbosity=2)
