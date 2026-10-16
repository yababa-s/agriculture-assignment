# Three useful database queries

These queries use real rows from the bundled Basic Statistics PDFs. The checked outputs below come from the included SQLite database.

## 1. Paddy and Coconut area/production by year

```sql
SELECT commodity, metric, period, value, unit, file_name, page
FROM v_provenance
WHERE commodity IN ('Paddy', 'Coconut')
ORDER BY commodity, metric, period, file_name;
```

Expected examples:

| Crop | Measure | Period | Value | Unit | Source page |
|---|---|---|---:|---|---|
| Coconut | area_cultivated | 2024-25 | 17902 | hectare | basic statistics report 2024-25.pdf, p. 1 |
| Coconut | production | 2024-25 | 112.1167 | million nuts | basic statistics report 2024-25.pdf, p. 1 |
| Paddy | area_cultivated | 2024-25 | 4365.2 | hectare | basic statistics report 2024-25.pdf, p. 1 |
| Paddy | production | 2024-25 | 13490.2 | MT | basic statistics report 2024-25.pdf, p. 1 |

## 2. Follow one number to its source and extractor

```sql
SELECT value_raw, value, unit, source_name, source_type, file_name,
       page, table_no, row_no, col_no, agent_id, run_id, evidence
FROM v_provenance
WHERE commodity='Paddy' AND metric='production' AND period='2024-25';
```

Expected: printed value `13490.2`, `pdf_table_agent`, the 2024–25 Basic Statistics PDF, page 1, with the exact source row and extraction run.

## 3. Check which source groups were completed or left pending

```sql
SELECT source_group, implementation_status, COUNT(*) AS files
FROM source_document
GROUP BY source_group, implementation_status
ORDER BY source_group;
```

This checks the manifest’s planned status. The actual run outcomes are in `evaluation/latest_evaluation.json`, where partial, pending and skipped counts are separated.
