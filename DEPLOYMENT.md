# GDPeso deployment

The dashboard at `https://www.gdpeso.xyz/` serves a static React build and reads economic indicators through the same-origin `/api/economy` endpoint. The API queries the existing GDPeso MySQL warehouse through verified TLS with a read-only account.

| Item | Production setting |
| --- | --- |
| Repository | `FrancisIGP/BI-Capstone`, ID `1448663628`, branch `main` |
| AWS target | Account `173677044880`, `us-east-1`, EC2 `i-068efaae507c5294d` |
| Release directory | `/home/ubuntu/2026_3dsa_4_GDPeso` |
| Routing | Nginx `gdpeso` site, loopback verification on `127.0.0.1:18052` |
| Database | Shared UST MySQL RDS, schema `2026_3dsa_4_GDPeso` |
| Database setup | Manual schema bootstrap from `database/mysql/schema.sql` |

## Release process

Pull requests build with locked Node.js dependencies and no AWS access. Pushes to `main` and dispatches from `main` build a static archive with `deployment/package.py`. The deployment job verifies the archive and revision, uses GitHub OIDC to upload it to private S3, and starts `GDPeso-DeployProduction` on the approved host. It reports the SSM command ID and outcome in the workflow summary. Rerun all jobs to rebuild artifacts for a new attempt.

The root-owned host runner validates archive size, member names and checksums before installing any files. Nginx serves the chosen static release without a per-release restart. The runner checks the actual HTML and asset bytes, restores the previous release on verification failure, and keeps the current and prior verified releases. Host configuration changes in `deployment/host/` and `deployment/aws/` require a separate operator rollout.

The GitHub deployment role can write only the GDPeso release prefix, invoke its fixed SSM document on the target instance, and poll the result. The existing EC2 profile has a separate policy granting read access to the GDPeso prefix. GitHub transfer artifacts expire after one day and S3 release artifacts after 30 days.

## Database and recovery

The MySQL bootstrap defines the original warehouse's 26 tables and 45 foreign keys. Connect explicitly to `2026_3dsa_4_GDPeso` before running it on a fresh database. The source PostgreSQL file is kept for reference. CI/CD does not run SQL or import data. The GDPeso API service uses a dedicated account with SELECT on the four warehouse tables its query joins.

Inspect the exact GitHub run and SSM invocation on failure. The host runner keeps detailed errors in `/home/ubuntu/2026_3dsa_4_GDPeso/.deploy-errors.log`. Confirm the previous command has stopped before retrying. To roll back an application regression that passed deployment checks, revert the application change on `main` and verify the resulting run. The database is outside application rollback.

## Published indicator data

The initial import used 121 annual World Bank World Development Indicators observations for the Philippines covering 2015–2025 across 11 series. The source URLs and indicator metadata are recorded in the warehouse. The validated input is in deployment/data/wdi-ph-2015-2025.json. The operator-only importer, deployment/data/import_wdi.py, requires a private TLS MySQL option file and refuses to overwrite existing warehouse data.

The EC2 operator installs deployment/data/api.py as /usr/local/lib/gdpeso-data/api.py and the matching systemd unit. Set up its dedicated client options at /etc/gdpeso-data/mysql.cnf, readable only by root, and load through systemd credentials. Install the exact /api/economy proxy from deployment/host/gdpeso-static.conf as part of the host rollout. The API binds to loopback and refreshes its cache from MySQL after 30 seconds. The annual data import is a snapshot with no scheduled upstream ingestion. PSA regional GRDP is pending a validated source.