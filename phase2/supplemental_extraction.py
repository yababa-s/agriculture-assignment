from __future__ import annotations
import re


def _num(text: str):
    value = (text or '').strip().replace(',', '')
    if re.fullmatch(r'[-+]?\d+(?:\.\d+)?', value):
        return float(value)
    return None


def _insert(conn, run_id, doc, page, table, row, col, metric, commodity, location, period, raw, unit, evidence):
    value = _num(raw)
    if value is None:
        return 0
    conn.execute('''INSERT OR IGNORE INTO observation
      (doc_id,run_id,agent_id,metric,commodity,location,period,value,unit,value_raw,page,table_no,row_no,col_no,evidence)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (doc['doc_id'], run_id, 'pdf_table_agent', metric, commodity, location, period,
       value, unit, raw.strip(), page, table, row, col, evidence[:2000]))
    return 1


def normalize_area_production(conn, run_id, doc, page_no, table_no, table):
    if table_no != 1 or len(table) < 4:
        return 0
    metric_index = next((i for i, row in enumerate(table[:4])
        if any(str(x or '').strip().lower() == 'area' for x in row)
        and any(str(x or '').strip().lower().startswith('prod') for x in row)), None)
    if metric_index is None or metric_index == 0:
        return 0
    header = table[metric_index - 1]
    locations = {col: str(header[col]).strip() for col in range(2, len(header), 2) if header[col]}
    if not locations:
        return 0
    period_match = re.search(r'20\d\d-\d\d', doc['file_name'])
    period = period_match.group(0) if period_match else 'unknown'
    category = ''
    added = 0
    for row_no, row in enumerate(table):
        if row_no <= metric_index or not row:
            continue
        first = str(row[0] or '').strip() if len(row) else ''
        crop = str(row[1] or '').strip() if len(row) > 1 else ''
        if first and not crop and _num(first) is None:
            category = first
            continue
        if not crop or crop.lower() == 'total':
            continue
        for col, location in locations.items():
            for metric, value_col, unit in (('area_cultivated', col, 'hectare'), ('production', col+1, 'MT')):
                if value_col < len(row) and row[value_col]:
                    raw = str(row[value_col]).strip()
                    ev = f'{category} | {crop} | {location} | {metric} | {period} | {raw}'
                    added += _insert(conn, run_id, doc, page_no, table_no, row_no, value_col, metric, crop, location, period, raw, unit, ev)
        if len(header) <= 21 and len(row) > 20 and row[20]:
            raw = str(row[20]).strip()
            ev = f'{category} | {crop} | Andaman & Nicobar Islands | yield/productivity | {period} | {raw}'
            added += _insert(conn, run_id, doc, page_no, table_no, row_no, 20, 'yield_productivity', crop,
                             'Andaman & Nicobar Islands', period, raw, 'MT/hectare', ev)
    return added


def normalize_lulc(conn, run_id, doc, page_no, table_no, table):
    if page_no != 1 or table_no != 1 or len(table) < 2:
        return 0
    period='2015-16'
    group=''
    added=0
    for row_no,row in enumerate(table):
        if not row:
            continue
        group_name=str(row[0] or '').strip() if len(row)>0 else ''
        label=str(row[1] or '').strip() if len(row)>1 else ''
        if group_name:
            group=group_name
        if not label:
            continue
        for col,location in ((2,'Andaman Islands'),(3,'Nicobar Islands')):
            if col<len(row) and row[col]:
                raw=str(row[col]).strip()
                ev=f'{group} | {label} | {location} | {period} | {raw}; provisional in source'
                added += _insert(conn,run_id,doc,page_no,table_no,row_no,col,'lulc_area',label,location,period,raw,'sq km',ev)
    return added


def _price_line(line):
    parts=line.split()
    if len(parts)<16 or not parts[0].rstrip('.').isdigit():
        return None
    tail=parts[-13:]
    if any(_num(x) is None and x.upper().replace('.','')!='NA' for x in tail):
        return None
    body=parts[1:-13]
    patterns=[('100','gms'),('Kg.',),('Kg',),('Doz.',),('Doz',),('Each.',),('Each',),('Ltr.',),('Ltr',),('Pkt.',),('Pkt',)]
    for i in range(len(body)):
        for pattern in patterns:
            candidate=body[i:i+len(pattern)]
            if tuple(x.lower().rstrip('.') for x in candidate)==tuple(x.lower().rstrip('.') for x in pattern):
                name=' '.join(body[:i]).strip()
                if name:
                    return name,' '.join(candidate),tail
    return None


def normalize_market_prices(conn, run_id, doc, page_no, text):
    year_match=re.search(r'20(23|24|25)',doc['file_name'])
    month_match=re.search(r'month of\s+([A-Za-z]+)',text,re.I)
    if not year_match or not month_match:
        return 0
    year=int('20'+year_match.group(1))
    month_names={name:i for i,name in enumerate(('','January','February','March','April','May','June','July','August','September','October','November','December')) if name}
    month=month_names.get(month_match.group(1).title())
    if not month:
        return 0
    if year==2023:
        pairs=[(2023,month),(2022,month-1 if month>1 else 12),(2022,month),(2021,month),(2020,month),(2019,month),(2011,4)]
    elif year==2024:
        pairs=[(2024,month),(2023,month-1 if month>1 else 12),(2023,month),(2022,month),(2021,month),(2020,month),(2011,4)]
    else:
        pairs=[(2025,month),(2024,month-1 if month>1 else 12),(2024,month),(2023,month),(2022,month),(2021,month),(2011,4)]
    periods=[f'{y}-{m:02d}' for y,m in pairs]
    added=0
    row_no=0
    for line in text.splitlines():
        parsed=_price_line(line)
        if not parsed:
            continue
        commodity,unit,values=parsed
        row_no+=1
        for col,(raw,period) in enumerate(zip(values[:7],periods),start=3):
            if raw.upper().replace('.','')=='NA':
                continue
            evidence=f'{commodity} | price | {period} | {raw} {unit}; source table page {page_no}'
            added += _insert(conn,run_id,doc,page_no,1,row_no,col,'market_price',commodity,
                'Andaman & Nicobar Islands',period,raw,f'price per {unit}',evidence)
    return added


def normalize_table(conn, run_id, doc, page_no, table_no, table):
    if doc['source_group']=='G1_AREA_PRODUCTION':
        return normalize_area_production(conn,run_id,doc,page_no,table_no,table)
    if doc['source_group']=='G7_LULC' and 'data' in doc['file_name'].lower():
        return normalize_lulc(conn,run_id,doc,page_no,table_no,table)
    return 0
