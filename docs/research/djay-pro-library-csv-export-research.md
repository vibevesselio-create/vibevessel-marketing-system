# djay Pro Library to CSV Export — Research Summary

**Research Agent:** Notion AI Research Agent  
**Date:** 2025-01-27  
**Context:** djay Pro synchronization workflows and CSV/Notion integration

---

## Summary

djay Pro does **not** provide a native feature to export the entire music library to CSV format. The application only supports exporting individual DJ session histories as CSV files through the History tab. However, the library data is stored in a SQLite database (`MediaLibrary.db`) using YapDatabase key-value structure, which can be programmatically accessed to extract track metadata for CSV export.

The workspace has already completed Phase 1 inventory analysis of the djay Pro library structure, identifying 12,770 tracks across 21 database collections. Phase 2 (ETL pipeline development) is in progress, with Python scripts being developed to extract BPM, key, and waveform data for Notion integration.

**Critical Finding:** No existing scripts exist in the codebase for djay Pro library-to-CSV conversion. The only reference to djay Pro in the codebase is a backup directory path (`/Volumes/VIBES/Djay-Pro-Auto-Import`) used by the SoundCloud download script.

---

## Key Facts with Citations

### 1. djay Pro Library Structure

- **Database Format:** SQLite3 with YapDatabase key-value structure [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]
- **Database Location:** `/Users/brianhellemn/Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db` [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]
- **Total Tracks:** 12,770 tracks across 21 collections [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]
- **Storage Model:** 93% local file references, 7% global/cloud items [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]
- **Metadata Available:** BPM analysis, key detection, waveform data, cue points, session history [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]

### 2. Native Export Capabilities

- **Session Export Only:** djay Pro can export individual DJ sessions (sets) to CSV via History tab → Export → "Export CSV File" [[Algoriddim Manual](https://download.algoriddim.com/manual/djay-pro-ai-mac-manual-pressqual.pdf)]
- **No Full Library Export:** The application does not provide a built-in feature to export the entire music library to CSV [[Web Research: Multiple Sources]]
- **Export Process:** Navigate to History section, select a set, click Export button, choose "Export CSV File" [[Algoriddim Manual](https://download.algoriddim.com/manual/djay-pro-ai-mac-manual-pressqual.pdf)]

### 3. Third-Party Solutions

- **MIXO:** Can import djay Pro playlists and export to CSV format, but does not preserve beat grids and cue points [[MIXO Documentation](https://www.mixo.dj/guides/djay-pro-to-mixo)]
- **Lexicon:** DJ library management tool that supports exporting playlists to CSV after importing djay Pro library [[Lexicon Manual](https://www.lexicondj.com/manual/share-and-export)]
- **OneLibrary:** Emerging universal DJ library database format developed by AlphaTheta, Algoriddim, and Native Instruments for cross-platform compatibility [[Algoriddim Help](https://help.algoriddim.com/hc/en-us/articles/23070080061212-Using-OneLibrary-in-djay)]

### 4. Technical Access Methods

- **SQLite Direct Access:** The `MediaLibrary.db` file can be opened with tools like DB Browser for SQLite to execute queries and export results to CSV [[DB Schema Documentation](https://dbschema.com/blog/databases/sqlite-database-dbschema/)]
- **Database Structure:** Uses YapDatabase key-value collections, not traditional relational tables [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]
- **Full-Text Search:** Database includes FTS indexes (`fts_mediaItemTitleIDSearchIndex`, `fts_searchIndex`) for optimized queries [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]

### 5. Workspace Integration Context

- **Auto-Import Folder:** The workspace uses `/Volumes/VIBES/Djay-Pro-Auto-Import` as a backup directory for processed audio files [[Codebase: soundcloud_download_prod_merge-2.py:1029]]
- **Sync Workflow Requirement:** A dedicated sub-workflow is needed for djay Pro library synchronization with single-track processing mode [[Notion: Music Sync Sub-Workflow Missing](https://www.notion.so/Music-Sync-Sub-Workflow-Missing-djay-Pro-Library-Synchronization-Single-Library-Single-Track-Mo-4c273872029442a1b5262f25fe3e6d51)]
- **Orchestrator Design:** Part of the Music Library Unified Sync Orchestrator, which dispatches to library-specific sub-workflows [[Notion: Music Library Unified Sync Orchestrator](https://www.notion.so/Music-Sync-Music-Library-Unified-Sync-Orchestrator-2d6e73616c27814ba4e1db6aaef09bde)]
- **CSV Integration:** Explicit mention of integrating with "Google Drive / Sheets or CSV mirrors used for djay Pro auto-import" [[Notion: Music Sync Sub-Workflow Missing](https://www.notion.so/Music-Sync-Sub-Workflow-Missing-djay-Pro-Library-Synchronization-Single-Library-Single-Track-Mo-4c273872029442a1b5262f25fe3e6d51)]

### 6. Current Implementation Status

- **Phase 1 (Complete):** Full inventory and database schema analysis completed 2025-11-23 [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]
- **Phase 2 (In Progress):** Python ETL scripts being developed to extract BPM, key, waveform data for Notion integration [[Notion: djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)]
- **Codebase Status:** No existing djay Pro library-to-CSV conversion scripts found in the repository [[Codebase Search Results]]

### 7. iPad/CloudKit Integration Blocker

- **Critical Gap:** iPad library integration and CloudKit sync layer have not been fully analyzed [[Notion: BLOCKER iPad Library Integration](https://www.notion.so/BLOCKER-iPad-Library-Integration-Not-Analyzed-Music-Sync-Incomplete-2b5e73616c2781478cbce73a63dbc8f8)]
- **Impact:** Multi-device workflow requires understanding CloudKit sync records and iPad database structure before finalizing sync architecture [[Notion: BLOCKER iPad Library Integration](https://www.notion.so/BLOCKER-iPad-Library-Integration-Not-Analyzed-Music-Sync-Incomplete-2b5e73616c2781478cbce73a63dbc8f8)]

---

## Gaps & Next Steps

### Critical Gaps

1. **No Native CSV Export Script**
   - **Gap:** No existing Python script in codebase to convert djay Pro SQLite database to CSV
   - **Impact:** Cannot leverage existing library metadata for Notion synchronization
   - **Next Step:** Develop Python script to read `MediaLibrary.db` and export track metadata to CSV

2. **iPad/CloudKit Sync Analysis Missing**
   - **Gap:** iPad library integration and CloudKit sync records not analyzed [[Notion: BLOCKER iPad Library Integration](https://www.notion.so/BLOCKER-iPad-Library-Integration-Not-Analyzed-Music-Sync-Incomplete-2b5e73616c2781478cbce73a63dbc8f8)]
   - **Impact:** Multi-device synchronization architecture incomplete
   - **Next Step:** Analyze iPad database structure and CloudKit sync records before implementing sync workflow

3. **YapDatabase Structure Understanding**
   - **Gap:** Database uses YapDatabase key-value collections, not standard SQL tables
   - **Impact:** Standard SQL queries may not work; need YapDatabase-specific access methods
   - **Next Step:** Research YapDatabase Python libraries or develop custom key-value extraction logic

4. **Auto-Import Folder CSV Format Unknown**
   - **Gap:** CSV format requirements for djay Pro auto-import folder not documented
   - **Impact:** Cannot generate compatible CSV files for auto-import workflow
   - **Next Step:** Test djay Pro auto-import functionality with sample CSV files to determine required format

5. **Service Page Content Gap**
   - **Gap:** Primary service page `[djay Pro](https://www.notion.so/djay-Pro-0b974aefa61446cbacb2886043eedb5f)` is blank, while technical data exists in separate library page
   - **Impact:** Service Role Framework compliance issue
   - **Next Step:** Merge or link content from library page to service page

### Implementation Questions

1. **Database Access Method:**
   - Should we use read-only SQLite access or require YapDatabase-specific libraries?
   - Can we safely query the database while djay Pro is running, or must it be closed?

2. **CSV Schema Design:**
   - What fields should be included in the CSV export? (Title, Artist, BPM, Key, File Path, etc.)
   - Should the CSV match Notion Music Tracks database schema for direct import?

3. **Sync Direction:**
   - Is this primarily for Ingest (djay Pro → Notion) or Sync (Notion → djay Pro)?
   - How should conflicts be resolved when metadata differs between sources?

4. **Auto-Import Integration:**
   - Does djay Pro watch the auto-import folder automatically, or does it require manual import?
   - What file naming conventions or CSV headers are required?

---

## Developer Experience & Common Issues

### Working Implementations

1. **MIXO Integration Pattern:**
   - Users export djay Pro session history as CSV
   - Import CSV into MIXO
   - Export from MIXO in desired format
   - **Limitation:** Does not preserve beat grids and cue points [[MIXO Documentation](https://www.mixo.dj/guides/djay-pro-to-mixo)]

2. **SQLite Direct Access:**
   - Developers use DB Browser for SQLite to open `MediaLibrary.db`
   - Execute SQL queries to extract track data
   - Export query results to CSV
   - **Challenge:** YapDatabase structure may require specialized access methods

### Common Developer Challenges

1. **Database Locking:**
   - djay Pro may lock the database file while running
   - Solution: Access database when application is closed, or use read-only mode

2. **YapDatabase Complexity:**
   - Key-value structure differs from traditional relational databases
   - May require understanding YapDatabase collection structure before querying

3. **Metadata Preservation:**
   - Third-party tools (MIXO, Lexicon) do not preserve all metadata (beat grids, cue points)
   - Custom scripts may be necessary for complete data extraction

4. **Multi-Device Sync:**
   - iPad/CloudKit integration adds complexity to synchronization
   - Need to account for sync conflicts and merge strategies

---

## Handoff Packet

### Objective
Create a Python script to export djay Pro library metadata from SQLite database to CSV format for Notion synchronization integration.

### Technical Requirements

1. **Database Access:**
   - Read-only access to `/Users/brianhellemn/Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db`
   - Handle YapDatabase key-value structure
   - Extract track metadata: Title, Artist, Album, BPM, Key, File Path, Duration, etc.

2. **CSV Export Format:**
   - Design CSV schema compatible with Notion Music Tracks database
   - Include all relevant metadata fields
   - Support incremental export (only new/changed tracks)

3. **Integration Points:**
   - Align with existing `soundcloud_download_prod_merge-2.py` workflow
   - Support auto-import folder integration (`/Volumes/VIBES/Djay-Pro-Auto-Import`)
   - Connect to Music Library Unified Sync Orchestrator

### Implementation Approach

1. **Phase 1: Database Exploration**
   - Use SQLite Python library (`sqlite3`) to explore database structure
   - Document YapDatabase collection names and key patterns
   - Identify track metadata fields and relationships

2. **Phase 2: CSV Export Script**
   - Create Python script to query database and extract track data
   - Generate CSV file with appropriate schema
   - Add error handling for database locks and missing files

3. **Phase 3: Notion Integration**
   - Map CSV fields to Notion Music Tracks database properties
   - Implement incremental sync logic
   - Add logging and error reporting

4. **Phase 4: Auto-Import Testing**
   - Test CSV format with djay Pro auto-import folder
   - Document required CSV structure
   - Document file naming conventions

### Dependencies

- Python 3.x
- `sqlite3` (standard library)
- Potentially: YapDatabase Python bindings (if available)
- `csv` module (standard library)
- `notion-client` (for Notion integration)

### Success Criteria

- Script successfully extracts all 12,770 tracks from djay Pro database
- CSV export includes all critical metadata (BPM, Key, File Path, etc.)
- CSV format compatible with Notion Music Tracks database import
- Script handles database locks gracefully
- Integration with Music Library Unified Sync Orchestrator

### Blockers to Resolve

1. **iPad/CloudKit Analysis:** Complete analysis of iPad library structure before finalizing sync architecture
2. **YapDatabase Access:** Determine best method to access YapDatabase key-value collections
3. **Auto-Import Format:** Document CSV format requirements for djay Pro auto-import folder

### Relevant Artifacts

- **Technical Spec:** [djay Pro Library](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)
- **Missing Workflow:** [Music Sync Sub-Workflow Missing — djay Pro Library Synchronization](https://www.notion.so/Music-Sync-Sub-Workflow-Missing-djay-Pro-Library-Synchronization-Single-Library-Single-Track-Mo-4c273872029442a1b5262f25fe3e6d51)
- **Blocker:** [BLOCKER: iPad Library Integration Not Analyzed](https://www.notion.so/BLOCKER-iPad-Library-Integration-Not-Analyzed-Music-Sync-Incomplete-2b5e73616c2781478cbce73a63dbc8f8)
- **Orchestrator:** [Music Library Unified Sync Orchestrator](https://www.notion.so/Music-Sync-Music-Library-Unified-Sync-Orchestrator-2d6e73616c27814ba4e1db6aaef09bde)
- **Service Page:** [djay Pro Service](https://www.notion.so/djay-Pro-0b974aefa61446cbacb2886043eedb5f)

### External Resources

- [djay Pro User Manual](https://download.algoriddim.com/manual/djay-pro-ai-mac-manual-pressqual.pdf)
- [MIXO djay Pro Import Guide](https://www.mixo.dj/guides/djay-pro-to-mixo)
- [Lexicon Export Documentation](https://www.lexicondj.com/manual/share-and-export)
- [OneLibrary Documentation](https://help.algoriddim.com/hc/en-us/articles/23070080061212-Using-OneLibrary-in-djay)
- [DB Browser for SQLite](https://dbschema.com/blog/databases/sqlite-database-dbschema/)

---

## Sources

1. **Notion Workspace:**
   - [djay Pro Library Technical Spec](https://www.notion.so/djay-Pro-2b5e73616c278105a927da9bb3e1fef7)
   - [Music Sync Sub-Workflow Missing](https://www.notion.so/Music-Sync-Sub-Workflow-Missing-djay-Pro-Library-Synchronization-Single-Library-Single-Track-Mo-4c273872029442a1b5262f25fe3e6d51)
   - [BLOCKER: iPad Library Integration](https://www.notion.so/BLOCKER-iPad-Library-Integration-Not-Analyzed-Music-Sync-Incomplete-2b5e73616c2781478cbce73a63dbc8f8)
   - [Music Library Unified Sync Orchestrator](https://www.notion.so/Music-Sync-Music-Library-Unified-Sync-Orchestrator-2d6e73616c27814ba4e1db6aaef09bde)
   - [djay Pro Service Page](https://www.notion.so/djay-Pro-0b974aefa61446cbacb2886043eedb5f)

2. **Codebase:**
   - `monolithic-scripts/soundcloud_download_prod_merge-2.py` (line 1029)

3. **External Documentation:**
   - Algoriddim djay Pro User Manual: https://download.algoriddim.com/manual/djay-pro-ai-mac-manual-pressqual.pdf
   - MIXO djay Pro Import Guide: https://www.mixo.dj/guides/djay-pro-to-mixo
   - Lexicon Export Documentation: https://www.lexicondj.com/manual/share-and-export
   - OneLibrary Documentation: https://help.algoriddim.com/hc/en-us/articles/23070080061212-Using-OneLibrary-in-djay
   - DB Browser for SQLite: https://dbschema.com/blog/databases/sqlite-database-dbschema/

4. **Web Research:**
   - Multiple sources confirming djay Pro does not natively export full library to CSV
   - Third-party tool capabilities (MIXO, Lexicon)
   - SQLite database access methods

---

**End of Research Summary**

