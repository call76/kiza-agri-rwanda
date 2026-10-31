# NISR data in KIZA-AGRI

`data/templates/nisr_sas_SAMPLE_SYNTHETIC.csv` is a **synthetic layout sample, NOT NISR data**. Its rows have `is_official=0`
and the dashboard shows them with a "SYNTHETIC sample" tag. No NISR number was invented or copied here.

## To load real NISR figures
1. Download the table (e.g. Seasonal Agricultural Survey report) from https://www.statistics.gov.rw and keep the original file in `data/raw/`.
2. Copy the figures into a CSV with the same columns: publication, year, season, table_ref, indicator, geography, crop, unit, value, source_url, is_official.
   Set `is_official=1` **only** when the value is copied from the publication; `source_url` is then mandatory (the loader rejects official rows without it).
3. Import: `python scripts/import_nisr.py data/processed/your_file.csv` (or Admin > Operations).
4. Check Admin > Operations for the run: rows read / inserted / rejected, file SHA-256 (lineage), rejects in `pipeline_rejects`.
Do not mix different years, units or boundary definitions in one comparison.
