import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db.client import ROOT, settings


RUNTIME=ROOT/".postgres"
DATA=RUNTIME/"data"
OWNER="btl_owner"


def find_bin(explicit=None):
    candidates=[explicit,os.getenv("POSTGRES_BIN")]
    found=shutil.which("pg_ctl")
    if found:
        candidates.append(str(Path(found).parent))
    if sys.platform=="win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"SYSTEM\CurrentControlSet\Services") as services:
            for index in range(winreg.QueryInfoKey(services)[0]):
                name=winreg.EnumKey(services,index)
                if name.lower().startswith("postgresql"):
                    with winreg.OpenKey(services,name) as service:
                        command=winreg.QueryValueEx(service,"ImagePath")[0]
                        match=re.search(r'"([^"]*pg_ctl\.exe)"',command,re.I)
                        if match:
                            candidates.append(str(Path(match.group(1)).parent))
        base=Path(os.getenv("ProgramFiles",r"C:\Program Files"))/"PostgreSQL"
        if base.exists():
            candidates.extend(str(p/"bin") for p in sorted(base.iterdir(),reverse=True) if p.is_dir())
    for candidate in candidates:
        if candidate:
            path=Path(candidate)
            if (path/("pg_ctl.exe" if sys.platform=="win32" else "pg_ctl")).is_file():
                return path
    raise FileNotFoundError("Không tìm thấy PostgreSQL. Khai báo POSTGRES_BIN trong .env hoặc dùng --bin đường_dẫn_bin.")


def control(binary,*args,check=True):
    exe=binary/("pg_ctl.exe" if sys.platform=="win32" else "pg_ctl")
    log=RUNTIME/"pg_ctl.log"
    with log.open("w",encoding="utf-8") as stream:
        result=subprocess.run([str(exe),"-D",str(DATA),*args],check=check,stdout=stream,stderr=subprocess.STDOUT)
    result.stdout=log.read_text(encoding="utf-8",errors="replace")
    result.stderr=""
    return result


def local_config():
    config=settings()
    if config["host"]!="127.0.0.1" or config["password"]:
        raise ValueError("Chế độ local dùng PGHOST=127.0.0.1 và PGPASSWORD rỗng. Server ngoài dùng trực tiếp etl.py.")
    if config["user"]==OWNER or not re.fullmatch(r"[a-z][a-z0-9_]{0,40}",config["user"]) or not re.fullmatch(r"[a-z][a-z0-9_]{0,40}",config["dbname"]):
        raise ValueError("User/database local phải là tên chữ thường, số, dấu gạch dưới; khác btl_owner.")
    return config


def start(binary):
    config=local_config()
    RUNTIME.mkdir(exist_ok=True)
    marker=RUNTIME/"project_cluster.json"
    if DATA.exists() and not marker.exists():
        raise ValueError("Thư mục dữ liệu chưa có dấu xác nhận của dự án; không thay đổi thư mục này.")
    if not DATA.exists():
        exe=binary/("initdb.exe" if sys.platform=="win32" else "initdb")
        result=subprocess.run([str(exe),"-D",str(DATA),"-U",OWNER,"--encoding=UTF8","--locale=C",
                               "--auth-local=trust","--auth-host=reject"],capture_output=True,text=True,
                              encoding="utf-8",errors="replace")
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        marker.write_text(json.dumps({"user":config["user"],"database":config["dbname"],"port":config["port"]}),encoding="utf-8")
        (DATA/"postgresql.conf").write_text((DATA/"postgresql.conf").read_text(encoding="utf-8")+
            f"\nlisten_addresses='127.0.0.1'\nport={config['port']}\n",encoding="utf-8")
        rules=(f"local postgres {OWNER} trust\n"
               f"local {config['dbname']} {config['user']} trust\n"
               "local all all reject\n"
               f"host postgres {OWNER} 127.0.0.1/32 trust\n"
               f"host {config['dbname']} {config['user']} 127.0.0.1/32 trust\n"
               "host all all 127.0.0.1/32 reject\n"
               "host all all ::1/128 reject\n")
        (DATA/"pg_hba.conf").write_text(rules,encoding="utf-8")
    else:
        saved=json.loads(marker.read_text(encoding="utf-8"))
        if saved!={"user":config["user"],"database":config["dbname"],"port":config["port"]}:
            raise ValueError("Cấu hình .env khác cluster local hiện có. Giữ cấu hình cũ hoặc tạo cluster riêng ở bản sao khác.")
    if control(binary,"status",check=False).returncode:
        result=control(binary,"-l",str(RUNTIME/"postgres.log"),"-w","start",check=False)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout)+"\nXem .postgres/postgres.log; kiểm tra cổng trong .env.")
    with psycopg.connect(host="127.0.0.1",port=config["port"],dbname="postgres",user=OWNER,
                         password="",autocommit=True,connect_timeout=5) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(config["user"],)).fetchone():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD NULL").format(sql.Identifier(config["user"])))
        role=connection.execute("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=%s",(config["user"],)).fetchone()
        if any(role):
            raise ValueError("Tài khoản ứng dụng local không được có quyền quản trị.")
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s",(config["dbname"],)).fetchone():
            connection.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
                sql.Identifier(config["dbname"]),sql.Identifier(config["user"])))
            connection.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(config["dbname"])))
    print(f"PostgreSQL local: 127.0.0.1:{config['port']}, database={config['dbname']}, user={config['user']}, không mật khẩu.")


def main():
    parser=argparse.ArgumentParser(description="PostgreSQL local riêng cho dự án")
    parser.add_argument("action",choices=["start","stop","status"],nargs="?",default="start")
    parser.add_argument("--bin")
    args=parser.parse_args()
    if os.getenv("POSTGRES_LOCAL","1")!="1":
        print("Dùng PostgreSQL đã cấu hình trong .env; không khởi động cluster local.")
        return
    binary=find_bin(args.bin)
    if args.action=="start":
        start(binary)
    elif DATA.exists():
        if not (RUNTIME/"project_cluster.json").is_file():
            raise ValueError("Không xác nhận được cluster thuộc dự án.")
        result=control(binary,"-w","-m","fast","stop",check=False) if args.action=="stop" else control(binary,"status",check=False)
        print(result.stdout or result.stderr)
    else:
        print("Chưa có cluster PostgreSQL local của dự án.")


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
