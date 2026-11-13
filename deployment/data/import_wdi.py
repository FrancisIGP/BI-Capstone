"""Import one reviewed, official World Bank WDI snapshot into the GDPeso warehouse."""

import argparse
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re
import subprocess


SCHEMA = "2026_3dsa_4_GDPeso"
UNITS = {
    "NY.GDP.MKTP.CD": (1, "Current US$"),
    "NY.GDP.MKTP.KD": (2, "Constant 2015 US$"),
    "NY.GDP.MKTP.KD.ZG": (3, "Annual percent"),
    "NY.GDP.PCAP.CD": (1, "Current US$"),
    "FP.CPI.TOTL.ZG": (3, "Annual percent"),
    "NV.AGR.TOTL.ZS": (4, "Percent of GDP"),
    "NV.IND.TOTL.ZS": (4, "Percent of GDP"),
    "NV.SRV.TOTL.ZS": (4, "Percent of GDP"),
    "NE.CON.PRVT.KD": (2, "Constant 2015 US$"),
    "NE.CON.PRVT.CD": (1, "Current US$"),
    "NE.GDI.TOTL.ZS": (4, "Percent of GDP"),
}
TABLES = ("dim_country", "dim_unit", "dim_year", "dim_source_file", "dim_wb_indicator", "fact_worldbank_annual")


def quoted(value):
    return "CONVERT(0x" + value.encode().hex() + " USING utf8mb4)"


def sql_script(records):
    if len(records) != len(UNITS) or {row["code"] for row in records} != set(UNITS):
        raise ValueError("Unexpected indicator coverage")
    years, units, sources, indicators, facts = set(), {}, [], [], []
    for key, record in enumerate(records, 1):
        code, url, label = (record[field] for field in ("code", "url", "label"))
        expected_url = f"https://api.worldbank.org/v2/country/PHL/indicator/{code}?format=json&date=2015:2025&source=2"
        if url != expected_url or not isinstance(label, str) or not label.strip():
            raise ValueError("Unexpected World Bank source")
        observations = record["values"]
        unit, unit_label = UNITS[code]
        units[unit] = unit_label
        valid_years = []
        for year, raw in observations.items():
            if not re.fullmatch(r"20(?:1[5-9]|2[0-5])", year):
                raise ValueError("Unexpected observation year")
            value = Decimal(raw).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            if not value.is_finite() or abs(value) >= Decimal(10) ** 18:
                raise ValueError("Observation is outside the warehouse precision")
            valid_years.append(int(year))
            facts.append(f"(608,{key},{year},{value:f},{key})")
        if len(valid_years) < 5:
            raise ValueError("Incomplete indicator series")
        years.update(valid_years)
        sources.append(f"({key},{quoted(url)},'World Bank','Annual',{min(valid_years)},{max(valid_years)},{len(valid_years)},'World Development Indicators API')")
        indicators.append(f"({key},{quoted(code)},{quoted(label)},{unit})")

    def insert(table, columns, values):
        return f"INSERT INTO {table} ({columns}) VALUES " + ",".join(values) + ";"

    statements = [
        "START TRANSACTION;",
        "INSERT INTO dim_country (country_key,country_code,country_name,is_asean,is_world,is_philippines) VALUES (608,'PHL','Philippines',TRUE,FALSE,TRUE);",
        insert("dim_unit", "unit_key,unit_name", (f"({key},{quoted(label)})" for key, label in sorted(units.items()))),
        insert("dim_year", "year_key,decade", (f"({year},{year // 10 * 10})" for year in sorted(years))),
        insert("dim_source_file", "source_file_key,file_name,publisher,frequency,first_year,last_year,rows_clean,description", sources),
        insert("dim_wb_indicator", "wb_indicator_key,indicator_code,indicator_name,unit_key", indicators),
        insert("fact_worldbank_annual", "country_key,wb_indicator_key,year_key,value,source_file_key", facts),
        "COMMIT;",
    ]
    return "\n".join(statements), len(facts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--mysql", required=True)
    parser.add_argument("--defaults-file", required=True, type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_bytes(), parse_float=Decimal)
    script, count = sql_script(snapshot)
    command = [args.mysql, f"--defaults-file={args.defaults_file.resolve(strict=True)}", "--no-login-paths",
               "--ssl-mode=VERIFY_IDENTITY", "--batch", "--raw", "--skip-column-names", "--binary-mode",
               "--local-infile=0", "--skip-reconnect", "--database", SCHEMA]

    def run(sql):
        process = subprocess.run(command, input=sql.encode(), capture_output=True, timeout=35)
        if process.returncode:
            raise RuntimeError("GDPeso import rejected by MySQL")
        return process.stdout.decode().splitlines()

    before = run("\n".join(f"SELECT COUNT(*) FROM {table};" for table in TABLES))
    if before != ["0"] * len(TABLES):
        raise RuntimeError("Existing warehouse data requires review before importing")
    run(script)
    rows = run("SELECT i.indicator_code,f.year_key,f.value FROM fact_worldbank_annual f "
               "JOIN dim_wb_indicator i USING (wb_indicator_key) WHERE f.country_key=608;")
    expected = {(record["code"], int(year)): Decimal(raw).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                for record in snapshot for year, raw in record["values"].items()}
    actual = {}
    for row in rows:
        code, year, value = row.split("\t")
        actual[code, int(year)] = Decimal(value)
    if len(rows) != count or actual != expected:
        raise RuntimeError("Imported data differs from the official snapshot")
    print(f"Verified {count} official WDI observations across {len(snapshot)} series")


if __name__ == "__main__":
    main()
