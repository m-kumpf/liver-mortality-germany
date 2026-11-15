# The plateau in liver disease mortality in Germany, 2000–2024

Analysis code and derived tables for the manuscript *The plateau in liver disease mortality in Germany: contrasting trends by age, region and ICD-10 code, 2000–2024*.

The analysis compares chronic liver disease mortality in Germany with 15 European countries (WHO Mortality Database, Eurostat), examines German mortality and hospital diagnoses by age, sex, federal state and ICD-10 code (GBE-Bund, Federal Statistical Office), and compares registry trends with Global Burden of Disease 2023 estimates (IHME).

## Layout

```
00_meta/        data_log.md (retrieval dates, queries, versions), standard_populations/ (written by step 3)
01_gbd2023/     GBD 2023 exports retrieved through the IHME data connector (not included; call parameters in the data log)
02_eurostat/    Eurostat tables (step 1)
03_who_mdb/     WHO Mortality Database bulk-download files (not included, see below)
04_destatis/    GENESIS-Online population tables (step 4) and GBE-Bund tables (steps 5, 18, download_gbe_full.py)
05_exposures/   alcohol_gdr_frg_sieber1998.csv (transcribed from Sieber et al. 1998, included); Mikrozensus and HFA-DB files (step 16)
10_derived/     derived tables (included, except the tables with GBD 2023 estimates, see below) and manuscript tables (10_derived/tables/, step 14)
20_analysis/    scripts
figures/        figure files of the manuscript and appendix
```

## Requirements

Python 3.10 or later with the packages in `requirements.txt` (`pip install -r requirements.txt`). The final run used Python 3.13, pandas 2.3.3 and numpy 2.2.6. All scripts are run from the repository root, for example `python3 20_analysis/standardise_who_mdb.py`.

## Input data

- **WHO Mortality Database**: download the ICD-10 bulk files `morticd10_part1.zip` to `morticd10_part6.zip`, the supplementary file `morticd10_add.zip` and the population file `mort_pop.zip` from https://www.who.int/data/data-collection-tools/who-mortality-database into `03_who_mdb/`. The analysis used the release of February 2026.
- **GENESIS-Online** (step 4) needs a free API token: set the environment variable `GENESIS_TOKEN` or write the token to `00_meta/.genesis_token`.
- **GBD 2023**: the files in `01_gbd2023/` are not included. They have to be retrieved from IHME (GBD Results Tool or the data connector) with the parameters in `00_meta/data_log.md` and saved to `01_gbd2023/` under the file names listed there; the scripts read the wide column layout of the data connector (`rate_male`, `count_male`, `rate_age_std_combined` and so on), so that exports of the GBD Results Tool have to be reshaped. Steps 3, 8, 14, 15 and 17 read from `01_gbd2023/`. The derived tables with GBD estimates are not included either and are written by these steps: `sdr_compare.csv` (step 3; read by steps 14 and 15), `gbd_age_bands.csv`, `gbd_vs_registry_age_bands.csv` and `gbd_aetiology_age_bands.csv` with their summaries (step 8), `gbd_standard_check.csv` (step 15), `exposures_sev_germany.csv` and `exposures_paf_alcohol_cirrhosis_by_age.csv` (step 17).
- Eurostat, GBE-Bund, statistikportal.de and the WHO Europe HFA-DB are retrieved by the scripts.

## Pipeline

| Step | Script | Writes |
|---|---|---|
| 1 | `download_eurostat.py` | 02_eurostat/ |
| 2 | `extract_who_mdb.py` | who_mdb_liver_raw.csv, who_mdb_pop_raw.csv, who_mdb_coverage.csv |
| 3 | `standardise_who_mdb.py` | who_mdb_sdr.csv, sdr_compare.csv, coding_indicators.csv, 00_meta/standard_populations/ |
| 4 | `download_destatis.py` | 04_destatis/12411-0041, 12411-0042 |
| 5 | `download_gbe_bund.py` | 04_destatis/gbe_bund/ (TOP-100 cause-of-death table, 3-character ICD-10) |
| – | `download_gbe_full.py --table deaths --laender` | 04_destatis/gbe_full/deaths/ (ICD-10 blocks by five-year age group) |
| – | `download_gbe_full.py --table hospital3` | 04_destatis/gbe_full/hospital3/ (3-character hospital diagnoses with in-hospital deaths) |
| – | `download_gbe_full.py --table hospital4 --laender` | 04_destatis/gbe_full/hospital4/ (4-character hospital diagnoses) |
| 6 | `age_specific_comparison.py` | age_specific_rates.csv |
| 7 | `age_band_detail.py` | age_band_detail.csv, age_band_detail_summary.csv |
| 8 | `gbd_vs_registry_age.py` | gbd_age_bands.csv, gbd_vs_registry_age_bands.csv (+ summary), gbd_aetiology_age_bands.csv (+ summary) |
| 9 | `east_west_age_bands.py` | east_west_age_bands.csv, east_west_age_bands_summary.csv |
| 10 | `hospital_age_bands.py` | hospital_age_bands.csv, hospital_age_bands_summary.csv |
| 11 | `hospital3_bands.py` | hospital3_bands.csv, hospital3_bands_summary.csv |
| 12 | `laender_age_bands.py` | laender_age_bands.csv, laender_age_bands_summary.csv |
| 14 | `make_tables.py` | 10_derived/tables/ (table 1, tables S3, S5–S9) |
| 15 | `gbd_standard_check.py` | gbd_standard_check.csv |
| 16 | `download_exposures.py` | 05_exposures/ |
| 17 | `exposures_east_west.py` | exposures_*.csv |
| 18 | `download_gbe_geda.py` | 04_destatis/gbe_geda/ |
| 19 | `geda_east_west.py` | geda_alcohol_east_west.csv |
| 20 | `alcohol_mortality_east_west.py` | alcohol_mortality_east_west.csv, alcohol_mortality_allocation_check.csv |

`whomdb_common.py` holds the shared helpers (age harmonisation, standard populations, direct standardisation, Eurostat denominators). Derived tables are written to `10_derived/`. Figure files are in `figures/`; all are based on the derived tables.

## Figures

| File | Manuscript |
|---|---|
| fig1_europe | Figure 1 |
| fig2_age_men | Figure 2 |
| fig3_germany | Figure 3 |
| fig4_hospital | Figure 4 |
| fig2_age_women | Figure S1 |
| gbd_vs_registry_age_bands | Figure S2 |
| figS3_exposures | Figure S3 |
| figS4_geda_east_west | Figure S4 |
| figS5_alcohol_mortality_east_west | Figure S5 |

## License

The code is released under the MIT License (see `LICENSE`). Tables derived from GBD 2023 estimates (table S5 and the tables written by steps 3, 8, 15 and 17) and the GBD estimates shown in Figures S2 and S3 carry the notice "Source: Institute for Health Metrics and Evaluation. Used with permission. All rights reserved." and remain under the IHME free-of-charge non-commercial user agreement. The transcribed consumption series in `05_exposures/alcohol_gdr_frg_sieber1998.csv` is from Sieber, Héon and Willich (Soz Präventivmed 1998; 43: 90–99). Data retrieved by the scripts remain under the terms of their sources (WHO, Eurostat, Statistisches Bundesamt, Robert Koch-Institut, Statistische Ämter des Bundes und der Länder, WHO Regional Office for Europe).
