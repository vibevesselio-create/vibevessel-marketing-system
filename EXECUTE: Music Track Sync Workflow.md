EXECUTE: Music Track Sync Workflow
⚡ IMMEDIATE EXECUTION REQUIRED - NO QUESTIONS, NO CLARIFICATIONS

**MANDATORY EXECUTION RULES:**
1. DO NOT summarize this document
2. DO NOT ask clarifying questions
3. DO NOT request confirmation
4. DO NOT explain what you're going to do - JUST DO IT
5. Execute ALL phases in sequence immediately
6. Report results in the exact format specified below
7. If a step fails, follow the error handling rules and continue

**EXPECTED AGENT RESPONSE FORMAT:**
- Execute each phase immediately upon reading
- Report progress as: "PHASE X: [status] - [action taken]"
- Report completion as: "PHASE X COMPLETE: [summary]"
- Report errors as: "PHASE X ERROR: [error] - [action taken per error handling]"
- Final report: "WORKFLOW COMPLETE: [Success/Partial] - [details]"

Begin PHASE 0 now. Execute all phases in sequence.

Input Parameters
| Parameter | Value |

|-----------|-------|

| URL | [PASTE SPOTIFY / SOUNDCLOUD / YOUTUBE URL HERE] — leave blank for auto-detect |

| Run Mode | ${RUN_MODE:-DEV} (DEV = dry-run, PROD = full execution) |

Database IDs
| Database | Env Variable | Fallback ID |

|----------|--------------|-------------|

| Music Tracks | ${TRACKS_DB_ID} | 27ce7361-6c27-80fb-b40e-fefdd47d6640 |

| Music Artists | ${ARTISTS_DB_ID} | 20ee7361-6c27-816d-9817-d4348f6de07c |

SoundCloud Profile
${SOUNDCLOUD_PROFILE:-vibe-vessel}

PHASE 0: Detect & Resolve Source
**YOU MUST:** Identify track source and proceed immediately. No questions about which source to use.

0.1 — If URL Provided: Detect Type
**EXPECTED RESPONSE:** Execute detection immediately and report: "PHASE 0.1: Source detected - [Spotify/SoundCloud/YouTube] - Track ID: [id]"
| URL Pattern | Source | Action |

|-------------|--------|--------|

| open.spotify.com/track/ | Spotify | Extract track ID, use Spotify API |

| soundcloud.com/ | SoundCloud | Use SoundCloud workflow |

| youtube.com/watch or youtu.be/ | YouTube | Extract video, search for Spotify/SoundCloud |

| on.soundcloud.com/ | SoundCloud (short) | web_fetch to resolve full URL |

**Spotify Track Processing:**
- Spotify tracks automatically search YouTube for alternative audio source
- Production workflow script searches YouTube using track title and artist name
- If YouTube URL found, track is downloaded and processed through full pipeline (M4A, AIFF, WAV creation)
- If no YouTube source found, falls back to metadata-only processing
- YouTube URL is saved to Notion for future reference
- All file formats (M4A, AIFF, WAV) are created in production workflow when YouTube source is found

0.2 — If No URL: Execute Sync-Aware Fallback Chain
**EXPECTED RESPONSE:** Execute fallback chain immediately. Report: "PHASE 0.2: Fallback chain executing - Priority [1/2/3] - Track found: [title] by [artist]"

RULE: Guarantee at least one track sync. If first source is fully synced, fall back to next. DO NOT ask which priority to use - execute all priorities until one succeeds.

Priority 1: Check Spotify Current Track
**EXPECTED RESPONSE:** Execute osascript command immediately. If Spotify is playing, query Notion. Report: "PHASE 0.2 Priority 1: [Playing/Not Playing] - [Track found/Not found in Notion]"

osascript -e 'tell application "Spotify" to {name, artist, id} of current track'


**YOU MUST:** If Spotify playing, query Notion immediately. DO NOT wait for confirmation:


notionApi:API-post-database-query on ${TRACKS_DB_ID}

filter: {"property": "Spotify ID", "rich_text": {"equals": "{spotify_track_id}"}}


| Spotify State | Notion Result | Action |

|---------------|---------------|--------|

| Playing | Not found | USE THIS TRACK → Phase 1 |

| Playing | Found, incomplete | USE THIS TRACK → Phase 1 (update) |

| Playing | Found, FULLY SYNCED | FALLBACK → Priority 2 |

| Not playing / Error | — | FALLBACK → Priority 2 |

Priority 2: Fetch SoundCloud Likes (up to 5)

source /Users/brianhellemn/Projects/venv-unified-MM1/bin/activate

cd /Users/brianhellemn/Projects/github-production/monolithic-scripts

SOUNDCLOUD_PROFILE="${SOUNDCLOUD_PROFILE:-vibe-vessel}"

python3 -c "

from yt_dlp import YoutubeDL

opts = {'quiet': True, 'extract_flat': False}

ytdl = YoutubeDL(opts)

info = ytdl.extract_info('https://soundcloud.com/${SOUNDCLOUD_PROFILE}/likes', download=False)

if info and info.get('entries'):

    for track in info['entries'][:5]:

        url = track.get('webpage_url') or track.get('url')

        title = track.get('title')

        artist = track.get('uploader')

        print(f'URL: {url}')

        print(f'TITLE: {title}')

        print(f'ARTIST: {artist}')

        print('---')

"


**EXPECTED RESPONSE:** Execute Python script immediately. For each track returned, query Notion. Report: "PHASE 0.2 Priority 2: [X] tracks fetched - [First unsynced track found/All synced, falling back]"

**YOU MUST:** For each track: Query Notion immediately. First unsynced/incomplete → USE IT → Proceed to Phase 1. DO NOT ask which track to use.

All 5 synced: → FALLBACK → Priority 3 (execute immediately, no questions)

Priority 3: Fetch Spotify Liked Tracks (up to 5)

**Note:** Spotify "Liked Songs" are accessed via the "Liked Songs" playlist. If direct saved tracks API is needed, it requires `/me/tracks` endpoint which is not currently implemented in spotify_integration_module.

**Fallback Chain Execution Rules:**
- Maximum 2 attempts per priority level
- Timeout after 30 seconds for each fetch operation
- If timeout or 2 failures: Move to next priority immediately
- Document failures but don't block workflow
- After 3 failed priorities: Use production script --mode single as final fallback

source /Users/brianhellemn/Projects/venv-unified-MM1/bin/activate

cd /Users/brianhellemn/Projects/github-production/monolithic-scripts

python3 -c "

from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager

try:
    oauth = SpotifyOAuthManager()
    sp = SpotifyAPI(oauth)
    
    # Get user playlists and find "Liked Songs" playlist
    playlists = sp.get_user_playlists(limit=50, offset=0)
    liked_songs_playlist = None
    
    for playlist in playlists:
        if playlist.get('name') == 'Liked Songs' or 'liked' in playlist.get('name', '').lower():
            liked_songs_playlist = playlist
            break
    
    if liked_songs_playlist:
        playlist_id = liked_songs_playlist.get('id')
        tracks = sp.get_playlist_tracks(playlist_id, limit=5)
        
        for item in tracks[:5]:
            track = item.get('track', {})
            if track:
                track_id = track.get('id')
                track_name = track.get('name', 'Unknown')
                artist_name = track.get('artists', [{}])[0].get('name', 'Unknown')
                
                print(f'URL: https://open.spotify.com/track/{track_id}')
                print(f'TITLE: {track_name}')
                print(f'ARTIST: {artist_name}')
                print(f'ID: {track_id}')
                print('---')
    else:
        print('Liked Songs playlist not found')
        # Fallback: Use first playlist as alternative
        if playlists:
            first_playlist = playlists[0]
            playlist_id = first_playlist.get('id')
            tracks = sp.get_playlist_tracks(playlist_id, limit=5)
            for item in tracks[:5]:
                track = item.get('track', {})
                if track:
                    track_id = track.get('id')
                    track_name = track.get('name', 'Unknown')
                    artist_name = track.get('artists', [{}])[0].get('name', 'Unknown')
                    print(f'URL: https://open.spotify.com/track/{track_id}')
                    print(f'TITLE: {track_name}')
                    print(f'ARTIST: {artist_name}')
                    print(f'ID: {track_id}')
                    print('---')
except Exception as e:
    print(f'Spotify API error: {e}')
    # Proceed to production script or next fallback

"


**EXPECTED RESPONSE:** Execute Python script immediately. For each track returned, query Notion. Report: "PHASE 0.2 Priority 3: [X] tracks fetched - [First unsynced track found/All synced, stopping]"

**YOU MUST:** For each track: Query Notion immediately. First unsynced/incomplete → USE IT → Proceed to Phase 1. DO NOT ask which track to use.

All 5 synced: → STOP — Report "PHASE 0.2 COMPLETE: All recent likes already synced - Workflow stopping"

0.3 — Normalize Track Identity
**EXPECTED RESPONSE:** Extract and store all available data. Report: "PHASE 0.3 COMPLETE: Track identity normalized - Title: [title], Artist: [artist], Source: [source], URLs: [list]"

**YOU MUST:** Extract and store immediately:
- track_title, track_artist, primary_source
- spotify_url, soundcloud_url, youtube_url (as available)
- duration_ms (for cross-platform matching, ±2000ms tolerance)

DO NOT ask which fields to extract - extract ALL available fields.

PHASE 1: Deduplicate (REQUIRED)
**EXPECTED RESPONSE:** Execute all deduplication checks immediately. Report: "PHASE 1: Deduplication check - [Match found/No match] - [Action taken]"

**YOU MUST:** Complete deduplication before proceeding. DO NOT skip this phase.

1.1 — Query Notion (stop on first match)
**EXPECTED RESPONSE:** Execute queries in order until match found. Report: "PHASE 1.1: [Match type] found - [Action: Update existing/Skip to Phase 6/Continue]"

notionApi:API-post-database-query on ${TRACKS_DB_ID}


Check in order:

Spotify ID Match:


{"property": "Spotify ID", "rich_text": {"equals": "{spotify_track_id}"}}


SoundCloud URL Match:


{"property": "SoundCloud URL", "url": {"contains": "{soundcloud_permalink}"}}


YouTube URL Match:


{"property": "YouTube URL", "url": {"contains": "{youtube_video_id}"}}


Title + Artist Fuzzy Match:


{"and": [

  {"property": "Title", "title": {"contains": "{core_title}"}},

  {"property": "Artist Name", "rich_text": {"contains": "{artist_name}"}}

]}


**YOU MUST:** If match found: Check completeness immediately. Missing URLs or Downloaded=false → update existing, continue to Phase 2. Fully complete → log "PHASE 1.1: Track fully synced, skipping to Phase 6", proceed to Phase 6. DO NOT ask what to do - follow the rules.

1.2 — Check Local Filesystem
**EXPECTED RESPONSE:** Execute filesystem search immediately. Report: "PHASE 1.2: Filesystem check - [Files found/Not found] - [Action taken]"

**YOU MUST:** Execute this command immediately. DO NOT ask which directories to check:

for dir in \

  "/Users/brianhellemn/Music/Downloads/SoundCloud" \

  "/Users/brianhellemn/Music/Downloads/Spotify" \

  "/Users/brianhellemn/Music/Downloads/YouTube" \

  "/Volumes/SYSTEM_SSD/Dropbox/Music/playlists" \

  "/Volumes/SYSTEM_SSD/Dropbox/Music/m4A-tracks" \

  "/Volumes/SYSTEM_SSD/Dropbox/Music/wav-tracks" \

  "/Volumes/VIBES/Playlists"; do

  [ -d "$dir" ] && find "$dir" -iname "*{partial_title}*" -type f 2>/dev/null

done


| Notion | Local | Action |

|--------|-------|--------|

| Found (complete) | Found | Skip to Phase 6 |

| Found (incomplete) | Found | Update Notion with file path, add missing URLs |

| Found (incomplete) | Not found | Continue to download |

| Not found | Found | Add to Notion with file path (skip download) |

| Not found | Not found | Full workflow |

PHASE 2: Resolve Cross-Platform URLs
**EXPECTED RESPONSE:** Execute all URL searches immediately. Report: "PHASE 2 COMPLETE: URLs resolved - Spotify: [url/not found], SoundCloud: [url/not found], YouTube: [url/not found]"

**YOU MUST:** Populate Spotify URL, SoundCloud URL, and YouTube URL for every track. Execute all searches. DO NOT skip any platform.

2.1 — From Spotify Source
**EXPECTED RESPONSE:** Execute both web_search queries immediately. Report: "PHASE 2.1: Spotify source - SoundCloud: [found/not found], YouTube: [found/not found]"

**YOU MUST:** Execute both searches immediately:
- SoundCloud: web_search("{title}" "{artist}" site:soundcloud.com)
- YouTube: web_search("{title}" "{artist}" site:youtube.com) (prefer Official Audio)

DO NOT ask which to search - search BOTH.

2.2 — From SoundCloud Source
Spotify: {title} {artist} spotify

YouTube: Same as above

2.3 — From YouTube Source
Spotify: Same as above

SoundCloud: Same as above

2.4 — Verify URLs
**EXPECTED RESPONSE:** Verify all URLs immediately. Report: "PHASE 2.4: URL verification - [X] URLs verified, [Y] failed"

**YOU MUST:** web_fetch each resolved URL to confirm HTTP 200. Store alternates in Notes. DO NOT skip verification.

PHASE 3: Database Operations
**EXPECTED RESPONSE:** Execute all database operations immediately. Report: "PHASE 3 COMPLETE: Artists [created/found], Track [created/updated]"

**YOU MUST:** Complete all database operations. DO NOT skip any step.

3.1 — Search/Create Artists
**EXPECTED RESPONSE:** Query Notion immediately, create missing artists. Report: "PHASE 3.1: Artists - [X] found, [Y] created"

notionApi:API-post-database-query on ${ARTISTS_DB_ID}

filter: {"or": [

  {"property": "Name", "title": {"contains": "{artist_1}"}},

  {"property": "Name", "title": {"contains": "{artist_2}"}}

]}


**YOU MUST:** For remixes: Link BOTH remixer AND original artist. DO NOT ask which artists to link - link ALL.

**YOU MUST:** Create missing artists immediately. DO NOT ask for confirmation:


notionApi:API-post-page on ${ARTISTS_DB_ID}

properties: {Name, Source, Spotify URL/SoundCloud Profile URL, Last Used}


3.2 — Create Track Entry
**EXPECTED RESPONSE:** Create track page immediately. Report: "PHASE 3.2: Track created - Page ID: [id]"

**YOU MUST:** Create track entry immediately. DO NOT wait for confirmation:

notionApi:API-post-page on ${TRACKS_DB_ID}

properties: {Title: {title: [{text: {content: "{full_track_title}"}}]}}


3.3 — Update Full Metadata
**EXPECTED RESPONSE:** Update all metadata properties immediately. Report: "PHASE 3.3: Metadata updated - [X] properties set"

**YOU MUST:** Update ALL properties listed below. DO NOT skip any property:

notionApi:API-patch-page


Properties to set (SET ALL OF THESE):

| Property | Value |

|----------|-------|

| Artist | relation: [artist_ids] |

| Artist Name | "{artist_name}" |

| Source | select: "{primary_source}" |

| Genre | select: "{genre}" |

| Spotify URL | url (if found) |

| Spotify ID | rich_text (if found) |

| SoundCloud URL | url (if found) |

| YouTube URL | url (if found) |

| Image URL | url: artwork |

| Release Date | date |

| DateAdded | today |

| Last Used | today |

| Duration (ms) | number |

| Album | rich_text (Spotify) |

| Popularity | number (Spotify) |

| ISRC / Track ISRC | rich_text (Spotify) |

PHASE 4: Download Track
**EXPECTED RESPONSE:** Execute download immediately using best available source. Report: "PHASE 4: Download started - Source: [SoundCloud/YouTube/Spotify], Command: [command executed]"

**YOU MUST:** Download track immediately. DO NOT ask which source to use.

4.1 — Select Best Source
**YOU MUST:** Use priority order: SoundCloud > YouTube > Spotify. Select first available source and proceed immediately.

4.2 — Execute Download
**EXPECTED RESPONSE:** Execute download command for selected source immediately. Report: "PHASE 4.2: Download executing - Source: [source], Status: [in progress]"

**YOU MUST:** Execute the appropriate download command based on source selected. DO NOT ask which command to run:

From SoundCloud:


source /Users/brianhellemn/Projects/venv-unified-MM1/bin/activate

cd /Users/brianhellemn/Projects/github-production/monolithic-scripts

python soundcloud_download_prod_merge-2.py --url "{soundcloud_url}" --single


From YouTube:


source /Users/brianhellemn/Projects/venv-unified-MM1/bin/activate

yt-dlp -x --audio-format wav --audio-quality 0 \

  --embed-thumbnail --add-metadata \

  -o "/Users/brianhellemn/Music/Downloads/YouTube/%(title)s.%(ext)s" \

  "{youtube_url}"


From Spotify:


source /Users/brianhellemn/Projects/venv-unified-MM1/bin/activate

command -v spotdl >/dev/null 2>&1 || { echo "spotdl not installed"; exit 1; }

spotdl download "{spotify_url}" \

  --output "/Users/brianhellemn/Music/Downloads/Spotify/{artist} - {title}.{output-ext}"


4.3 — Verify Download
**EXPECTED RESPONSE:** Execute verification command immediately. Report: "PHASE 4.3: Download verified - File: [path], Size: [size]"

**YOU MUST:** Execute this command immediately. DO NOT skip verification:

ls -la "/Users/brianhellemn/Music/Downloads/{Source}/"*"{partial_title}"*


4.4 — Verify Production Workflow File Creation (MANDATORY)
**EXPECTED RESPONSE:** Execute ALL verification commands immediately. Report: "PHASE 4.4: File verification - M4A: [found/missing], AIFF: [found/missing], WAV: [found/missing]"

**YOU MUST:** After production workflow execution, verify all expected files were created. Execute ALL checks below. DO NOT skip any verification:

**File Creation Verification:**

**Check M4A File:**
- Primary: `ls -lh "{OUT_DIR}/{playlist_name}/{track_name}.m4a"`
- Backup: `ls -lh "{BACKUP_DIR}/{track_name}.m4a"`
- OUT_DIR Default: `/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/EAGLE-AUTO-IMPORT/Music Library-2`
- BACKUP_DIR Default: `/Volumes/VIBES/Djay-Pro-Auto-Import`

**Check AIFF File:**
- Primary: `ls -lh "{OUT_DIR}/{playlist_name}/{track_name}.aiff"`
- Expected Path: `{OUT_DIR}/Unassigned/{track_name}.aiff` (if no playlist relation)

**Check WAV Backup File:**
- Backup: `ls -lh "{WAV_BACKUP_DIR}/{track_name}.wav"`
- WAV_BACKUP_DIR Default: `/Volumes/VIBES/Apple-Music-Auto-Add`

**Verify File Properties:**
- File sizes should be reasonable (> 1MB for audio files)
- Verify Notion properties contain file paths:
  * Query Notion page for "M4A File Path" property
  * Query Notion page for "AIFF File Path" property
  * Query Notion page for "WAV File Path" property

**YOU MUST:** If Files Missing:
- Check production workflow logs for errors immediately
- Verify Spotify track found YouTube alternative source
- Create Agent-Task immediately if files expected but not created (use error handling section below)
- Report: "PHASE 4.4 ERROR: Files missing - [details] - Agent-Task created"

4.5 — Update Notion
**EXPECTED RESPONSE:** Update Notion immediately with download status. Report: "PHASE 4.5: Notion updated - Downloaded: true, File paths: [paths]"

**YOU MUST:** Update Notion immediately. DO NOT wait for confirmation:

notionApi:API-patch-page

properties: {

  Downloaded: {checkbox: true},

  Processed At: {date: today},

  WAV File Path / M4A File Path: {rich_text: file_path},

  Download Source: {rich_text: "{source}"}

}


PHASE 5: Post-Processing Handoff (Optional)
**EXPECTED RESPONSE:** If needed, create trigger file immediately. Report: "PHASE 5: [Trigger file created/Not needed]"

**YOU MUST:** If audio analysis or Eagle import needed, create trigger file immediately. DO NOT ask if it's needed - create it if files were downloaded:

Write trigger file to: /Users/brianhellemn/Documents/Agents/Agent-Triggers/Cursor-MM1-Agent-Trigger/01_inbox


# [Cursor MM1] — Audio Processing: {track_title} — {date}

 

## Track

- Title: {title}

- Notion Page: {page_id}

- File Path: {downloaded_file_path}

 

## Tasks

- [ ] BPM analysis

- [ ] Key detection

- [ ] Eagle library import

- [ ] Update Notion with audio metadata


PHASE 6: Cross-Platform Bonus Sync (MANDATORY)
**EXPECTED RESPONSE:** Execute bonus sync immediately after primary track complete. Report: "PHASE 6: Bonus sync - [Source selected] - [Track found/Not found] - [Action taken]"

**YOU MUST:** Execute after primary track processing complete. DO NOT skip this phase.

6.1 — Determine Bonus Source
| Primary Source | Bonus Target |

|----------------|--------------|

| Spotify | SoundCloud most recent like |

| SoundCloud | Spotify most recent liked |

| YouTube | SoundCloud first, then Spotify if SC synced |

6.2 — Recursion Guards
Max bonus syncs per session: 1

Skip if: Bonus track URL = Primary track URL

Skip if: Bonus track already fully synced

6.3 — Execute Bonus Sync
**EXPECTED RESPONSE:** Fetch bonus track immediately. Report: "PHASE 6.3: Bonus track fetched - [title] by [artist]"

**YOU MUST:** Fetch most recent track from alternate platform immediately (use Phase 0.2 scripts). DO NOT ask which platform - follow the table above.

6.4 — Process Bonus Track
**EXPECTED RESPONSE:** Process bonus track immediately. Report: "PHASE 6.4: Bonus track - [Synced/Skipped - already synced]"

**YOU MUST:** Dedupe Check: Query Notion immediately.

**YOU MUST:** If not synced/incomplete: Run Phases 2-4 immediately. DO NOT ask - just execute.

**YOU MUST:** If fully synced: Log "PHASE 6.4: Bonus track already synced" → DONE

Error Handling
**EXPECTED RESPONSE:** On any error, follow error handling rules immediately. Report: "ERROR HANDLED: [Error type] - [Action taken]"

**YOU MUST:** On Critical Failure: Create Agent-Task immediately. DO NOT ask for permission. Execute this immediately:

notionApi:API-post-page on 284e7361-6c27-8018-872a-eb14e82e0392

properties: {

  Name: {title: [{text: {content: "CRITICAL: Music Sync Failure - {error_type}"}}]},

  Status: {status: {name: "Not Started"}},

  Priority: {select: {name: "High"}},

  Description: {rich_text: [{text: {content: "Error: {error_message}\nPhase: {current_phase}\nTrack: {track_title}\nTimestamp: {iso_timestamp}"}}]},

  Source Agent: {rich_text: [{text: {content: "Claude MM1 Agent"}}]}

}


| Error Type | Severity | Action |

|------------|----------|--------|

| Notion API 401/403 | CRITICAL | STOP, create Agent-Task |

| Notion API 404 | CRITICAL | STOP, create Agent-Task |

| yt-dlp rate limit | HIGH | Retry 3x with backoff, then Agent-Task |

| Download failure | MEDIUM | Log, mark Downloaded=false, continue |

| External volume unmounted | MEDIUM | Skip that volume, log warning |

Completion Gates
**EXPECTED RESPONSE:** Check all gates and report final status. Report format: "WORKFLOW COMPLETE: [Success/Partial] - [List of completed items] - [List of incomplete items if Partial]"

**YOU MUST:** All must pass for "Success". Check each gate and report:

- [ ] Primary track source identified
- [ ] Sync-aware fallback executed if needed
- [ ] Deduplication completed (Notion + filesystem)
- [ ] Cross-platform URLs resolved
- [ ] Track exists in Music Tracks with all URLs
- [ ] All artists linked
- [ ] Track downloaded
- [ ] Downloaded=true, file path recorded
- [ ] Cross-platform bonus sync attempted
- [ ] At least ONE new/updated track synced

**YOU MUST:** Report: "WORKFLOW COMPLETE: Success" if ALL pass. Otherwise "WORKFLOW COMPLETE: Partial - [incomplete items]". DO NOT ask if workflow is complete - check gates and report.

<details> <summary>📋 Document Metadata</summary>
Doc Key: DOC_PROMPT_MUSIC_SYNC_V2

Version: 2.4

Doc Level: L2

Category: Pipelines

Primary Owner: Claude MM1 Agent

Last Updated: 2026-01-08

Changelog
v2.4 (2026-01-08)

MAJOR: Made prompt MORE TARGETED AND CLEAR on expected agent response
- Added explicit "EXPECTED RESPONSE" sections for every phase and sub-phase
- Added "YOU MUST" directives throughout to eliminate ambiguity
- Added explicit "DO NOT" statements to prevent questions/clarifications
- Added mandatory execution rules at top of document
- Added explicit response format requirements
- Added progress reporting format for each phase
- Removed all ambiguity that could lead to questions
- Made every step explicitly directive with no optional interpretation

v2.3 (2026-01-08)

Fixed Spotify API references - replaced get_spotify_client() with SpotifyAPI/SpotifyOAuthManager
Fixed saved tracks method - use "Liked Songs" playlist approach with proper error handling
Added fallback chain timeout/retry rules (max 2 attempts, 30s timeout per priority)
Added Spotify track YouTube search documentation in Phase 0.1
Added comprehensive file creation verification in Phase 4.4 (M4A, AIFF, WAV paths)
Added explicit verification commands and file path checks

v2.2 (2025-12-18)

Restructured as execution prompt (not reference doc)

Moved metadata to collapsed footer

Added immediate execution header

Converted all phases to imperative voice

v2.1 (2025-12-18)

Added workspace-aligned headers, env vars, error handling

v2.0 (2025-12-19)

Added sync-aware fallback chain, mandatory Phase 6

v1.0 (2025-12-17)

Initial universal workflow

