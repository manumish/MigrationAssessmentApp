# MigrationAssessmentApp

**Cloud Migration Assessment Dashboard** — An interactive dashboard for planning and tracking VMware-to-OCI cloud migrations, powered by an agentic AI chat backed by Grok 4 on OCI GenAI.

![Dashboard](docs/screenshot.png)

## Overview

This application helps organizations plan and execute their migration from on-premises VMware infrastructure to Oracle Cloud Infrastructure (OCI). It provides:

- **Interactive Dashboard** — Real-time visualization of migration status, cost projections, and infrastructure inventory
- **AI-Powered Chat** — Natural language interface powered by Grok 4 (via OCI GenAI) that queries your live database
- **Cost Analysis** — TCO comparison between on-prem, OCI-Native, and OCVS migration targets
- **What-If Scenarios** — Instantly recalculate costs by changing migration targets
- **Admin Overrides** — Per-app migration target and wave adjustments with full audit trail

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 Frontend (React)                 │
│           Single HTML + React.createElement      │
│         Served by Nginx on port 80               │
├────────────┬────────────────────────────────────┤
│ /data/*.json │        /chat (POST)              │
│ Static JSON  │        Nginx proxy → :5050       │
├────────────┴────────────────────────────────────┤
│              Chat API (FastAPI)                   │
│          Python + OCI SDK + oracledb             │
│              Port 5050 (systemd)                 │
├─────────────────────────────────────────────────┤
│    OCI GenAI (Grok 4)  │  Oracle ADB (Wallet)   │
│    us-chicago-1         │  RVTOOLS_VINFO         │
│    xai.grok-4           │  APP_MIGRATION_PLAN    │
│                         │  APP_INVENTORY          │
└─────────────────────────────────────────────────┘
```

## Features

### Dashboard Tabs
1. **Overview** — KPIs, migration target pie chart, category breakdown, wave cards, license exposure, OS distribution
2. **Migration Plan** — Phase details, decision framework, what-if scenario builder
3. **Cost Analysis** — TCO timeline, savings by target (OCI-Native vs OCVS), top 15 savings opportunities
4. **Applications** — Searchable app table with drill-down drawers
5. **Infrastructure** — VM inventory, cluster breakdown, OS distribution, datacenter view

### Agentic Chat (Grok 4)
- Natural language questions about your migration data
- Generates Oracle SQL on the fly and queries ADB live
- Contextual answers with inline data tables
- Example queries:
  - *"Which apps save the most if moved to OCI?"*
  - *"Show me all Windows 2008 VMs"*
  - *"What apps are staying on-prem and why?"*
  - *"How many VMs are in the DEV cluster?"*

## Prerequisites

- **OCI Account** with:
  - Generative AI service enabled (Grok 4 model access)
  - Autonomous Database (ADB) provisioned
  - OCI CLI configured (`~/.oci/config`)
- **VM or Compute Instance** (Oracle Linux / Ubuntu) with:
  - Python 3.9+
  - Nginx
  - ADB Wallet downloaded
- **RVTools Export** — VM inventory data loaded into ADB

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/manumish/MigrationAssessmentApp.git
cd MigrationAssessmentApp
cp .env.example .env
# Edit .env with your OCI and ADB credentials
```

### 2. Set Up Database

```bash
# Load the schema into your ADB
sqlcl ADMIN/yourpassword@your_adb_dsn @sql/schema.sql

# Load your RVTools data (customize extract_data.py paths)
source .env
cd backend && python3 extract_data.py
```

### 3. Install Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test
python3 chat_api.py
# → Uvicorn running on http://0.0.0.0:5050
curl http://localhost:5050/health
```

### 4. Deploy Frontend

```bash
# Copy frontend to nginx root
sudo cp frontend/index.html /var/www/html/index.html

# Copy nginx config
sudo cp nginx/migration.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
```

### 5. Extract Data from ADB

```bash
cd backend
python3 extract_data.py
# Creates JSON files in /var/www/html/data/
```

### 6. Set Up as Service

```bash
sudo cp systemd/migration-chat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable migration-chat
sudo systemctl start migration-chat
```

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Description | Example |
|----------|-------------|---------|
| `OCI_COMPARTMENT_ID` | OCI compartment OCID | `ocid1.compartment.oc1..aaa...` |
| `OCI_GENAI_ENDPOINT` | GenAI inference endpoint | `https://inference.generativeai.us-chicago-1.oci.oraclecloud.com` |
| `OCI_GENAI_MODEL` | Model ID | `xai.grok-4` |
| `ADB_USER` | ADB username | `ADMIN` |
| `ADB_PASS` | ADB password | `yourpassword` |
| `ADB_DSN` | ADB service name | `yourdb_medium` |
| `ADB_WALLET_DIR` | Path to wallet directory | `/home/opc/wallet_yourdb` |
| `ADB_WALLET_PASSWORD` | Wallet password | `yourwalletpw` |

## Database Schema

Three core tables (see `sql/schema.sql`):

- **RVTOOLS_VINFO** — VM inventory from RVTools export
- **APP_MIGRATION_PLAN** — Migration decisions per application
- **APP_INVENTORY** — Application catalog with vendor/category metadata

## Cost Model

The dashboard uses a configurable cost model based on TCO analysis:

- **On-Prem Cost**: Per-VM baseline scaled by CPU/memory intensity
- **OCI-Native**: ~39% of on-prem (configurable multiplier)
- **OCVS**: ~55% of on-prem (VMware overlay adds overhead)

Adjust the `gc()` function in `frontend/index.html` to match your TCO analysis.

## Security Notes

- Dashboard password is configurable in `frontend/index.html` (`AUTH_HASH` variable)
- Chat API uses read-only SQL (SELECT only, dangerous keywords blocked)
- ADB credentials are in environment variables, never in code
- OCI authentication via standard OCI config file

## License

MIT

## Contributing

1. Fork the repo
2. Create a feature branch
3. Submit a PR

Built with ❤️ for cloud migration teams.
