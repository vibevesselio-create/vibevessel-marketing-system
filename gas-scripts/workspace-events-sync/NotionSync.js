/**
 * NotionSync
 * Minimal Notion API client (search + upsert + execution log).
 *
 * This is intentionally conservative: it will skip actions when required DBs
 * cannot be discovered to avoid breaking the workflow.
 */

var NotionSync = (function () {
  function NotionSync(cfg) {
    this.cfg = cfg;
    this.baseUrl = "https://api.notion.com/v1/";
    this._dbIdCache = {}; // name -> id (no dashes)
    this._dbSchemaCache = {}; // dbId -> properties dict
  }

  NotionSync.prototype._headers_ = function () {
    return {
      Authorization: "Bearer " + this.cfg.notionToken,
      "Notion-Version": this.cfg.notionVersion,
      "Content-Type": "application/json"
    };
  };

  NotionSync.prototype._request_ = function (method, path, body) {
    var url = this.baseUrl + path.replace(/^\//, "");
    var params = {
      method: method,
      muteHttpExceptions: true,
      headers: this._headers_()
    };
    if (body !== undefined) {
      params.payload = JSON.stringify(body);
    }
    var resp = UrlFetchApp.fetch(url, params);
    var code = resp.getResponseCode();
    var text = resp.getContentText();
    if (code >= 200 && code < 300) {
      return text ? JSON.parse(text) : {};
    }
    throw new Error("Notion API error " + code + ": " + text);
  };

  NotionSync.prototype.discoverDatabaseByName_ = function (dbName) {
    if (!dbName) return null;
    if (this._dbIdCache[dbName]) return this._dbIdCache[dbName];

    var scriptProps = PropertiesService.getScriptProperties();
    var cacheKey = "DB_CACHE_" + dbName.replace(/[^a-zA-Z0-9]/g, "_").toUpperCase();
    var cached = scriptProps.getProperty(cacheKey);
    if (cached) {
      this._dbIdCache[dbName] = cached;
      return cached;
    }

    var cursor = null;
    for (var i = 0; i < 10; i++) {
      var body = {
        query: dbName,
        page_size: 100,
        filter: { property: "object", value: "data_source" }
      };
      if (cursor) body.start_cursor = cursor;
      var res = this._request_("POST", "search", body);
      var results = res.results || [];
      for (var r = 0; r < results.length; r++) {
        var ds = results[r];
        var title = "";
        if (ds.title && ds.title.length) title = ds.title[0].plain_text || "";
        if (!title && ds.name) title = ds.name;
        if (title && title.toLowerCase() === dbName.toLowerCase()) {
          var found = (ds.id || "").replace(/-/g, "");
          if (found) {
            scriptProps.setProperty(cacheKey, found);
            this._dbIdCache[dbName] = found;
            return found;
          }
        }
      }
      if (!res.has_more) break;
      cursor = res.next_cursor;
    }
    return null;
  };

  NotionSync.prototype._ensureLoopGuardProperties_ = function (databaseId) {
    if (!databaseId) return false;
    try {
      var db = this._request_("GET", "databases/" + databaseId);
      var props = db.properties || {};
      var toAdd = {};
      if (!props[this.cfg.serenAutomationSourceProperty]) toAdd[this.cfg.serenAutomationSourceProperty] = { rich_text: {} };
      if (!props[this.cfg.serenAutomationEventIdProperty]) toAdd[this.cfg.serenAutomationEventIdProperty] = { rich_text: {} };
      if (!props[this.cfg.serenAutomationNodeIdProperty]) toAdd[this.cfg.serenAutomationNodeIdProperty] = { rich_text: {} };
      if (Object.keys(toAdd).length) {
        this._request_("PATCH", "databases/" + databaseId, { properties: toAdd });
      }
      return true;
    } catch (e) {
      // Not fatal; we can still upsert without loop-guard tags.
      return false;
    }
  };

  NotionSync.prototype._applyLoopGuardProps_ = function (properties, ce) {
    var p = properties || {};
    try {
      p[this.cfg.serenAutomationSourceProperty] = {
        rich_text: [{ text: { content: this.cfg.automationSourceValue } }]
      };
      p[this.cfg.serenAutomationNodeIdProperty] = {
        rich_text: [{ text: { content: this.cfg.nodeId } }]
      };
      if (ce && ce.id) {
        p[this.cfg.serenAutomationEventIdProperty] = {
          rich_text: [{ text: { content: String(ce.id) } }]
        };
      }
    } catch (_) {}
    return p;
  };

  NotionSync.prototype.upsertDriveFile_ = function (targetDbId, driveFileId, driveProps, ce) {
    if (!targetDbId) return { ok: false, error: "No target DB" };
    if (!driveFileId) return { ok: false, error: "No driveFileId" };

    // Ensure loop-guard properties exist so Notion webhook server can ignore these edits.
    var canTag = this._ensureLoopGuardProperties_(targetDbId);

    // Find existing page by "File ID" rich_text equals driveFileId (best-effort).
    var pageId = null;
    try {
      var q = {
        filter: {
          property: "File ID",
          rich_text: { equals: driveFileId }
        },
        page_size: 1
      };
      var res = this._request_("POST", "databases/" + targetDbId + "/query", q);
      if (res.results && res.results.length) pageId = res.results[0].id;
    } catch (e) {
      // If schema doesn't have "File ID", skip upsert to avoid creating bad pages.
      return { ok: false, error: "Target DB missing File ID property (cannot upsert safely)" };
    }

    var properties = JSON.parse(JSON.stringify(driveProps || {}));
    if (canTag) properties = this._applyLoopGuardProps_(properties, ce);

    try {
      if (pageId) {
        this._request_("PATCH", "pages/" + pageId, { properties: properties });
        return { ok: true, pageId: pageId, action: "updated" };
      }
      var created = this._request_("POST", "pages", {
        parent: { database_id: targetDbId },
        properties: properties
      });
      return { ok: true, pageId: created.id, action: "created" };
    } catch (e2) {
      return { ok: false, error: String(e2 && e2.message ? e2.message : e2) };
    }
  };

  NotionSync.prototype.createExecutionLog_ = function (runId, payload) {
    // Best-effort: discover Execution-Logs by name and create a log page.
    try {
      var execDbId = this.discoverDatabaseByName_("Execution-Logs");
      if (!execDbId) return null;

      var canTag = this._ensureLoopGuardProperties_(execDbId);
      var properties = {
        "Script Name": { title: [{ text: { content: "GAS Workspace Events Sync" } }] },
        "Execution Result": { rich_text: [{ text: { content: JSON.stringify(payload || {}) } }] },
        "Last Run": { date: { start: new Date().toISOString() } }
      };
      if (canTag) properties = this._applyLoopGuardProps_(properties, null);

      var created = this._request_("POST", "pages", {
        parent: { database_id: execDbId },
        properties: properties
      });
      return created && created.id ? created.id : null;
    } catch (_) {
      return null;
    }
  };

  return NotionSync;
})();

