/**
 * DriveHandler
 * Routes Drive file events to Notion upsert.
 */

var DriveHandler = (function () {
  function DriveHandler(cfg, notionSync) {
    this.cfg = cfg;
    this.notion = notionSync;
  }

  DriveHandler.prototype._extractFileId_ = function (subject) {
    if (!subject) return "";
    var s = String(subject);
    if (s.indexOf("/files/") >= 0) return s.split("/files/").pop();
    if (s.indexOf("files") >= 0) {
      var parts = s.split("/");
      var idx = parts.indexOf("files");
      if (idx >= 0 && parts[idx + 1]) return parts[idx + 1];
    }
    return s.replace(/^\/\//, "");
  };

  DriveHandler.prototype._shouldIgnoreDriveFileByName_ = function (fileName) {
    if (!fileName) return false;
    for (var i = 0; i < this.cfg.ignoreNamePrefixes.length; i++) {
      if (fileName.indexOf(this.cfg.ignoreNamePrefixes[i]) === 0) return true;
    }
    return false;
  };

  DriveHandler.prototype._mapDriveMetadataToNotionProps_ = function (file, ce) {
    var name = file.getName();
    var id = file.getId();
    var url = file.getUrl();
    var lastUpdated = file.getLastUpdated();
    var created = file.getDateCreated();

    var props = {
      "Name": { title: [{ text: { content: name || "Untitled" } }] },
      "File ID": { rich_text: [{ text: { content: id } }] },
      "URL": { url: url }
    };
    if (lastUpdated) props["Last Modified"] = { date: { start: new Date(lastUpdated).toISOString() } };
    if (created) props["Created"] = { date: { start: new Date(created).toISOString() } };

    // Try to include a lightweight MIME hint (Apps Script doesn't expose MIME for all types reliably)
    try {
      props["MIME Type"] = { rich_text: [{ text: { content: String(file.getMimeType ? file.getMimeType() : "") } }] };
    } catch (_) {}

    return props;
  };

  DriveHandler.prototype._resolveTargetDatabaseId_ = function (file, ce) {
    // Minimal routing: allow explicit override; otherwise pick first active from Workspace-Databases via user configuration.
    // Users can set WORKSPACE_EVENTS_TARGET_DB_ID if they want to bypass routing.
    var scriptProps = PropertiesService.getScriptProperties();
    var explicit = scriptProps.getProperty("WORKSPACE_EVENTS_TARGET_DB_ID");
    if (explicit) return String(explicit).replace(/-/g, "");

    // Best-effort: try to discover Workspace-Databases and use first "Active" row's Database URL.
    try {
      var workspaceDbId = this.notion.discoverDatabaseByName_("Workspace-Databases");
      if (!workspaceDbId) return null;
      var res = this.notion._request_("POST", "databases/" + workspaceDbId + "/query", {
        filter: {
          and: [
            { property: "Type", select: { equals: "Database" } },
            { property: "Status", select: { equals: "Active" } }
          ]
        },
        page_size: 5
      });
      var rows = res.results || [];
      if (!rows.length) return null;
      var first = rows[0];
      var props = first.properties || {};
      var urlProp = props["Database URL"];
      var url = urlProp && urlProp.url ? urlProp.url : "";
      if (!url) return null;
      var dbId = url.split("/").pop().split("?")[0];
      return String(dbId).replace(/-/g, "");
    } catch (e) {
      return null;
    }
  };

  DriveHandler.prototype.handle_ = function (ce) {
    try {
      // Only handle Drive file events
      if (!ce || !ce.type || ce.type.indexOf("google.workspace.drive.file.") !== 0) {
        return { ok: true, skipped: true, reason: "Non-drive event" };
      }

      var fileId = this._extractFileId_(ce.subject);
      if (!fileId) return { ok: false, error: "Missing fileId from subject" };

      var file = DriveApp.getFileById(fileId);
      var name = file.getName();

      // Loop-guard: ignore Drive artifacts that create circular flows
      if (this._shouldIgnoreDriveFileByName_(name)) {
        return { ok: true, skipped: true, reason: "Ignored by name prefix loop-guard" };
      }

      var targetDbId = this._resolveTargetDatabaseId_(file, ce);
      if (!targetDbId) return { ok: false, error: "Could not resolve target Notion database" };

      var notionProps = this._mapDriveMetadataToNotionProps_(file, ce);
      var upsert = this.notion.upsertDriveFile_(targetDbId, fileId, notionProps, ce);
      if (!upsert.ok) return { ok: false, error: upsert.error || "Notion upsert failed" };

      return { ok: true, upsert: upsert };
    } catch (e) {
      return { ok: false, error: String(e && e.message ? e.message : e) };
    }
  };

  return DriveHandler;
})();

