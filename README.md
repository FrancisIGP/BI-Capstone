# PH Growth Insights

**Unpacking Philippine GDP: A BI Approach to Measuring Real Economic Growth and Purchasing Power in the Philippines**

A React + Vite + Tailwind CSS frontend prototype for a University of Santo Tomas Business Intelligence capstone.

## Run locally

Requires Node.js 20.19+ or 22.12+ (Vite compatible versions).

```bash
npm install
npm run dev
```

Open the localhost URL printed by Vite.

## Production build

```bash
npm run build
npm run preview
```

Deploy the contents of `dist/` to any static host. Build command: `npm run build`. Output directory: `dist`.

## Sections

- Economic Overview
- GDP & Inflation
- Sectoral Growth
- Regional GRDP
- Purchasing Power
- About & Sources

## Data status — important

**All numeric chart series in this prototype are synthetic placeholders for UI demonstration.** They are not actual Philippine GDP, PSA, or World Bank measurements and must not be used to draw empirical conclusions. KPI cards explicitly say "Pending". Replace the example arrays in `src/App.jsx` with a validated data API before publication of results.

The original group SQL schema is included in `database/schema.sql` for reference. It defines PostgreSQL schema `dw` with 18 dimension tables and 8 fact tables. It does not include populated data or a database server. Do not expose database passwords or connect to PostgreSQL directly from the browser; use a backend API.

## Project data sources (planned)

- Philippine Statistics Authority — Philippine System of National Accounts, GRDP, household expenditure, inflation indicators
- World Bank — GDP and GDP per-capita indicators

## Collaborator handoff

Repository: https://github.com/FrancisIGP/BI-Capstone

Suggested site name: `ph-growth-insights` (subject to availability)

Tech: React, Vite, Tailwind CSS, Recharts. Build: `npm run build`. Publish directory: `dist`.
