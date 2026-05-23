import duckdb
from pathlib import Path
from typing import List, Dict, Any, Optional

# Column mappings keyed by format name
_FORMAT_MAPS = {
    # Raw CUR export — lineItem/ProductCode style
    "cur_slash": {
        "service":    "lineItem/ProductCode",
        "account_id": "lineItem/UsageAccountId",
        "usage_date": "lineItem/UsageStartDate",
        "cost":       "lineItem/UnblendedCost",
        "region":     "product/region",
    },
    # Athena/Glue-crawled — underscore style
    "cur_athena": {
        "service":    "line_item_product_code",
        "account_id": "line_item_usage_account_id",
        "usage_date": "line_item_usage_start_date",
        "cost":       "line_item_unblended_cost",
        "region":     "product_region",
    },
}


def _detect_format(columns: List[str]) -> str:
    col_lower = {c.lower() for c in columns}
    if "lineitem/productcode" in col_lower or "lineitem/usagestartdate" in col_lower:
        return "cur_slash"
    if "line_item_product_code" in col_lower or "line_item_usage_start_date" in col_lower:
        return "cur_athena"
    # Fallback: look for any column containing "productcode"
    for c in col_lower:
        if "productcode" in c or "product_code" in c:
            return "cur_slash" if "/" in c else "cur_athena"
    return "cur_athena"


def _q(name: str) -> str:
    """Quote a column name if it contains special characters."""
    if "/" in name or " " in name or name[0].isdigit():
        return f'"{name}"'
    return name


class CUREngine:
    """DuckDB-backed query engine for AWS CUR CSV / Parquet files."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ext = Path(file_path).suffix.lower()
        self._col_map: Optional[Dict[str, str]] = None

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _read_fn(self) -> str:
        if self._ext == ".parquet":
            return f"read_parquet('{self.file_path}')"
        return f"read_csv_auto('{self.file_path}', sample_size=-1, ignore_errors=true)"

    def _ensure_col_map(self) -> None:
        if self._col_map is not None:
            return
        con = duckdb.connect()
        try:
            result = con.execute(f"SELECT * FROM {self._read_fn()} LIMIT 1")
            columns = [d[0] for d in result.description]
            fmt = _detect_format(columns)
            self._col_map = _FORMAT_MAPS[fmt]
        finally:
            con.close()

    def _c(self, key: str) -> str:
        """Return a quoted column reference for the given logical key."""
        self._ensure_col_map()
        return _q(self._col_map[key])

    def _con(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_metadata(self) -> Dict[str, Any]:
        """Return row count, period start/end, and total cost."""
        self._ensure_col_map()
        con = self._con()
        try:
            row = con.execute(f"""
                SELECT
                    COUNT(*)                                                    AS row_count,
                    MIN(CAST({self._c('usage_date')} AS TIMESTAMP))::DATE       AS period_start,
                    MAX(CAST({self._c('usage_date')} AS TIMESTAMP))::DATE       AS period_end,
                    SUM(TRY_CAST({self._c('cost')} AS DOUBLE))                  AS total_cost
                FROM {self._read_fn()}
            """).fetchone()
            return {
                "row_count":    row[0],
                "period_start": row[1],
                "period_end":   row[2],
                "total_cost":   float(row[3] or 0),
            }
        finally:
            con.close()

    def get_cost_by_service(self, year: int, month: int) -> List[Dict]:
        """Top services by spend for a given year/month."""
        self._ensure_col_map()
        con = self._con()
        try:
            rows = con.execute(f"""
                SELECT
                    {self._c('service')}                                AS service,
                    SUM(TRY_CAST({self._c('cost')} AS DOUBLE))          AS cost
                FROM {self._read_fn()}
                WHERE YEAR(CAST({self._c('usage_date')} AS TIMESTAMP))  = {year}
                  AND MONTH(CAST({self._c('usage_date')} AS TIMESTAMP)) = {month}
                  AND TRY_CAST({self._c('cost')} AS DOUBLE) > 0
                GROUP BY 1
                ORDER BY cost DESC
            """).fetchall()

            total = sum(r[1] for r in rows if r[1]) or 1
            return [
                {
                    "service":      r[0] or "Unknown",
                    "cost":         round(float(r[1] or 0), 2),
                    "pct_of_total": round(float(r[1] or 0) / total * 100, 1),
                }
                for r in rows
            ]
        finally:
            con.close()

    def get_monthly_trend(self, months: int = 3) -> Dict[str, Any]:
        """Monthly cost per service for the last N months."""
        self._ensure_col_map()
        con = self._con()
        try:
            rows = con.execute(f"""
                SELECT
                    YEAR(CAST({self._c('usage_date')} AS TIMESTAMP))::TEXT
                        || '-' ||
                    LPAD(MONTH(CAST({self._c('usage_date')} AS TIMESTAMP))::TEXT, 2, '0')
                                                                        AS month,
                    {self._c('service')}                                AS service,
                    ROUND(SUM(TRY_CAST({self._c('cost')} AS DOUBLE)), 2) AS cost
                FROM {self._read_fn()}
                WHERE CAST({self._c('usage_date')} AS TIMESTAMP) >=
                      CURRENT_DATE - INTERVAL '{months} months'
                  AND TRY_CAST({self._c('cost')} AS DOUBLE) > 0
                GROUP BY 1, 2
                ORDER BY 1, cost DESC
            """).fetchall()

            month_data: Dict[str, Dict[str, float]] = {}
            services: set = set()
            for row in rows:
                m, svc, cost = row
                svc = svc or "Unknown"
                month_data.setdefault(m, {})[svc] = float(cost or 0)
                services.add(svc)

            return {
                "months":   sorted(month_data.keys()),
                "services": sorted(services),
                "data":     month_data,
            }
        finally:
            con.close()

    def get_mom_delta(self) -> List[Dict]:
        """Month-over-month cost delta per service (two most recent months)."""
        self._ensure_col_map()
        con = self._con()
        try:
            rows = con.execute(f"""
                WITH monthly AS (
                    SELECT
                        YEAR(CAST({self._c('usage_date')} AS TIMESTAMP))::TEXT
                            || '-' ||
                        LPAD(MONTH(CAST({self._c('usage_date')} AS TIMESTAMP))::TEXT, 2, '0')
                                                                            AS month,
                        {self._c('service')}                                AS service,
                        ROUND(SUM(TRY_CAST({self._c('cost')} AS DOUBLE)), 2) AS cost
                    FROM {self._read_fn()}
                    WHERE TRY_CAST({self._c('cost')} AS DOUBLE) > 0
                    GROUP BY 1, 2
                ),
                top2 AS (
                    SELECT DISTINCT month FROM monthly ORDER BY month DESC LIMIT 2
                ),
                cur AS (SELECT * FROM monthly WHERE month = (SELECT month FROM top2 LIMIT 1)),
                prv AS (SELECT * FROM monthly WHERE month = (SELECT month FROM top2 LIMIT 1 OFFSET 1))
                SELECT
                    COALESCE(cur.service, prv.service) AS service,
                    COALESCE(prv.cost, 0)              AS last_month,
                    COALESCE(cur.cost, 0)              AS this_month
                FROM cur FULL OUTER JOIN prv ON cur.service = prv.service
                ORDER BY this_month DESC
            """).fetchall()

            result = []
            for row in rows:
                svc = row[0] or "Unknown"
                last_m = float(row[1] or 0)
                this_m = float(row[2] or 0)
                change = this_m - last_m
                pct = round(change / last_m * 100, 1) if last_m > 0 else 0.0
                result.append({
                    "service":    svc,
                    "last_month": round(last_m, 2),
                    "this_month": round(this_m, 2),
                    "change":     round(change, 2),
                    "pct_change": pct,
                })
            return result
        finally:
            con.close()

    def get_anomalies(self, threshold: float = 0.20) -> List[Dict]:
        """Services with MoM cost spike above the given threshold (default 20%)."""
        self._ensure_col_map()
        con = self._con()
        try:
            rows = con.execute(f"""
                WITH monthly AS (
                    SELECT
                        YEAR(CAST({self._c('usage_date')} AS TIMESTAMP))::TEXT
                            || '-' ||
                        LPAD(MONTH(CAST({self._c('usage_date')} AS TIMESTAMP))::TEXT, 2, '0')
                                                                            AS month,
                        {self._c('service')}                                AS service,
                        ROUND(SUM(TRY_CAST({self._c('cost')} AS DOUBLE)), 2) AS cost
                    FROM {self._read_fn()}
                    WHERE TRY_CAST({self._c('cost')} AS DOUBLE) > 0
                    GROUP BY 1, 2
                ),
                with_prev AS (
                    SELECT *,
                           LAG(cost) OVER (PARTITION BY service ORDER BY month) AS prev_cost
                    FROM monthly
                )
                SELECT
                    service,
                    month,
                    cost                              AS current_cost,
                    prev_cost,
                    (cost - prev_cost) / prev_cost    AS pct_change
                FROM with_prev
                WHERE prev_cost > 0
                  AND (cost - prev_cost) / prev_cost > {threshold}
                ORDER BY pct_change DESC
                LIMIT 20
            """).fetchall()

            return [
                {
                    "service":       row[0] or "Unknown",
                    "month":         row[1],
                    "current_cost":  round(float(row[2] or 0), 2),
                    "previous_cost": round(float(row[3] or 0), 2),
                    "pct_increase":  round(float(row[4] or 0) * 100, 1),
                }
                for row in rows
            ]
        finally:
            con.close()

    def get_summary_for_claude(self) -> Dict[str, Any]:
        """Aggregate CUR data into a compact JSON payload for Claude context."""
        self._ensure_col_map()
        con = self._con()
        try:
            rows = con.execute(f"""
                SELECT
                    YEAR(CAST({self._c('usage_date')} AS TIMESTAMP))::TEXT
                        || '-' ||
                    LPAD(MONTH(CAST({self._c('usage_date')} AS TIMESTAMP))::TEXT, 2, '0')
                                                                        AS month,
                    {self._c('service')}                                AS service,
                    ROUND(SUM(TRY_CAST({self._c('cost')} AS DOUBLE)), 2) AS cost
                FROM {self._read_fn()}
                WHERE CAST({self._c('usage_date')} AS TIMESTAMP) >=
                      CURRENT_DATE - INTERVAL '6 months'
                  AND TRY_CAST({self._c('cost')} AS DOUBLE) > 0
                GROUP BY 1, 2
                ORDER BY 1, cost DESC
            """).fetchall()

            meta_row = con.execute(f"""
                SELECT
                    COUNT(*)                                                   AS row_count,
                    MIN(CAST({self._c('usage_date')} AS TIMESTAMP))::DATE      AS period_start,
                    MAX(CAST({self._c('usage_date')} AS TIMESTAMP))::DATE      AS period_end,
                    ROUND(SUM(TRY_CAST({self._c('cost')} AS DOUBLE)), 2)       AS total_cost
                FROM {self._read_fn()}
            """).fetchone()

            monthly: Dict[str, Dict[str, float]] = {}
            for row in rows:
                m, svc, cost = row
                monthly.setdefault(m, {})[svc or "Unknown"] = float(cost or 0)

            return {
                "period_start":            str(meta_row[1]),
                "period_end":              str(meta_row[2]),
                "total_cost_usd":          float(meta_row[3] or 0),
                "monthly_cost_by_service": monthly,
            }
        finally:
            con.close()

    def get_services(self) -> List[str]:
        self._ensure_col_map()
        con = self._con()
        try:
            rows = con.execute(
                f"SELECT DISTINCT {self._c('service')} FROM {self._read_fn()} "
                f"WHERE {self._c('service')} IS NOT NULL ORDER BY 1"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        finally:
            con.close()

    def get_accounts(self) -> List[str]:
        self._ensure_col_map()
        con = self._con()
        try:
            rows = con.execute(
                f"SELECT DISTINCT {self._c('account_id')} FROM {self._read_fn()} "
                f"WHERE {self._c('account_id')} IS NOT NULL ORDER BY 1"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        finally:
            con.close()

    def get_regions(self) -> List[str]:
        self._ensure_col_map()
        con = self._con()
        try:
            rows = con.execute(
                f"SELECT DISTINCT {self._c('region')} FROM {self._read_fn()} "
                f"WHERE {self._c('region')} IS NOT NULL ORDER BY 1"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        finally:
            con.close()
