# Intelligent Agriculture Information System — Andaman & Nicobar Islands

## CS F/U 407 — Artificial Intelligence

### Project Overview

This project aims to develop an **Intelligent Agriculture Information System for the Andaman & Nicobar Islands**.

The system will collect agricultural information from multiple heterogeneous sources and organize the extracted information into a structured, queryable **Agricultural Knowledge Base**.

The system will use AI-based agents to process different types of sources and eventually answer natural-language queries while maintaining information about the provenance of the extracted data.

---

## Knowledge Base

The initial knowledge base focuses on **Agricultural Production** and **Agricultural Prices**, along with source provenance.

### 1. Agricultural Production

The knowledge base will contain information such as:

- Crop / commodity
- Region / island / district
- Season
- Year
- Area
- Production
- Yield

### 2. Agricultural Prices

The knowledge base will contain information such as:

- Commodity
- Market / region
- Time period
- Wholesale price
- Retail / farm-harvest price, where available
- Unit of measurement

### 3. Source Provenance

Each extracted piece of information will retain its source details, including:

- Source name
- URL
- Document name
- Page / table, where applicable
- Date / period
- Language
- Modality

This will allow the system to provide both the requested information and its source.

---

## Data Sources

The project focuses primarily on official government sources related to agriculture in the Andaman & Nicobar Islands.

The initial source inventory includes:

1. **Basic Statistics — Agriculture**
2. **Market Price Analysis**
3. **Island-wise Statistical Outline**
4. **Land Use Statistics**
5. **Agriculture Census**

Detailed information about the identified sources, including their URLs, information periods, modalities, limitations, and the type of information they provide is maintained in the Phase 1 source inventory.

---

## Phase 1

The objective of Phase 1 is to establish the problem framework and identify viable sources for building the Agricultural Knowledge Base.

### Phase 1 activities

- Define the purpose of the knowledge base
- Identify relevant agricultural information sources
- Record source URLs
- Identify the modalities of the sources
- Study source limitations
- Identify the information that can be extracted
- Determine how each source contributes to the knowledge base

### Phase 1 Source Inventory

The current source inventory is available in the PHASE 1 folder in the repository.

---

## Planned System

The overall system is planned as the following pipeline:

```
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
