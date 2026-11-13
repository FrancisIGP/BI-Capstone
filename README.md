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

## Production data

The deployed dashboard reads the shared GDPeso MySQL warehouse through its same-origin API. The national charts use Philippine World Bank World Development Indicators from 2015–2025. The import includes GDP, annual growth, GDP per capita, CPI inflation, sector shares, household consumption, and capital formation. The Regional GRDP section is pending a validated Philippine Statistics Authority dataset.

See [deployment notes](DEPLOYMENT.md) for the API and import. Production data comes from the warehouse, and published source updates require a separate import.

## Collaborator handoff

Repository: https://github.com/FrancisIGP/BI-Capstone

Suggested site name: `ph-growth-insights` (subject to availability)

Tech: React, Vite, Tailwind CSS, Recharts. Build: `npm run build`. Publish directory: `dist`.
