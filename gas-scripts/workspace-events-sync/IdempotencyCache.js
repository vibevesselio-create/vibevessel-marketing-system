/**
 * IdempotencyCache
 * Short-term dedupe to reduce duplicate processing (Pub/Sub at-least-once delivery).
 */

var IdempotencyCache = (function () {
  function isDuplicate_(key, ttlSeconds) {
    if (!key) return false;
    var ttl = ttlSeconds || 900;
    try {
      var cache = CacheService.getScriptCache();
      var existing = cache.get(key);
      if (existing) return true;
      cache.put(key, "1", ttl);
      return false;
    } catch (e) {
      // Fallback: use script properties with simple timestamp key (best-effort)
      try {
        var props = PropertiesService.getScriptProperties();
        var tsKey = "IDEMPOTENCY_" + key;
        var now = Date.now();
        var prev = props.getProperty(tsKey);
        if (prev) {
          var prevMs = parseInt(prev, 10);
          if (!isNaN(prevMs) && (now - prevMs) < (ttl * 1000)) {
            return true;
          }
        }
        props.setProperty(tsKey, String(now));
        return false;
      } catch (_) {
        return false;
      }
    }
  }

  return {
    isDuplicate_: isDuplicate_
  };
})();

