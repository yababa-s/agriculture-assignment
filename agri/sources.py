"""Source registry: every publisher/portal and every corpus file, with its source group.

The source group decides which agent handles the file (see docs/source_agent_map.md).
Download URLs come from the team's Phase 1 source inventory (DOCUMENT_URLS below).
"""
from __future__ import annotations

SOURCES = {
    "SRC_DES": {
        "name": "Directorate of Economics & Statistics, A&N Administration",
        "portal_url": "https://des.andaman.gov.in",
        "source_type": "government_statistical_publication",
        "license": "No explicit licence on portal; content owned by DES A&N. Flagged: academic use only.",
    },
    "SRC_AGRI": {
        "name": "Department of Agriculture, A&N Administration",
        "portal_url": "https://agri.andaman.gov.in",
        "source_type": "government_department_publication",
        "license": "No explicit licence on portal. Flagged: academic use only.",
    },
    "SRC_NRSC": {
        "name": "National Remote Sensing Centre (NRSC), ISRO",
        "portal_url": "https://www.nrsc.gov.in",
        "source_type": "government_remote_sensing_publication",
        "license": "NRSC data policy; publications free for non-commercial/academic use with attribution.",
    },
    "SRC_BHUVAN": {
        "name": "Bhuvan, NRSC/ISRO",
        "portal_url": "https://bhuvan.nrsc.gov.in",
        "source_type": "geoportal",
        "license": "Bhuvan terms of use; free for non-commercial/academic use with attribution.",
    },
    "SRC_MOFPI": {
        "name": "Ministry of Food Processing Industries, Government of India",
        "portal_url": "https://www.mofpi.gov.in",
        "source_type": "government_report",
        "license": "Copyright MoFPI, all rights reserved. Academic use only; do not redistribute the file.",
    },
}

# source_group -> human description; one agent owns each group (router uses this).
SOURCE_GROUPS = {
    "G1_MATRIX_TABLES": "English crop x location matrix tables (area/production)",
    "G2_BILINGUAL_TABLES": "Bilingual Hindi(legacy Kruti Dev font)+English statistical tables",
    "G3_PRICE_TABLES": "Monthly comparative retail price tables",
    "G4_ISLAND_PROFILES": "Semi-structured island-wise statistical profiles (key-value prose)",
    "G5_NARRATIVE": "Narrative reports and budget memoranda (schemes, outlays, context)",
    "G6_IMAGE_TABLES": "Raster screenshots of tables (OCR required)",
    "G7_LULC": "Land use / land cover statistics and atlases",
    "G8_RASTER_MAPS": "Large raster maps (out of scope: no raster interpretation per brief)",
}

# Collection date of every corpus file, from the team's Phase 1 records.
COLLECTION_DATE = "2026-09-26"

# Download URLs recorded in the Phase 1 source inventory (one per file).
URL_DES_ECOSTAT = "http://andssw1.and.nic.in/ecostat/index.php"
URL_BHUVAN_LULC = ("https://bhuvan.nrsc.gov.in/ngmaps/thematic?theme1=LULC250K_2425&tlp=raster"
                   "&state=ANDAMAN+AND+NICOBAR&district=ALL#6.28/10.242/93.243")
URL_MOFPI_PROFILE = "https://www.mofpi.gov.in/sites/default/files/KnowledgeCentre/State%20Profile/Andaman_Nicobar.pdf"
DOCUMENT_URLS = {
    **{f"D{i:02d}": URL_DES_ECOSTAT for i in range(1, 14)},   # area & production, basic stats, island-wise, prices
    "D14": URL_MOFPI_PROFILE,
    "D15": URL_DES_ECOSTAT,
    "D16": URL_DES_ECOSTAT,
    **{f"D{i:02d}": URL_BHUVAN_LULC for i in range(17, 21)},  # SAT Bhuvan folder
}

# doc_id, relative path, source_id, group, period label, geography, notes
DOCUMENTS = [
    ("D01", "Area and Production/42-Zone-Wise Area and Production of Crops During 2023-24.pdf", "SRC_AGRI", "G1_MATRIX_TABLES", "2023-24", "A&N zones", "Zone-wise area (ha) and production (MT) for 8 agri zones"),
    ("D02", "Area and Production/47-Area and Production 2025-26.pdf", "SRC_AGRI", "G1_MATRIX_TABLES", "2025-26", "A&N zones + districts", "Zone and district area/production incl. fruits, plantation"),
    ("D03", "Basic Statistics/Year 2021-22.pdf", "SRC_DES", "G2_BILINGUAL_TABLES", "2021-22", "A&N districts", "Basic Statistics agriculture chapter"),
    ("D04", "Basic Statistics/Year 2022-23.pdf", "SRC_DES", "G2_BILINGUAL_TABLES", "2022-23", "A&N districts", "Basic Statistics agriculture chapter"),
    ("D05", "Basic Statistics/Year 2023-24.pdf", "SRC_DES", "G2_BILINGUAL_TABLES", "2023-24", "A&N districts", "Basic Statistics agriculture chapter"),
    ("D06", "Basic Statistics/Year 2024-25.pdf", "SRC_DES", "G2_BILINGUAL_TABLES", "2024-25", "A&N districts", "Basic Statistics agriculture chapter"),
    ("D07", "Basic Statistics/37-7. Basic Statistics Report 2023-24- Machinery Farmers.pdf", "SRC_DES", "G1_MATRIX_TABLES", "2023-24", "A&N islands/tehsils", "Farmers, depots, machinery, irrigation by island"),
    ("D08", "Island-Wise Statistics/IslandwiseStatistical2022-23.pdf", "SRC_DES", "G4_ISLAND_PROFILES", "2022-23", "A&N islands", "Island-wise statistical outline"),
    ("D09", "Island-Wise Statistics/IslandwiseStatistical2023-24.pdf", "SRC_DES", "G4_ISLAND_PROFILES", "2023-24", "A&N islands", "Island-wise statistical outline"),
    ("D10", "Island-Wise Statistics/IslandwiseStatistical2024-25.pdf", "SRC_DES", "G4_ISLAND_PROFILES", "2024-25", "A&N islands", "Island-wise statistical outline"),
    ("D11", "Market Price Analysis/Fooditems2023.pdf", "SRC_DES", "G3_PRICE_TABLES", "2023", "Port Blair market", "Monthly retail prices, 5-year comparison"),
    ("D12", "Market Price Analysis/Fooditems2024.pdf", "SRC_DES", "G3_PRICE_TABLES", "2024", "Port Blair market", "Monthly retail prices, 5-year comparison"),
    ("D13", "Market Price Analysis/Fooditems2025.pdf", "SRC_DES", "G3_PRICE_TABLES", "2025", "Port Blair market", "Monthly retail prices, 5-year comparison"),
    ("D14", "Miscellaneous/food processing for sustainable growth.pdf", "SRC_MOFPI", "G5_NARRATIVE", "2024-25", "A&N UT", "Food processing UT profile (MoFPI/EY)"),
    ("D15", "Miscellaneous/subsidies 2024-25.pdf", "SRC_AGRI", "G5_NARRATIVE", "2024-25", "A&N UT", "Explanatory memoranda: scheme outlay/expenditure"),
    ("D16", "Miscellaneous/agri census 2015-16.png", "SRC_DES", "G6_IMAGE_TABLES", "2015-16", "A&N UT", "Agri census operational holdings screenshot"),
    ("D17", "SAT Bhuvan Data/Andaman Nicobar LULC 2015-16 data.pdf", "SRC_BHUVAN", "G7_LULC", "2015-16", "UT districts", "District LULC area (sq km) for all UTs"),
    ("D18", "SAT Bhuvan Data/India LULC atlas 2024.pdf", "SRC_NRSC", "G7_LULC", "2024", "India states/UTs", "Annual LULC atlas; mostly charts/maps"),
    ("D19", "SAT Bhuvan Data/Map of India LULC 2024-25.pdf", "SRC_NRSC", "G8_RASTER_MAPS", "2024-25", "India", "Single-page raster map"),
    ("D20", "SAT Bhuvan Data/Andaman Nicobar LULC 2015-16 map.jpg", "SRC_BHUVAN", "G8_RASTER_MAPS", "2015-16", "A&N", "9919x7019 raster LULC map"),
]
