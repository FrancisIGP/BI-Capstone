"""Read published Philippine WDI observations from the GDPeso warehouse."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit

SCHEMA = "2026_3dsa_4_GDPeso"
INDICATORS = (
    "NY.GDP.MKTP.CD", "NY.GDP.MKTP.KD", "NY.GDP.MKTP.KD.ZG", "NY.GDP.PCAP.CD",
    "FP.CPI.TOTL.ZG", "NV.AGR.TOTL.ZS", "NV.IND.TOTL.ZS", "NV.SRV.TOTL.ZS",
    "NE.CON.PRVT.KD", "NE.CON.PRVT.CD", "NE.GDI.TOTL.ZS",
)
SQL = """
SELECT indicator.indicator_code, fact.year_key, fact.value
FROM fact_worldbank_annual AS fact
JOIN dim_country AS country USING (country_key)
JOIN dim_wb_indicator AS indicator USING (wb_indicator_key)
JOIN dim_source_file AS source USING (source_file_key)
WHERE country.country_code = 'PHL' AND source.publisher = 'World Bank'
  AND fact.year_key BETWEEN 1960 AND YEAR(CURRENT_DATE)
  AND fact.value IS NOT NULL
ORDER BY indicator.indicator_code, fact.year_key;
"""


def read_data(credentials):
    result = subprocess.run([
        "/usr/bin/mysql", f"--defaults-file={credentials}", "--no-login-paths",
        "--ssl-mode=VERIFY_IDENTITY", "--binary-mode", "--skip-reconnect",
        "--local-infile=0", "--connect-timeout=5", "--default-character-set=utf8mb4",
        "--batch", "--raw", "--skip-column-names", "--database", SCHEMA,
    ], input=SQL.encode(), capture_output=True, check=True, timeout=12)
    series = {code: [] for code in INDICATORS}
    for line in result.stdout.decode().splitlines():
        code, raw_year, raw_value = line.split("\t")
        if code not in series:
            continue
        year, value = int(raw_year), float(raw_value)
        points = series[code]
        if not math.isfinite(value) or (points and year <= points[-1]["year"]):
            raise ValueError("Invalid World Bank observation")
        points.append({"year": year, "value": value})
    return json.dumps({"series": series, "source": "World Bank World Development Indicators",
                       "country": "Philippines"}, separators=(",", ":"), allow_nan=False).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(True)

    def do_HEAD(self):
        self.respond(False)

    def respond(self, send_body):
        if urlsplit(self.path).path != "/api/economy":
            self.send_error(404)
            return
        try:
            if self.server.expires <= time.monotonic():
                self.server.data = read_data(self.server.credentials)
                self.server.expires = time.monotonic() + 30
        except (OSError, ValueError, subprocess.SubprocessError):
            self.log_error("GDPeso MySQL read failed")
            self.send_error(503, "Economic data temporarily unavailable")
            return
        data = self.server.data
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass


if __name__ == "__main__":
    with HTTPServer(("127.0.0.1", 18183), Handler) as server:
        server.credentials = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "mysql.cnf"
        server.expires = 0
        server.serve_forever()
