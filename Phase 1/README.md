# Intelligent Agriculture Information System — Andaman & Nicobar Islands

## CS F/U 407 — Artificial Intelligence

## Project Overview

This project aims to develop an **Intelligent Agriculture Information System for the Andaman & Nicobar Islands**.

The system collects agricultural and related information from multiple heterogeneous sources and organizes the collected information into a structured and queryable **Agricultural Knowledge Base**.

The current Phase 1 dataset consists of official government statistics, agricultural reports, crop and market analysis, agricultural census information, land-use/land-cover data, Bhuvan geospatial information, and other government information related to agriculture and food processing.

The project also maintains **source provenance**, allowing information to be traced back to the original portal, document, dataset, webpage, or image from which it was obtained.

---

# Knowledge Base

The current knowledge base is organized into the following major categories.

## 1. Basic Agricultural Statistics

The `basic stats` folder contains official statistical information related to agriculture and allied activities in the Andaman & Nicobar Islands.

The collected information includes, where available:

- Farmers / cultivators
- Agricultural area
- Agricultural production
- Agricultural farms
- Agricultural depots
- Irrigation sources
- Agricultural inputs
- Fertilizer-related information
- Organic and non-organic farming
- Livestock and allied agricultural activities
- Other agricultural statistics reported by official sources

The primary statistical material is obtained from the Directorate of Economics & Statistics, Andaman & Nicobar Administration.

---

## 2. Crop and Market Analysis

The `price analysis` folder contains reports and information concerning the **market analysis of agricultural crops and commodities**.

This category includes information such as:

- Crop / commodity
- Market / region
- Time period
- Market prices
- Comparative prices
- Price trends
- Crop-wise market analysis
- Other market-related observations available in the source reports

The term "price analysis" in the repository therefore refers to the broader **crop and market analysis** represented in the collected reports, rather than only individual price values.

---

## 3. Island-wise Statistics

The `island wise stats` folder contains statistical information organized by island, district, or other geographical regions where such information is available.

This category is particularly relevant to the Andaman & Nicobar Islands because agricultural conditions and activities vary across different islands and administrative regions.

The information is intended to support geographical and regional analysis within the Agricultural Knowledge Base.

---

## 4. Agricultural Area and Production

The `total area and prod` folder contains information related to agricultural area and production.

The collected information includes, where available:

- Crop / commodity
- Area
- Production
- Year / period
- Region / island / district
- Other production-related agricultural statistics

This information forms an important component of the Agricultural Knowledge Base for understanding agricultural production in the Union Territory.

---

## 5. Bhuvan, Agricultural Census and LULC Data

The `sat bhuvan data(lulc)` folder contains geospatial, land-use/land-cover, and agricultural census-related information.

The collected material includes:

- Agricultural Census information
- Bhuvan LULC information
- Andaman & Nicobar-specific LULC maps
- India-level LULC information
- Satellite / geospatial map representations
- Land-use and land-cover classifications

The current collection includes relevant **2015–16** Bhuvan/agricultural census information and more recent LULC information, including **2024–25 Bhuvan LULC material** and the **2024 NRSC LULC Atlas**.

The Bhuvan resources include LULC products at different spatial scales. Bhuvan's official resource catalogue lists LULC products at 1:50,000 and 1:250,000 scales, along with associated metadata, statistics, maps and other resources.

The National Remote Sensing Centre (NRSC), ISRO, describes its LULC programme as an annual assessment of land use and land cover for India under the Natural Resources Census programme.

---

## 6. Miscellaneous Agriculture and Food-Processing Information

The `misc data` folder contains additional trusted government information relevant to the agricultural ecosystem.

This includes information related to:

- Food processing
- Government-supported agricultural activities
- Government schemes and support
- Government subsidiaries / organizations
- Agriculture-related institutions
- Other supporting information relevant to the agricultural knowledge base

These sources supplement the main agricultural statistics and help provide broader context for the agriculture and food-processing ecosystem.

---

# Data Organization

The current Phase 1 data is organized into six major folders:

    agriculture-assignment/
    │
    ├── basic stats/
    │
    ├── price analysis/
    │
    ├── island wise stats/
    │
    ├── total area and prod/
    │
    ├── sat bhuvan data(lulc)/
    │
    └── misc data/

Each folder contains the collected source documents, PDFs, images, maps, and other relevant data associated with that category.

The folder structure is intended to preserve the classification of the collected information and make the source material easier to locate and review.

---

# Data Periods

The collected information covers multiple time periods depending on the source and dataset.

Major periods represented in the current collection include:

- **2023–2025** — recent agricultural and statistical information
- **2015–2016** — agricultural census and relevant Bhuvan/LULC information
- **2024** — India-level LULC information from NRSC
- **2024–2025** — recent Bhuvan LULC information
- Other periods where individual reports provide historical, comparative, or supporting information

The exact period associated with each source is maintained in the Phase 1 source inventory and/or the corresponding source document.

---

# Official Data Portals and Sources

The Phase 1 dataset has been collected primarily from official government and government-supported portals.

## 1. Department of Agriculture, Andaman & Nicobar Administration

The official Agriculture Department portal provides agriculture-related information, reports, announcements, schemes, and other information concerning agriculture in the Union Territory.

Source:

- Department of Agriculture — Andaman & Nicobar Administration
- Agriculture Statistics portal

## 2. Directorate of Economics & Statistics, Andaman & Nicobar Administration

The Directorate of Economics & Statistics provides official statistical publications and datasets for the Andaman & Nicobar Islands.

The collected material includes:

- Basic Statistics
- Agricultural statistics
- Economic and statistical reports
- Island-wise statistics
- Agricultural Census information
- Other statistical publications

## 3. Agricultural Census

Agricultural Census information is used to provide structured information concerning agricultural holdings and related agricultural characteristics.

The relevant agricultural census material in the current collection corresponds to the available **2015–16** dataset/source.

## 4. National Remote Sensing Centre (NRSC), ISRO

NRSC provides national-level remote-sensing and geospatial information.

The project uses NRSC's **Land Use / Land Cover (LULC) Atlas** as a supporting source for India-level LULC information.

The NRSC LULC programme provides annual land-use and land-cover information and associated crop-related information derived from satellite data.

## 5. Bhuvan — NRSC / ISRO

Bhuvan is used as the primary geospatial/LULC source for the project's satellite and land-use/land-cover component.

The collected Bhuvan resources include:

- 1:50,000 LULC resources
- 1:250,000 LULC resources
- Andaman & Nicobar-specific LULC maps
- LULC statistics and supporting documentation
- Relevant map images/PDFs

---

# Source Provenance

Maintaining source provenance is an important part of the project.

For each source, the project aims to retain information such as:

- Source name
- Official portal
- Original URL
- Document name
- Dataset name
- Data period
- Page / table reference, where applicable
- Geographic coverage
- Modality
- Type of information provided

The original source documents and images are also retained in the repository where available.

This allows information extracted into the Agricultural Knowledge Base to be traced back to its source.

---

# Phase 1

The objective of Phase 1 is to establish the information framework and collect relevant sources required for building the Agricultural Knowledge Base.

## Phase 1 Activities

- Define the scope of the Agricultural Knowledge Base
- Identify relevant agricultural information
- Identify official government and trusted sources
- Collect source documents and datasets
- Collect relevant maps and geospatial information
- Organize information into meaningful categories
- Record source URLs and provenance
- Identify the time period of each source
- Identify the geographical coverage of each dataset
- Identify the modality of each source
- Identify the information that can be extracted
- Prepare the collected information for subsequent processing and information extraction

---

# Phase 1 Data Categories

| Folder | Main Information |
|---|---|
| `basic stats` | Basic agricultural and statistical information |
| `price analysis` | Crop and market analysis, including price-related information |
| `island wise stats` | Island, district and region-wise statistics |
| `total area and prod` | Agricultural area and production information |
| `sat bhuvan data(lulc)` | Agricultural Census, Bhuvan and LULC/geospatial information |
| `misc data` | Food processing, government support/subsidiaries and other related information |

---

# Planned System

The collected information will be processed and incorporated into the Agricultural Knowledge Base.

The planned system pipeline is:

    Government / Agricultural Sources
                  ↓
           Data Collection
                  ↓
       Document / Data Processing
                  ↓
         Information Extraction
                  ↓
      Agricultural Knowledge Base
                  ↓
               AI Agent
                  ↓
        Natural Language Query
                  ↓
          Answer + Provenance

The final system is intended to allow users to query agricultural information using natural language while retaining the provenance of the information used to generate an answer.

---

# Repository Purpose

This repository serves as the working data and documentation repository for the Intelligent Agriculture Information System.

It currently contains:

- Official agricultural statistical reports
- Basic agricultural statistics
- Crop and market analysis
- Island-wise statistics
- Agricultural area and production information
- Agricultural Census information
- Bhuvan LULC data
- NRSC LULC information
- Maps and images
- Food-processing information
- Government schemes, support and subsidiary-related information
- Phase 1 source documentation

The collected material provides the foundation for subsequent stages of:

**Data Processing → Information Extraction → Knowledge Base Construction → AI-based Querying**

---

# Source Links

The detailed source URLs are maintained in the Phase 1 source inventory.

The principal official sources used in the current collection are:

1. Department of Agriculture, Andaman & Nicobar Administration
2. Directorate of Economics & Statistics, Andaman & Nicobar Administration
3. Agricultural Census
4. National Remote Sensing Centre (NRSC), ISRO
5. Bhuvan — NRSC / ISRO