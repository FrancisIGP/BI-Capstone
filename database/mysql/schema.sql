-- MySQL 8.4 schema for GDPeso.
-- Connect to database `2026_3dsa_4_GDPeso` before running this file.
-- Additive bootstrap only: creates tables; does not select/create/drop databases,
-- grant privileges, or insert data. Requires InnoDB for foreign keys.
CREATE TABLE dim_year (
    year_key INTEGER,
    decade INTEGER,
    era LONGTEXT,
    psna_quarters_available SMALLINT,
    is_complete_psna_year BOOLEAN,
    PRIMARY KEY (year_key)
);

CREATE TABLE dim_date (
    date_key INTEGER,
    full_date DATE,
    year_key INTEGER,
    month_no SMALLINT,
    PRIMARY KEY (date_key),
    FOREIGN KEY (year_key) REFERENCES dim_year (year_key)
);

CREATE TABLE dim_quarter (
    quarter_key INTEGER,
    year_key INTEGER,
    quarter_no SMALLINT,
    quarter_label LONGTEXT,
    start_date_key INTEGER,
    PRIMARY KEY (quarter_key),
    FOREIGN KEY (year_key) REFERENCES dim_year (year_key),
    FOREIGN KEY (start_date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE dim_price_basis (
    price_basis_key INTEGER,
    price_basis_code LONGTEXT,
    description LONGTEXT,
    PRIMARY KEY (price_basis_key)
);

CREATE TABLE dim_measure (
    measure_key INTEGER,
    measure_code LONGTEXT,
    description LONGTEXT,
    PRIMARY KEY (measure_key)
);

CREATE TABLE dim_unit (
    unit_key INTEGER,
    unit_name LONGTEXT,
    unit_note LONGTEXT,
    PRIMARY KEY (unit_key)
);

CREATE TABLE dim_source_file (
    source_file_key INTEGER,
    file_name LONGTEXT,
    publisher LONGTEXT,
    frequency LONGTEXT,
    first_year INTEGER,
    last_year INTEGER,
    rows_clean INTEGER,
    description LONGTEXT,
    PRIMARY KEY (source_file_key)
);

CREATE TABLE dim_psna_table (
    table_key INTEGER,
    table_no LONGTEXT,
    table_title LONGTEXT,
    breakdown LONGTEXT,
    measure_key INTEGER,
    unit_key INTEGER,
    PRIMARY KEY (table_key),
    FOREIGN KEY (measure_key) REFERENCES dim_measure (measure_key),
    FOREIGN KEY (unit_key) REFERENCES dim_unit (unit_key)
);

CREATE TABLE dim_sector (
    sector_key INTEGER,
    sector_name LONGTEXT,
    PRIMARY KEY (sector_key)
);

CREATE TABLE dim_industry (
    industry_key INTEGER,
    industry_name LONGTEXT,
    industry_code LONGTEXT,
    industry_level SMALLINT,
    industry_path LONGTEXT,
    is_sector_total BOOLEAN,
    sector_key INTEGER,
    PRIMARY KEY (industry_key),
    FOREIGN KEY (sector_key) REFERENCES dim_sector (sector_key)
);

CREATE TABLE dim_expenditure_item (
    expenditure_item_key INTEGER,
    item_name LONGTEXT,
    item_code LONGTEXT,
    item_level SMALLINT,
    item_path LONGTEXT,
    parent_item_key INTEGER,
    PRIMARY KEY (expenditure_item_key),
    FOREIGN KEY (parent_item_key) REFERENCES dim_expenditure_item (expenditure_item_key)
);

CREATE TABLE dim_per_capita_indicator (
    per_capita_indicator_key INTEGER,
    indicator_name LONGTEXT,
    PRIMARY KEY (per_capita_indicator_key)
);

CREATE TABLE dim_primary_income_item (
    primary_income_item_key INTEGER,
    item_name LONGTEXT,
    item_level SMALLINT,
    item_path LONGTEXT,
    parent_item_key INTEGER,
    PRIMARY KEY (primary_income_item_key),
    FOREIGN KEY (parent_item_key) REFERENCES dim_primary_income_item (primary_income_item_key)
);

CREATE TABLE dim_household_category (
    household_category_key INTEGER,
    category_name LONGTEXT,
    display_order SMALLINT,
    is_total BOOLEAN,
    PRIMARY KEY (household_category_key)
);

CREATE TABLE dim_island_group (
    island_group_key INTEGER,
    island_group_name LONGTEXT,
    PRIMARY KEY (island_group_key)
);

CREATE TABLE dim_region (
    region_key INTEGER,
    region_name LONGTEXT,
    region_code LONGTEXT,
    is_ncr BOOLEAN,
    is_national BOOLEAN,
    island_group_key INTEGER,
    PRIMARY KEY (region_key),
    FOREIGN KEY (island_group_key) REFERENCES dim_island_group (island_group_key)
);

CREATE TABLE dim_country (
    country_key INTEGER,
    country_code LONGTEXT,
    country_name LONGTEXT,
    is_asean BOOLEAN,
    is_world BOOLEAN,
    is_philippines BOOLEAN,
    PRIMARY KEY (country_key)
);

CREATE TABLE dim_wb_indicator (
    wb_indicator_key INTEGER,
    indicator_code LONGTEXT,
    indicator_name LONGTEXT,
    unit_key INTEGER,
    PRIMARY KEY (wb_indicator_key),
    FOREIGN KEY (unit_key) REFERENCES dim_unit (unit_key)
);

CREATE TABLE fact_gdp_quarterly (
    quarter_key INTEGER,
    gdp_current DECIMAL(24,6),
    gdp_constant DECIMAL(24,6),
    gdp_ipi_published DECIMAL(24,6),
    gdp_ipi_computed DECIMAL(24,6),
    gdp_nominal_growth_pct DECIMAL(24,6),
    gdp_real_growth_pct DECIMAL(24,6),
    gni_current DECIMAL(24,6),
    gni_constant DECIMAL(24,6),
    gni_real_growth_pct DECIMAL(24,6),
    net_primary_income_current DECIMAL(24,6),
    net_primary_income_constant DECIMAL(24,6),
    source_file_key INTEGER,
    PRIMARY KEY (quarter_key),
    FOREIGN KEY (quarter_key) REFERENCES dim_quarter (quarter_key),
    FOREIGN KEY (source_file_key) REFERENCES dim_source_file (source_file_key)
);

CREATE TABLE fact_expenditure_quarterly (
    quarter_key INTEGER,
    expenditure_item_key INTEGER,
    table_key INTEGER,
    price_basis_key INTEGER,
    value DECIMAL(24,6),
    source_file_key INTEGER,
    PRIMARY KEY (quarter_key, expenditure_item_key, table_key, price_basis_key),
    FOREIGN KEY (quarter_key) REFERENCES dim_quarter (quarter_key),
    FOREIGN KEY (expenditure_item_key) REFERENCES dim_expenditure_item (expenditure_item_key),
    FOREIGN KEY (table_key) REFERENCES dim_psna_table (table_key),
    FOREIGN KEY (price_basis_key) REFERENCES dim_price_basis (price_basis_key),
    FOREIGN KEY (source_file_key) REFERENCES dim_source_file (source_file_key)
);

CREATE TABLE fact_industry_gva_quarterly (
    quarter_key INTEGER,
    industry_key INTEGER,
    table_key INTEGER,
    price_basis_key INTEGER,
    value DECIMAL(24,6),
    source_file_key INTEGER,
    PRIMARY KEY (quarter_key, industry_key, table_key, price_basis_key),
    FOREIGN KEY (quarter_key) REFERENCES dim_quarter (quarter_key),
    FOREIGN KEY (industry_key) REFERENCES dim_industry (industry_key),
    FOREIGN KEY (table_key) REFERENCES dim_psna_table (table_key),
    FOREIGN KEY (price_basis_key) REFERENCES dim_price_basis (price_basis_key),
    FOREIGN KEY (source_file_key) REFERENCES dim_source_file (source_file_key)
);

CREATE TABLE fact_per_capita_quarterly (
    quarter_key INTEGER,
    per_capita_indicator_key INTEGER,
    table_key INTEGER,
    price_basis_key INTEGER,
    value DECIMAL(24,6),
    source_file_key INTEGER,
    PRIMARY KEY (quarter_key, per_capita_indicator_key, table_key, price_basis_key),
    FOREIGN KEY (quarter_key) REFERENCES dim_quarter (quarter_key),
    FOREIGN KEY (per_capita_indicator_key) REFERENCES dim_per_capita_indicator (per_capita_indicator_key),
    FOREIGN KEY (table_key) REFERENCES dim_psna_table (table_key),
    FOREIGN KEY (price_basis_key) REFERENCES dim_price_basis (price_basis_key),
    FOREIGN KEY (source_file_key) REFERENCES dim_source_file (source_file_key)
);

CREATE TABLE fact_primary_income_quarterly (
    quarter_key INTEGER,
    primary_income_item_key INTEGER,
    table_key INTEGER,
    price_basis_key INTEGER,
    value DECIMAL(24,6),
    source_file_key INTEGER,
    PRIMARY KEY (quarter_key, primary_income_item_key, table_key, price_basis_key),
    FOREIGN KEY (quarter_key) REFERENCES dim_quarter (quarter_key),
    FOREIGN KEY (primary_income_item_key) REFERENCES dim_primary_income_item (primary_income_item_key),
    FOREIGN KEY (table_key) REFERENCES dim_psna_table (table_key),
    FOREIGN KEY (price_basis_key) REFERENCES dim_price_basis (price_basis_key),
    FOREIGN KEY (source_file_key) REFERENCES dim_source_file (source_file_key)
);

CREATE TABLE fact_household_spending_annual (
    year_key INTEGER,
    household_category_key INTEGER,
    price_basis_key INTEGER,
    unit_key INTEGER,
    spending_value DECIMAL(24,6),
    source_file_key INTEGER,
    PRIMARY KEY (year_key, household_category_key, price_basis_key),
    FOREIGN KEY (year_key) REFERENCES dim_year (year_key),
    FOREIGN KEY (household_category_key) REFERENCES dim_household_category (household_category_key),
    FOREIGN KEY (price_basis_key) REFERENCES dim_price_basis (price_basis_key),
    FOREIGN KEY (unit_key) REFERENCES dim_unit (unit_key),
    FOREIGN KEY (source_file_key) REFERENCES dim_source_file (source_file_key)
);

CREATE TABLE fact_regional_pc_growth (
    region_key INTEGER,
    year_key INTEGER,
    price_basis_key INTEGER,
    period_label LONGTEXT,
    growth_pct DECIMAL(24,6),
    source_file_key INTEGER,
    PRIMARY KEY (region_key, year_key, price_basis_key),
    FOREIGN KEY (region_key) REFERENCES dim_region (region_key),
    FOREIGN KEY (year_key) REFERENCES dim_year (year_key),
    FOREIGN KEY (price_basis_key) REFERENCES dim_price_basis (price_basis_key),
    FOREIGN KEY (source_file_key) REFERENCES dim_source_file (source_file_key)
);

CREATE TABLE fact_worldbank_annual (
    country_key INTEGER,
    wb_indicator_key INTEGER,
    year_key INTEGER,
    value DECIMAL(24,6),
    source_file_key INTEGER,
    PRIMARY KEY (country_key, wb_indicator_key, year_key),
    FOREIGN KEY (country_key) REFERENCES dim_country (country_key),
    FOREIGN KEY (wb_indicator_key) REFERENCES dim_wb_indicator (wb_indicator_key),
    FOREIGN KEY (year_key) REFERENCES dim_year (year_key),
    FOREIGN KEY (source_file_key) REFERENCES dim_source_file (source_file_key)
);
