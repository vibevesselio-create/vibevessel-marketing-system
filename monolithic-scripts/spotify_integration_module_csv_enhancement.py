"""
Spotify Integration Module CSV Enhancement
==========================================

This file contains enhancements to add CSV backup fallback to spotify_integration_module.py.
Apply these changes to integrate CSV backup as documented backup data source.

Author: Cursor MM1 Agent • 2026-01-13
"""

# Add this import at the top of spotify_integration_module.py (after existing imports):
"""
try:
    from spotify_csv_backup import SpotifyCSVBackup, get_spotify_csv_backup
    CSV_BACKUP_AVAILABLE = True
except ImportError:
    CSV_BACKUP_AVAILABLE = False
    logger.warning("Spotify CSV backup module not available")
"""

# Modify SpotifyAPI.__init__ to add CSV backup instance:
"""
def __init__(self, oauth_manager: Optional[SpotifyOAuthManager] = None, market: Optional[str] = None):
    self.oauth_manager = oauth_manager or SpotifyOAuthManager()
    self.base_url = "https://api.spotify.com/v1"
    self.market = market or os.getenv("SPOTIFY_MARKET", "US")
    
    # CSV backup integration
    self.use_csv_fallback = os.getenv("SPOTIFY_CSV_BACKUP_ENABLED", "true").lower() == "true"
    self.csv_fallback_on_rate_limit = os.getenv("SPOTIFY_CSV_FALLBACK_ON_RATE_LIMIT", "true").lower() == "true"
    self.csv_fallback_on_error = os.getenv("SPOTIFY_CSV_FALLBACK_ON_ERROR", "true").lower() == "true"
    
    if CSV_BACKUP_AVAILABLE and self.use_csv_fallback:
        try:
            self.csv_backup = get_spotify_csv_backup()
            logger.info("CSV backup enabled for Spotify API fallback")
        except Exception as e:
            logger.warning(f"Failed to initialize CSV backup: {e}")
            self.csv_backup = None
    else:
        self.csv_backup = None
"""

# Modify _make_request to add CSV fallback on rate limit/error:
"""
def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None, 
                  use_csv_fallback: bool = True) -> Optional[Dict]:
    \"\"\"Make API request with error handling, retry logic, and CSV fallback.\"\"\"
    url = f"{self.base_url}{endpoint}"
    headers = self._get_headers()
    
    for attempt in range(3):
        try:
            response = requests.request(
                method, url, headers=headers, params=params, json=data, timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                # Rate limited - try CSV fallback if enabled
                if self.csv_fallback_on_rate_limit and self.csv_backup and use_csv_fallback:
                    logger.info(f"Rate limited on {endpoint}, attempting CSV fallback")
                    csv_result = self._try_csv_fallback(endpoint, params)
                    if csv_result:
                        logger.info("CSV fallback successful")
                        return csv_result
                
                retry_after = int(response.headers.get('Retry-After', 1))
                logger.warning(f"Rate limited, waiting {retry_after} seconds")
                time.sleep(retry_after)
                continue
            elif response.status_code == 401:
                # Token expired, try to refresh
                logger.warning("Token expired, attempting refresh")
                if self.oauth_manager._refresh_token():
                    headers = self._get_headers()
                    continue
                else:
                    logger.error("Failed to refresh token")
                    # Try CSV fallback if enabled
                    if self.csv_fallback_on_error and self.csv_backup and use_csv_fallback:
                        logger.info(f"Token refresh failed, attempting CSV fallback for {endpoint}")
                        return self._try_csv_fallback(endpoint, params)
                    return None
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                # Try CSV fallback on error if enabled
                if self.csv_fallback_on_error and self.csv_backup and use_csv_fallback:
                    logger.info(f"API error, attempting CSV fallback for {endpoint}")
                    return self._try_csv_fallback(endpoint, params)
                return None
                
        except Exception as e:
            logger.error(f"Request error (attempt {attempt + 1}): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            # Try CSV fallback on exception if enabled
            if self.csv_fallback_on_error and self.csv_backup and use_csv_fallback:
                logger.info(f"Request exception, attempting CSV fallback for {endpoint}")
                return self._try_csv_fallback(endpoint, params)
            return None
            
    return None

def _try_csv_fallback(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
    \"\"\"Attempt to get data from CSV backup based on endpoint.\"\"\"
    if not self.csv_backup:
        return None
    
    try:
        # Parse endpoint to determine what to fetch
        if endpoint.startswith("/tracks/"):
            # Extract track ID from endpoint
            track_id = endpoint.replace("/tracks/", "").split("?")[0]
            track = self.csv_backup.get_track_by_id(track_id)
            if track:
                # Convert CSV track format to API response format
                return self._csv_track_to_api_format(track)
        
        elif endpoint.startswith("/audio-features/"):
            # Extract track ID
            track_id = endpoint.replace("/audio-features/", "").split("?")[0]
            audio_features = self.csv_backup.get_audio_features(track_id)
            if audio_features:
                return audio_features
        
        elif endpoint.startswith("/playlists/") and "/tracks" in endpoint:
            # Playlist tracks - would need playlist name mapping
            # This is more complex and may not be fully supported
            logger.debug("CSV fallback for playlist tracks not fully implemented")
            return None
        
        elif endpoint == "/me/playlists":
            # User playlists - return playlist names from CSV files
            playlist_names = self.csv_backup.get_playlist_names()
            # Convert to API format (simplified)
            playlists = []
            for name in playlist_names:
                playlists.append({
                    "id": "",  # CSV doesn't have playlist IDs
                    "name": name,
                    "external_urls": {}
                })
            return {"items": playlists}
        
    except Exception as e:
        logger.error(f"CSV fallback error: {e}")
        return None
    
    return None

def _csv_track_to_api_format(self, csv_track: Dict[str, Any]) -> Dict[str, Any]:
    \"\"\"Convert CSV track format to Spotify API response format.\"\"\"
    # CSV track already matches API format (from spotify_csv_backup.py)
    # Just return as-is, but remove CSV-specific metadata
    api_track = csv_track.copy()
    api_track.pop("_csv_metadata", None)
    api_track.pop("audio_features", None)  # Audio features are separate endpoint
    return api_track
"""

# Modify get_track_info to add CSV fallback parameter:
"""
def get_track_info(self, track_id: str, use_csv_fallback: bool = True) -> Optional[Dict[str, Any]]:
    \"\"\"Get detailed track information with CSV fallback support.\"\"\"
    # Try API first
    result = self._make_request("GET", f"/tracks/{track_id}", use_csv_fallback=use_csv_fallback)
    if result:
        return result
    
    # If API failed and CSV fallback wasn't already tried, try it now
    if use_csv_fallback and self.csv_backup:
        logger.info(f"API failed for track {track_id}, trying CSV backup")
        track = self.csv_backup.get_track_by_id(track_id)
        if track:
            return self._csv_track_to_api_format(track)
    
    return None
"""

# Modify get_audio_features to add CSV fallback:
"""
def get_audio_features(self, track_id: str, use_csv_fallback: bool = True) -> Optional[Dict[str, Any]]:
    \"\"\"Get audio features for a track with CSV fallback support.\"\"\"
    # Try API first
    result = self._make_request("GET", f"/audio-features/{track_id}", use_csv_fallback=use_csv_fallback)
    if result:
        return result
    
    # If API failed and CSV fallback wasn't already tried, try it now
    if use_csv_fallback and self.csv_backup:
        logger.info(f"API failed for audio features {track_id}, trying CSV backup")
        return self.csv_backup.get_audio_features(track_id)
    
    return None
"""

# Modify get_playlist_tracks to add CSV fallback:
"""
def get_playlist_tracks(self, playlist_id: str, limit: int = 100, 
                       playlist_name: Optional[str] = None,
                       use_csv_fallback: bool = True) -> List[Dict[str, Any]]:
    \"\"\"Get tracks from a playlist with CSV fallback support.
    
    Args:
        playlist_id: Spotify playlist ID
        limit: Maximum number of tracks to return
        playlist_name: Optional playlist name for CSV fallback (if playlist_id not in CSV)
        use_csv_fallback: Enable CSV fallback
    \"\"\"
    tracks = []
    offset = 0
    
    while True:
        params = {
            "limit": min(limit, 100),
            "offset": offset,
            "market": self.market
        }
        
        data = self._make_request("GET", f"/playlists/{playlist_id}/tracks", 
                                  params=params, use_csv_fallback=use_csv_fallback)
        if not data:
            # Try CSV fallback if API failed
            if use_csv_fallback and self.csv_backup and playlist_name:
                logger.info(f"API failed for playlist {playlist_name}, trying CSV backup")
                csv_tracks = self.csv_backup.get_playlist_tracks(playlist_name)
                if csv_tracks:
                    # Convert CSV tracks to API format
                    return [self._csv_track_to_api_format(t) for t in csv_tracks[:limit]]
            break
            
        items = data.get("items", [])
        if not items:
            break
            
        tracks.extend(items)
        offset += len(items)
        
        if len(items) < params["limit"]:
            break
    
    return tracks
"""

# Modify get_user_playlists to add CSV fallback:
"""
def get_user_playlists(self, limit: int = 50, offset: int = 0, 
                      use_csv_fallback: bool = True) -> List[Dict[str, Any]]:
    \"\"\"Get user's playlists with CSV fallback support.\"\"\"
    params = {"limit": limit, "offset": offset, "market": self.market}
    data = self._make_request("GET", "/me/playlists", params=params, 
                              use_csv_fallback=use_csv_fallback)
    
    if data:
        return data.get("items", [])
    
    # Try CSV fallback if API failed
    if use_csv_fallback and self.csv_backup:
        logger.info("API failed for user playlists, trying CSV backup")
        playlist_names = self.csv_backup.get_playlist_names()
        playlists = []
        for name in playlist_names[offset:offset+limit]:
            playlists.append({
                "id": "",  # CSV doesn't have playlist IDs
                "name": name,
                "external_urls": {},
                "tracks": {"total": 0}  # Would need to count tracks in CSV
            })
        return playlists
    
    return []
"""

# Modify search_tracks to add CSV fallback:
"""
def search_tracks(self, query: str, limit: int = 20, use_csv_fallback: bool = True) -> List[Dict[str, Any]]:
    \"\"\"Search for tracks with CSV fallback support.\"\"\"
    params = {
        "q": query,
        "type": "track",
        "limit": limit,
        "market": self.market
    }
    data = self._make_request("GET", "/search", params=params, use_csv_fallback=use_csv_fallback)
    
    if data:
        return data.get("tracks", {}).get("items", [])
    
    # Try CSV fallback if API failed
    if use_csv_fallback and self.csv_backup:
        logger.info(f"API failed for search '{query}', trying CSV backup")
        csv_tracks = self.csv_backup.search_tracks(query)
        if csv_tracks:
            # Convert and limit results
            return [self._csv_track_to_api_format(t) for t in csv_tracks[:limit]]
    
    return []
"""
