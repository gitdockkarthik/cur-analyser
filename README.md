# AWS CUR Analyser Portal

AI-powered AWS Cost & Usage Report analysis. Ask natural language questions about your cloud spend, explore cost trends, and detect anomalies — all from a single portal.

## Architecture

```
Frontend (Vanilla HTML/JS + Chart.js)
        ↕ HTTP
Backend (FastAPI + Python)
    ├── DuckDB  — queries CUR CSV/Parquet files directly
    ├── Claude API (claude-sonnet-4-6) — natural language cost analysis
    └── PostgreSQL — report registry, chat history, settings
```

## Quick Start (Docker Compose)

**1. Clone and configure**

```bash
git clone <repo>
cd cur-analyser
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

**2. Start services**

```bash
docker compose up --build
```

**3. Open the portal**

```
http://localhost:8000
```

**4. Load data**

- Go to **Reports** → click **Generate Sample Data** for instant test data, or upload your own CUR file.
- The first uploaded report is automatically set as active.

---

## Local Development (without Docker)

**Prerequisites:** Python 3.11+, PostgreSQL running locally.

```bash
cd backend
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/curanalyser
export ANTHROPIC_API_KEY=sk-ant-...
export UPLOADS_DIR=./uploads

# Create the database
psql -U postgres -c "CREATE DATABASE curanalyser;"
psql -U postgres -d curanalyser -f ../db/init.sql

# Start the server (serves frontend at http://localhost:8000)
uvicorn main:app --reload --port 8000
```

---

## Railway Deployment

1. **Create a Railway project** at [railway.app](https://railway.app)

2. **Add a PostgreSQL service** from the Railway dashboard.

3. **Add environment variables** in the Railway service settings:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   UPLOADS_DIR=/app/uploads
   ```

4. **Deploy via GitHub** — connect your repo, Railway detects the `Dockerfile` automatically.
   - Set the **Root Directory** to the repo root.
   - Set the **Dockerfile Path** to `backend/Dockerfile`.

5. **Run DB migrations** — Railway will run `init.sql` automatically on the Postgres service if you use the init script, or run it manually via the Railway shell.

6. **Generate the domain** — Railway provides a public URL automatically.

---

## Pages

| Page | URL | Description |
|------|-----|-------------|
| Home | `/` | Summary stats and quick links |
| AI Chatbot | `/chat.html` | Natural language cost Q&A powered by Claude |
| Dashboard | `/dashboard.html` | Charts, trends, MoM table, anomalies |
| Reports | `/reports.html` | Upload / manage CUR files |
| Settings | `/settings.html` | Configure data source |

---

## API Reference

All endpoints are under `/api/`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/reports/upload` | Upload a CUR CSV or Parquet file |
| `GET` | `/api/reports` | List all reports |
| `PUT` | `/api/reports/{id}/activate` | Set a report as active |
| `DELETE` | `/api/reports/{id}` | Delete a report |
| `POST` | `/api/reports/generate-sample` | Generate 3-month synthetic CUR |
| `POST` | `/api/chat` | Send a message to Claude |
| `GET` | `/api/chat/sessions/{id}/messages` | Fetch session history |
| `DELETE` | `/api/chat/sessions/{id}` | Clear a session |
| `GET` | `/api/dashboard/summary` | Summary KPIs |
| `GET` | `/api/dashboard/service-breakdown` | Cost by service (month) |
| `GET` | `/api/dashboard/trend` | Monthly trend (last N months) |
| `GET` | `/api/dashboard/mom-delta` | Month-over-month delta |
| `GET` | `/api/dashboard/anomalies` | Cost spike anomalies |
| `GET` | `/api/settings` | Get settings |
| `PUT` | `/api/settings` | Save settings |

---

## CUR File Format Support

The engine auto-detects:
- **File type**: CSV or Parquet
- **Column format**: Raw CUR export (`lineItem/ProductCode`) or Athena-crawled (`line_item_product_code`)
- **Granularity**: Hourly or daily (any is supported)

---

## Phased Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | File upload (CSV/Parquet) | ✅ Done |
| 1 | AI chatbot (Claude) | ✅ Done |
| 1 | Cost dashboard + charts | ✅ Done |
| 1 | MoM comparison + anomalies | ✅ Done |
| 2 | Direct S3 connectivity | 🔜 Coming Soon |
| 2 | Multi-account support | 🔜 Coming Soon |
| 3 | Org AI Platform integration | 📋 Planned |
