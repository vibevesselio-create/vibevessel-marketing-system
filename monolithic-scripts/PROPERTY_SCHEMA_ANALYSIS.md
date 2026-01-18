# Music Tracks Database Property Schema Analysis
Generated: 2026-01-16

## Database Info
- **Database ID**: `27ce7361-6c27-80fb-b40e-fefdd47d6640`
- **Title**: Music Tracks

---

## CRITICAL PROPERTIES (Must be updated by processing workflow)

### Core Track Identification
| Property | Type | Purpose | Update When |
|----------|------|---------|-------------|
| `Title` | title | Track name | Initial creation |
| `Artist Name` | rich_text | Primary artist | Initial creation |
| `Album` | rich_text | Album name | Initial creation |
| `Genre` | select | Music genre | Initial creation / enrichment |

### Download/Processing Status
| Property | Type | Purpose | Update When |
|----------|------|---------|-------------|
| `Downloaded` | checkbox | Whether files have been downloaded | After successful file creation |
| `Audio Processing` | multi_select | Processing stages completed | Throughout processing |
| `Audio Processing Status` | multi_select | Current processing status | Throughout processing |
| `Audio Analysis Status` | multi_select | Analysis completion status | After audio analysis |

### File Paths (CRITICAL - prevents reprocessing)
| Property | Type | Purpose | Update When |
|----------|------|---------|-------------|
| `WAV File Path` | rich_text | Path to WAV file | After file creation |
| `AIFF File Path` | rich_text | Path to AIFF file | After file creation |
| `M4A File Path` | rich_text | Path to M4A file | After file creation (if used) |

### Audio Metadata (CRITICAL - must be saved after analysis)
| Property | Type | Purpose | Update When |
|----------|------|---------|-------------|
| `Tempo` | number | BPM value | After audio analysis |
| `Key` | rich_text | Musical key | After audio analysis |
| `Audio Duration (seconds)` | number | Track length | After audio analysis |

### Fingerprint Properties
| Property | Type | Purpose | Update When |
|----------|------|---------|-------------|
| `WAV Fingerprint` | rich_text | WAV file fingerprint | After fingerprint calculation |
| `AIFF Fingerprint` | rich_text | AIFF file fingerprint | After fingerprint calculation |
| `M4A Fingerprint` | rich_text | M4A file fingerprint | After fingerprint calculation |

### Eagle Integration
| Property | Type | Purpose | Update When |
|----------|------|---------|-------------|
| `Eagle File ID` | rich_text | ID in Eagle library | After Eagle import |

---

## AUDIO ANALYSIS PROPERTIES (Updated during processing)

### Quality Metrics
| Property | Type | Purpose |
|----------|------|---------|
| `Audio Quality Score` | number | Overall quality score |
| `Audio LUFS Level` | number | Loudness level |
| `Audio Peak Level` | number | Peak amplitude |
| `Audio RMS Level` | number | RMS level |
| `Audio Dynamic Range (dB)` | number | Dynamic range |
| `Audio Crest Factor` | number | Peak-to-RMS ratio |

### Normalization Metrics
| Property | Type | Purpose |
|----------|------|---------|
| `Audio Normalized` | checkbox | Whether normalization applied |
| `Audio Normalizer Available` | checkbox | Whether normalizer was available |
| `Loudness Level` | number | Target loudness level |
| `Warmth Enhancement Level` | number | Warmth processing level |

### Spectral Analysis
| Property | Type | Purpose |
|----------|------|---------|
| `Audio Spectral Centroid` | number | Brightness measure |
| `Audio Spectral Flatness` | number | Tonality measure |
| `Audio Spectral Rolloff` | number | High frequency content |
| `Audio Harmonic Ratio` | number | Harmonic content |
| `Audio Percussive Ratio` | number | Percussive content |

### Technical Metrics
| Property | Type | Purpose |
|----------|------|---------|
| `Audio Sample Rate` | number | Sample rate in Hz |
| `Audio File Size (MB)` | number | File size |
| `BitRate` | number | Bit rate |
| `Audio Clipping Percentage` | number | Clipping detection |
| `Audio THD Approximation` | number | Distortion estimate |
| `Audio Estimated SNR (dB)` | number | Signal-to-noise ratio |
| `Audio Zero Crossing Rate` | number | ZCR metric |
| `Audio Phase Coherence` | number | Phase correlation |
| `Audio Key Confidence` | number | Key detection confidence |
| `Audio Tempo Consistency` | number | Tempo stability |

---

## SOURCE URL PROPERTIES

| Property | Type | Purpose |
|----------|------|---------|
| `SoundCloud URL` | url | SoundCloud source |
| `Spotify URL` | url | Spotify source |
| `YouTube URL` | url | YouTube source |
| `Bandcamp URL` | url | Bandcamp source |
| `Beatport URL` | url | Beatport source |
| `Apple Music URL` | url | Apple Music source |
| `Dropbox URL` | url | Dropbox source |

---

## SPOTIFY-SPECIFIC PROPERTIES

| Property | Type | Purpose |
|----------|------|---------|
| `Spotify ID` | rich_text | Spotify track ID |
| `Spotify Track ID` | rich_text | Spotify track ID (duplicate?) |
| `Spotify Playlist ID` | rich_text | Source playlist ID |
| `Track URI` | rich_text | Spotify URI |
| `Acousticness` | number | Spotify audio feature |
| `Danceability` | number | Spotify audio feature |
| `Energy` | number | Spotify audio feature |
| `Instrumentalness` | number | Spotify audio feature |
| `Liveness` | number | Spotify audio feature |
| `Speechiness` | number | Spotify audio feature |
| `Valence` | number | Spotify audio feature |
| `Popularity` | number | Spotify popularity |
| `Track Popularity` | number | Spotify popularity (duplicate?) |

---

## PROCESSING METADATA PROPERTIES

| Property | Type | Purpose |
|----------|------|---------|
| `Processing Timestamp` | date | When processed |
| `Processing Duration` | number | Processing time |
| `Compression Mode` | select | Compression setting |
| `Compression Mode Used` | select | Actual compression used |
| `Download Source` | rich_text | Where downloaded from |
| `Fallback Used` | checkbox | Whether fallback was used |
| `System Information` | rich_text | Processing system info |
| `Script Version` | rich_text | Script version used |
| `File Sizes` | rich_text | File size info |
| `Metadata Applied` | multi_select | What metadata was embedded |
| `Audio Processing Details` | rich_text | Detailed processing info |
| `Audio Processing Summary` | rich_text | Summary of processing |

---

## DUPLICATE/LEGACY PROPERTIES (Consider consolidating)

These properties appear to have overlapping purposes:

1. **BPM/Tempo**: `Tempo` (number) vs `AverageBpm` (number)
   - **KEEP**: `Tempo` - it's the standard name
   - **DEPRECATE**: `AverageBpm`

2. **Duration**: `Audio Duration (seconds)` vs `Duration (ms)` vs `TotalTime` vs `Length`
   - **KEEP**: `Audio Duration (seconds)` - clear units
   - **CONVERT**: `Duration (ms)` - divide by 1000
   - **DEPRECATE**: `TotalTime`, `Length`

3. **Track Number**: `Track Number` vs `TrackNumber`
   - **KEEP**: `Track Number` - standard naming
   - **DEPRECATE**: `TrackNumber`

4. **Disc Number**: `Disc Number` vs `DiscNumber`
   - **KEEP**: `Disc Number` - standard naming
   - **DEPRECATE**: `DiscNumber`

5. **Spotify ID**: `Spotify ID` vs `Spotify Track ID`
   - **KEEP**: `Spotify ID` - simpler
   - **DEPRECATE**: `Spotify Track ID`

6. **Popularity**: `Popularity` vs `Track Popularity`
   - **KEEP**: `Popularity` - simpler
   - **DEPRECATE**: `Track Popularity`

---

## RECOMMENDED ALT_PROP_NAMES MAPPING

```python
ALT_PROP_NAMES = {
    # Core identification
    "Title": ["Title", "Name"],
    "Artist Name": ["Artist Name", "Artists"],
    "Album": ["Album", "Album Name"],
    "Genre": ["Genre", "Genres"],

    # Status
    "DL": ["Downloaded", "DL"],

    # File paths
    "WAV File Path": ["WAV File Path", "WAV", "WAV Path"],
    "AIFF File Path": ["AIFF File Path", "AIFF", "AIFF Path"],
    "M4A File Path": ["M4A File Path", "M4A", "M4A Path"],

    # Audio metadata - CRITICAL
    "BPM": ["Tempo", "AverageBpm", "BPM"],  # Tempo is primary
    "Key": ["Key"],
    "Duration (s)": ["Audio Duration (seconds)", "Duration (s)", "TotalTime"],

    # Fingerprints
    "WAV Fingerprint": ["WAV Fingerprint"],
    "AIFF Fingerprint": ["AIFF Fingerprint"],
    "M4A Fingerprint": ["M4A Fingerprint"],
    "Fingerprint": ["WAV Fingerprint", "AIFF Fingerprint", "M4A Fingerprint"],  # Legacy fallback

    # Eagle
    "Eagle File ID": ["Eagle File ID", "Eagle ID", "EagleID"],

    # Source URLs
    "SoundCloud URL": ["SoundCloud URL", "SoundCloud-URL"],
    "Spotify URL": ["Spotify URL", "Spotify Link"],
    "YouTube URL": ["YouTube URL"],

    # Spotify
    "Spotify ID": ["Spotify ID", "Spotify Track ID", "SpotifyID"],

    # Processing
    "Processing Lock": ["Processing Lock"],
    "Audio Processing": ["Audio Processing"],
    "Audio Processing Status": ["Audio Processing Status"],

    # Playlists
    "Playlists": ["Playlists", "Playlist", "Playlist Relation"],
}
```

---

## UNIFIED UPDATE FUNCTION REQUIREMENTS

The unified update function should handle:

1. **Core Track Update** - After successful processing:
   - `Downloaded` = True
   - `WAV File Path` = actual path
   - `Eagle File ID` = eagle item id
   - `WAV Fingerprint` = fingerprint value

2. **Audio Metadata Update** - After audio analysis:
   - `Tempo` = BPM value
   - `Key` = musical key
   - `Audio Duration (seconds)` = duration

3. **Processing Status Update** - Throughout workflow:
   - `Audio Processing` = stages completed
   - `Processing Timestamp` = current time

4. **Quality Metrics Update** - After analysis:
   - All `Audio *` number properties

---

---

## REDUNDANT PROPERTIES ANALYSIS

### Properties to MERGE (Same Data, Multiple Properties)

#### 1. BPM/Tempo
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Tempo` | number | ✅ KEEP | Primary BPM property |
| `AverageBpm` | number | ❌ MERGE | Copy value to `Tempo`, then remove |

**Rationale**: Standard audio software uses "Tempo" or "BPM". Keep `Tempo` as it's the standard.

---

#### 2. Duration
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Audio Duration (seconds)` | number | ✅ KEEP | Primary duration in seconds |
| `Duration (ms)` | number | ❌ MERGE | Convert to seconds, copy to primary |
| `TotalTime` | number | ❌ MERGE | Copy to primary if valid |
| `Length` | rich_text | ❌ REMOVE | Text format, not useful |

**Rationale**: One numeric duration property in seconds is sufficient.

---

#### 3. Track Number
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Track Number` | number | ✅ KEEP | Standard naming |
| `TrackNumber` | number | ❌ MERGE | Copy to primary |

---

#### 4. Disc Number
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Disc Number` | number | ✅ KEEP | Standard naming |
| `DiscNumber` | number | ❌ MERGE | Copy to primary |

---

#### 5. Spotify ID
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Spotify ID` | rich_text | ✅ KEEP | Primary Spotify identifier |
| `Spotify Track ID` | rich_text | ❌ MERGE | Copy to primary |
| `Spotify-ID*` | formula | ⚠️ REVIEW | Formula - check if still needed |

---

#### 6. Popularity
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Popularity` | number | ✅ KEEP | Primary popularity score |
| `Track Popularity` | number | ❌ MERGE | Copy to primary |

---

#### 7. Sample Rate
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Audio Sample Rate` | number | ✅ KEEP | Primary sample rate |
| `SampleRate` | number | ❌ MERGE | Copy to primary |

---

#### 8. Bit Rate
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `BitRate` | number | ✅ KEEP | Primary bit rate |

---

#### 9. Play Count
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `PlayCount` | number | ⚠️ REVIEW | SoundCloud plays? |
| `Play Count (DJ)` | number | ✅ KEEP | DJ session plays |
| `Plays` | number | ❌ MERGE | Merge to appropriate property |

---

#### 10. Date Properties
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `DateAdded` | date | ❌ MERGE | Merge to `Added At` |
| `Added At` | date | ✅ KEEP | Primary add date |
| `Date Added (Dropbox)` | date | ⚠️ REVIEW | Source-specific |
| `DateModified` | rich_text | ❌ REMOVE | Should be `Last edited time` |
| `Created time` | created_time | ✅ KEEP | System property |
| `Last edited time` | last_edited_time | ✅ KEEP | System property |

---

#### 11. Compression Mode
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Compression Mode` | select | ❌ MERGE | Merge to `Compression Mode Used` |
| `Compression Mode Used` | select | ✅ KEEP | What was actually used |
| `Audio Compression Mode` | select | ❌ MERGE | Duplicate |

---

#### 12. Processing Status
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Audio Processing` | multi_select | ✅ KEEP | Processing stages |
| `Audio Processing Status` | multi_select | ❌ MERGE | Redundant with above |
| `Audio Analysis Status` | multi_select | ⚠️ REVIEW | Might be separate |

---

#### 13. Quality Score
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Audio Quality Score` | number | ✅ KEEP | Primary quality score |
| `Quality Score` | number | ❌ MERGE | Duplicate |

---

#### 14. Loudness
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Audio LUFS Level` | number | ✅ KEEP | Primary loudness (LUFS) |
| `Loudness Level` | number | ❌ MERGE | Redundant |
| `Loudness` | number | ⚠️ REVIEW | Spotify loudness? Different scale |

---

#### 15. ISRC
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `ISRC` | rich_text | ✅ KEEP | Primary ISRC |
| `Track ISRC` | rich_text | ❌ MERGE | Duplicate |

---

#### 16. Timestamp Properties
| Current Property | Type | Keep? | Action |
|-----------------|------|-------|--------|
| `Processing Timestamp` | date | ✅ KEEP | When processed |
| `Processed At` | date | ❌ MERGE | Duplicate |
| `Audio Analysis Timestamp` | date | ⚠️ REVIEW | Separate analysis time? |
| `Last Sync Time` | date | ❌ MERGE | Merge to single sync property |
| `Last Sync Timestamp` | date | ❌ REMOVE | Duplicate |
| `Last Merge` | date | ✅ KEEP | Dedup merge timestamp |

---

### Properties to REMOVE (Nonsensical/Unused)

| Property | Type | Reason for Removal |
|----------|------|-------------------|
| `Length` | rich_text | Text format duration - use `Audio Duration (seconds)` |
| `DateModified` | rich_text | Redundant with `Last edited time` |
| `SoundCloud-URL` | formula | Redundant formula |
| `Spotify-ID*` | formula | Redundant formula |
| `Traditional Key` | formula | Can be calculated client-side |
| `__last_synced_iso` | rich_text | Internal sync tracking - should be system property |
| `Property Mapping` | rich_text | Debug/migration property |
| `Merge Confidence` | rich_text | Should be number or removed |
| `Fingerprint File Mapping Notes` | rich_text | Debug property |
| `Audio Analysis Raw Data` | rich_text | Too large, should be separate storage |

---

### Properties to REVIEW (Purpose Unclear)

| Property | Type | Question |
|----------|------|----------|
| `Added By` | number | What does this number represent? |
| `Comments` | number | SoundCloud comments? Should be `SoundCloud Comments` |
| `Likes` | number | SoundCloud likes? Should be `SoundCloud Likes` |
| `Reposts` | number | SoundCloud reposts? Should be `SoundCloud Reposts` |
| `Size` | number | File size? Which file? |
| `Size (Dropbox)` | number | Dropbox-specific size |
| `TrackID` | number | What system's track ID? |
| `Group` | rich_text | What grouping? |
| `Kind` | select | What kind? |
| `License` | select | Track license? |
| `Lifecycle` | select | What lifecycle? |
| `Mix` | rich_text | Mix name/version? |
| `Permalink` | rich_text | SoundCloud permalink? |
| `Source` | select | Download source? Different from `Download Source`? |
| `Streamable` | checkbox | SoundCloud streamable flag? |
| `Downloadable` | checkbox | SoundCloud downloadable flag? |
| `Snapshot ID` | rich_text | Spotify snapshot? |
| `djay Pro ID` | rich_text | djay Pro integration? |
| `Apple Music ID` | select | Should be rich_text |
| `Rekordbox Path` | rich_text | Rekordbox integration? |

---

## UNIFIED PROPERTY SCHEMA (PROPOSED)

### Core Track Properties
| Canonical Name | Type | Description |
|----------------|------|-------------|
| `Title` | title | Track title |
| `Artist Name` | rich_text | Artist name(s) |
| `Album` | rich_text | Album name |
| `Genre` | select | Music genre |
| `Label` | rich_text | Record label |
| `Release Date` | date | Release date |
| `Year` | number | Release year |
| `Track Number` | number | Track number on album |
| `Disc Number` | number | Disc number |
| `ISRC` | rich_text | International Standard Recording Code |

### Audio Analysis Properties
| Canonical Name | Type | Description |
|----------------|------|-------------|
| `Tempo` | number | BPM (beats per minute) |
| `Key` | rich_text | Musical key |
| `Audio Duration (seconds)` | number | Track length in seconds |
| `Audio Sample Rate` | number | Sample rate in Hz |
| `BitRate` | number | Bit rate in kbps |
| `Audio Quality Score` | number | Overall quality score (0-100) |
| `Audio LUFS Level` | number | Loudness in LUFS |
| `Audio Peak Level` | number | Peak amplitude (dB) |
| `Audio RMS Level` | number | RMS level (dB) |
| `Audio Dynamic Range (dB)` | number | Dynamic range |
| `Audio Crest Factor` | number | Peak-to-RMS ratio |
| `Audio Key Confidence` | number | Key detection confidence (0-1) |
| `Audio Tempo Consistency` | number | Tempo stability (0-1) |

### File Properties
| Canonical Name | Type | Description |
|----------------|------|-------------|
| `WAV File Path` | rich_text | Path to WAV file |
| `AIFF File Path` | rich_text | Path to AIFF file |
| `M4A File Path` | rich_text | Path to M4A file |
| `WAV Fingerprint` | rich_text | WAV acoustic fingerprint |
| `AIFF Fingerprint` | rich_text | AIFF acoustic fingerprint |
| `M4A Fingerprint` | rich_text | M4A acoustic fingerprint |
| `Audio File Size (MB)` | number | Primary file size |
| `Eagle File ID` | rich_text | Eagle library ID |

### Status Properties
| Canonical Name | Type | Description |
|----------------|------|-------------|
| `Downloaded` | checkbox | Files downloaded successfully |
| `Audio Normalized` | checkbox | Normalization applied |
| `Duplicate` | checkbox | Known duplicate |
| `Explicit` | checkbox | Explicit content |
| `Audio Processing` | multi_select | Processing stages completed |

### Source Properties
| Canonical Name | Type | Description |
|----------------|------|-------------|
| `SoundCloud URL` | url | SoundCloud source |
| `SoundCloud ID` | number | SoundCloud track ID |
| `Spotify URL` | url | Spotify source |
| `Spotify ID` | rich_text | Spotify track ID |
| `YouTube URL` | url | YouTube source |
| `Apple Music URL` | url | Apple Music source |
| `Bandcamp URL` | url | Bandcamp source |
| `Beatport URL` | url | Beatport source |

### Spotify Audio Features
| Canonical Name | Type | Description |
|----------------|------|-------------|
| `Acousticness` | number | Spotify acousticness (0-1) |
| `Danceability` | number | Spotify danceability (0-1) |
| `Energy` | number | Spotify energy (0-1) |
| `Instrumentalness` | number | Spotify instrumentalness (0-1) |
| `Liveness` | number | Spotify liveness (0-1) |
| `Speechiness` | number | Spotify speechiness (0-1) |
| `Valence` | number | Spotify valence (0-1) |
| `Popularity` | number | Spotify popularity (0-100) |

### Processing Metadata
| Canonical Name | Type | Description |
|----------------|------|-------------|
| `Processing Timestamp` | date | When processing completed |
| `Compression Mode Used` | select | Compression mode applied |
| `Download Source` | rich_text | Source used for download |
| `Fallback Used` | checkbox | Whether fallback was needed |

### Relations
| Canonical Name | Type | Description |
|----------------|------|-------------|
| `Playlists` | relation | Related playlists |
| `Artist` | relation | Related artist pages |
| `DJ Sessions` | relation | Related DJ sessions |
| `Sets/Mixes` | relation | Related mixes |
| `Goes With:` | relation | Compatible tracks |

---

## ACTION ITEMS

1. [ ] Update `ALT_PROP_NAMES` to match actual schema
2. [ ] Create migration script to merge duplicate properties
3. [ ] Create unified `update_track_complete()` function
4. [ ] Ensure all workflows use canonical property names
5. [ ] Add validation to ensure critical properties are set
6. [ ] Remove deprecated/unused properties from schema
7. [ ] Update documentation with canonical schema

---

## METADATA GAP ANALYSIS (2026-01-16)

### Properties Listed in Schema BUT NOT CALCULATED by Script

These properties exist in the database schema but the script does NOT calculate or populate them:

| Property | Type | Status | Recommendation |
|----------|------|--------|----------------|
| `Audio Spectral Centroid` | number | ❌ NOT CALCULATED | **REMOVE** - Advanced analysis not implemented |
| `Audio Spectral Flatness` | number | ❌ NOT CALCULATED | **REMOVE** - Advanced analysis not implemented |
| `Audio Spectral Rolloff` | number | ❌ NOT CALCULATED | **REMOVE** - Advanced analysis not implemented |
| `Audio Harmonic Ratio` | number | ❌ NOT CALCULATED | **REMOVE** - Advanced analysis not implemented |
| `Audio Percussive Ratio` | number | ❌ NOT CALCULATED | **REMOVE** - Advanced analysis not implemented |
| `Audio Clipping Percentage` | number | ⚠️ CALCULATED but NOT SAVED | **FIX** - Add to unified_track_update |
| `Audio THD Approximation` | number | ❌ NOT CALCULATED | **REMOVE** - Not implemented |
| `Audio Estimated SNR (dB)` | number | ❌ NOT CALCULATED | **REMOVE** - Not implemented |
| `Audio Zero Crossing Rate` | number | ❌ NOT CALCULATED | **REMOVE** - Not implemented |
| `Audio Phase Coherence` | number | ❌ NOT CALCULATED | **REMOVE** - Not implemented |
| `Audio Key Confidence` | number | ❌ NOT CALCULATED | **ADD** - librosa key detection can provide this |
| `Audio Tempo Consistency` | number | ❌ NOT CALCULATED | **REMOVE** - Not implemented |
| `Warmth Enhancement Level` | number | ⚠️ CALCULATED but NOT SAVED | **FIX** - Add to unified_track_update |
| `Processing Duration` | number | ⚠️ CAN BE CALCULATED | **ADD** - Track processing time |
| `Audio File Size (MB)` | number | ⚠️ CAN BE CALCULATED | **ADD** - os.path.getsize() on output file |

### Properties CALCULATED but NOT SAVED to Notion

| Data Calculated | Source Function | Notion Property | Status |
|-----------------|-----------------|-----------------|--------|
| `clipping_percentage` | `analyze_audio_loudness` | `Audio Clipping Percentage` | ❌ NOT SAVED |
| `harmonic_content` | `apply_harmonic_saturation` | N/A | ❌ NO PROPERTY |
| `warmth_applied` | normalization_metrics | `Warmth Enhancement Level` | ❌ NOT SAVED |
| `original_lufs` | normalization_metrics | N/A (could use) | ❌ NOT SAVED |
| `gain_applied_db` | normalization_metrics | N/A | ❌ NOT SAVED |
| `limiting_applied` | normalization_metrics | N/A | ❌ NOT SAVED |

### Fix: Add Missing Data to unified_track_update

The following should be added to `processing_data_unified` and `unified_track_update`:

```python
# In normalization_metrics creation (already fixed):
'clipping_percentage': initial_analysis.get('clipping_percentage'),

# In processing_data_unified:
"clipping_percentage": norm_metrics.get("clipping_percentage"),
"warmth_level": 1.0 if norm_metrics.get("warmth_applied") else 0.0,

# In unified_track_update set_prop calls:
set_prop("Audio Clipping Percentage", processing_data.get("clipping_percentage"), "number")
set_prop("Warmth Enhancement Level", processing_data.get("warmth_level"), "number")
```

---

## PROPERTIES TO REMOVE (No Data Source, No Value)

These properties have NO sensible data source in the current workflow and should be removed:

### Spectral Analysis Properties (NOT IMPLEMENTED)
| Property | Reason for Removal |
|----------|-------------------|
| `Audio Spectral Centroid` | librosa can calculate but NOT in current workflow |
| `Audio Spectral Flatness` | librosa can calculate but NOT in current workflow |
| `Audio Spectral Rolloff` | librosa can calculate but NOT in current workflow |
| `Audio Harmonic Ratio` | NOT calculated |
| `Audio Percussive Ratio` | NOT calculated |
| `Audio THD Approximation` | NOT calculated |
| `Audio Estimated SNR (dB)` | NOT calculated |
| `Audio Zero Crossing Rate` | NOT calculated |
| `Audio Phase Coherence` | NOT calculated |
| `Audio Tempo Consistency` | NOT calculated |

### Debug/Migration Properties (OBSOLETE)
| Property | Reason for Removal |
|----------|-------------------|
| `Property Mapping` | Debug property from migration |
| `Merge Confidence` | Should be number, rarely used |
| `Fingerprint File Mapping Notes` | Debug property |
| `Audio Analysis Raw Data` | Too large, rarely useful |
| `__last_synced_iso` | Internal sync tracking |

### Redundant Formulas (COMPUTED CLIENT-SIDE)
| Property | Reason for Removal |
|----------|-------------------|
| `SoundCloud-URL` | Formula - URL already in `SoundCloud URL` |
| `Spotify-ID*` | Formula - ID already in `Spotify ID` |
| `Traditional Key` | Formula - can compute from `Key` |

### Ambiguous/Orphaned Properties (PURPOSE UNKNOWN)
| Property | Type | Issue |
|----------|------|-------|
| `Added By` | number | What does this number represent? No clear source |
| `TrackID` | number | Which system's ID? Redundant with source IDs |
| `Group` | rich_text | What grouping system? |
| `Kind` | select | What classification? |
| `Lifecycle` | select | What lifecycle stages? |
| `Mix` | rich_text | Mix name/version - redundant with Title |
| `Source` | select | Redundant with `Download Source` |
| `Snapshot ID` | rich_text | Spotify playlist snapshot - rarely useful |

---

## PROPERTIES TO KEEP (Valuable, Mappable Data)

### SoundCloud Metadata (CAN BE POPULATED)
| Property | Data Source | Status |
|----------|-------------|--------|
| `Comments` | SoundCloud API `comment_count` | ⚠️ Rename to `SoundCloud Comments` |
| `Likes` | SoundCloud API `likes_count` | ⚠️ Rename to `SoundCloud Likes` |
| `Reposts` | SoundCloud API `reposts_count` | ⚠️ Rename to `SoundCloud Reposts` |
| `Plays` | SoundCloud API `playback_count` | ⚠️ Rename to `SoundCloud Plays` |
| `Permalink` | SoundCloud API `permalink_url` | ✅ Keep as-is |
| `License` | SoundCloud API `license` | ✅ Keep as-is |
| `Streamable` | SoundCloud API `streamable` | ✅ Keep as-is |
| `Downloadable` | SoundCloud API `downloadable` | ✅ Keep as-is |

### DJ Software Integration (KEEP)
| Property | Data Source | Status |
|----------|-------------|--------|
| `djay Pro ID` | djay Pro export | ✅ Keep |
| `Play Count (DJ)` | DJ session tracking | ✅ Keep |
| `Rekordbox Path` | Rekordbox library path | ✅ Keep |

### File Management (KEEP)
| Property | Data Source | Status |
|----------|-------------|--------|
| `Size` | File size of primary file | ⚠️ Rename to `Audio File Size (MB)` |
| `Size (Dropbox)` | Dropbox file size | ⚠️ Review if Dropbox used |
| `Date Added (Dropbox)` | Dropbox add date | ⚠️ Review if Dropbox used |

---

## FINAL PROPERTY COUNT SUMMARY

| Category | Keep | Remove | Merge | Total |
|----------|------|--------|-------|-------|
| Core Identification | 10 | 0 | 0 | 10 |
| Audio Analysis | 8 | 10 | 2 | 20 |
| File Properties | 8 | 0 | 0 | 8 |
| Status/Processing | 6 | 3 | 3 | 12 |
| Source URLs | 7 | 1 | 0 | 8 |
| Spotify Features | 8 | 1 | 2 | 11 |
| SoundCloud Stats | 6 | 0 | 0 | 6 |
| DJ Integration | 3 | 0 | 0 | 3 |
| Relations | 5 | 0 | 0 | 5 |
| Debug/Migration | 0 | 6 | 0 | 6 |
| **TOTAL** | **61** | **21** | **7** | **89** |

**Recommended actions:**
- Remove 21 properties (spectral analysis + debug + orphaned)
- Merge 7 duplicate property pairs
- Final schema: ~61 active properties
