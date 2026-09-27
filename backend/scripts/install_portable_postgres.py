"""Download and configure portable PostgreSQL 15 + PostGIS for Windows."""

import os
import sys
import time
import zipfile
import subprocess
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PGSQL_DIR = BASE_DIR / "pgsql"
DATA_DIR = PGSQL_DIR / "data"
BIN_DIR = PGSQL_DIR / "bin"
DOWNLOAD_DIR = BASE_DIR / "pgsql_downloads"

PG_URL = "https://get.enterprisedb.com/postgresql/postgresql-15.8-1-windows-x64-binaries.zip"
POSTGIS_URL = "https://download.osgeo.org/postgis/windows/pg15/postgis-bundle-pg15-3.6.2x64.zip"

def download_file(url: str, dest_path: Path):
    if dest_path.exists():
        print(f"Already downloaded: {dest_path.name}")
        return
    print(f"Downloading {url} to {dest_path.name}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Download with progress report
    t0 = time.time()
    def reporthook(count, block_size, total_size):
        if count % 1000 == 0 or count * block_size >= total_size:
            downloaded = count * block_size / 1024 / 1024
            total = total_size / 1024 / 1024
            pct = count * block_size / total_size * 100 if total_size > 0 else 0
            sys.stdout.write(f"\r  -> {downloaded:.1f} / {total:.1f} MB ({pct:.1f}%)")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, dest_path, reporthook)
    print(f"\nCompleted in {time.time() - t0:.1f}s")

def extract_zip(zip_path: Path, target_dir: Path):
    print(f"Extracting {zip_path.name}...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(target_dir)
    print("Done extracting.")

def main():
    print("=== PORTABLE POSTGRESQL + POSTGIS SETUP ===")
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    pg_zip = DOWNLOAD_DIR / "postgresql-15.8-binaries.zip"
    postgis_zip = DOWNLOAD_DIR / "postgis-bundle-pg15.zip"

    # Step 1: Download
    download_file(PG_URL, pg_zip)
    download_file(POSTGIS_URL, postgis_zip)

    # Step 2: Extract PostgreSQL
    if not (BIN_DIR / "postgres.exe").exists():
        # EDB zip contains top-level 'pgsql/' directory
        extract_zip(pg_zip, BASE_DIR)
        assert (BIN_DIR / "postgres.exe").exists(), "Failed to locate postgres.exe after extraction"

    # Step 3: Extract PostGIS overlay
    # PostGIS bundle contains top-level bin/, gdal-data/, lib/, share/, etc.
    # It overlays directly into PGSQL_DIR
    print("Overlaying PostGIS into pgsql directory...")
    extract_zip(postgis_zip, PGSQL_DIR)

    # Step 4: Initialize DB cluster
    if not (DATA_DIR / "PG_VERSION").exists():
        print(f"Initializing database cluster in {DATA_DIR}...")
        initdb = BIN_DIR / "initdb.exe"
        cmd = [
            str(initdb),
            "-D", str(DATA_DIR),
            "-U", "thermalwatch",
            "-A", "trust",
            "--locale=C",
            "--encoding=UTF8",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print("initdb failed:\n", res.stderr)
            sys.exit(1)
        print("Cluster initialized successfully.")

    # Step 5: Start PostgreSQL service
    pg_ctl = BIN_DIR / "pg_ctl.exe"
    logfile = PGSQL_DIR / "logfile.log"
    print("Starting PostgreSQL on port 5432...")
    start_cmd = [str(pg_ctl), "-D", str(DATA_DIR), "-l", str(logfile), "start"]
    res = subprocess.run(start_cmd, capture_output=True, text=True)
    print("pg_ctl start:", res.stdout, res.stderr)
    time.sleep(3)

    # Step 6: Create database 'thermalwatch'
    createdb = BIN_DIR / "createdb.exe"
    cmd_createdb = [str(createdb), "-U", "thermalwatch", "-h", "localhost", "-p", "5432", "thermalwatch"]
    res_db = subprocess.run(cmd_createdb, capture_output=True, text=True)
    print("createdb:", res_db.stdout, res_db.stderr)

    # Step 7: Create PostGIS extension
    psql = BIN_DIR / "psql.exe"
    cmd_postgis = [
        str(psql), "-U", "thermalwatch", "-h", "localhost", "-p", "5432", "-d", "thermalwatch",
        "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"
    ]
    res_postgis = subprocess.run(cmd_postgis, capture_output=True, text=True)
    print("postgis extension:", res_postgis.stdout, res_postgis.stderr)

    # Step 8: Verify PostGIS Version
    cmd_ver = [
        str(psql), "-U", "thermalwatch", "-h", "localhost", "-p", "5432", "-d", "thermalwatch",
        "-c", "SELECT PostGIS_Full_Version();"
    ]
    res_ver = subprocess.run(cmd_ver, capture_output=True, text=True)
    print("PostGIS Full Version:\n", res_ver.stdout)

    print("=== PORTABLE POSTGRESQL + POSTGIS SETUP COMPLETE ===")

if __name__ == "__main__":
    main()
