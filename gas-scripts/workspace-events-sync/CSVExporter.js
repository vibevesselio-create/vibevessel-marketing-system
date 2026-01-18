/**
 * CSVExporter
 * Buffers event rows and writes one CSV file per run into a Drive folder.
 */

var CSVExporter = (function () {
  function CSVExporter(cfg) {
    this.cfg = cfg;
    this._lines = [];
    this._fileId = null;
    this._started = false;
    this._runStamp = new Date().toISOString().replace(/[:.]/g, "").replace("Z", "Z");
  }

  CSVExporter.prototype._ensureStarted_ = function () {
    if (this._started) return;
    this._started = true;
    this._lines.push([
      "event_id",
      "event_type",
      "source",
      "subject",
      "timestamp",
      "node_id",
      "processed",
      "error",
      "data_json"
    ].join(","));
  };

  CSVExporter.prototype.appendEvent_ = function (ce, result) {
    this._ensureStarted_();
    var processed = (result && result.processed) ? "true" : "false";
    var err = (result && result.error) ? String(result.error) : "";
    // Escape CSV fields minimally
    function esc(v) {
      var s = String(v === undefined || v === null ? "" : v);
      if (s.indexOf('"') >= 0) s = s.replace(/"/g, '""');
      if (s.indexOf(",") >= 0 || s.indexOf("\n") >= 0 || s.indexOf('"') >= 0) {
        return '"' + s + '"';
      }
      return s;
    }

    var row = [
      esc(ce.id || ""),
      esc(ce.type || ""),
      esc(ce.source || ""),
      esc(ce.subject || ""),
      esc(ce.time || ""),
      esc(this.cfg.nodeId || "gas"),
      esc(processed),
      esc(err),
      esc(JSON.stringify(ce.data === undefined ? null : ce.data))
    ].join(",");
    this._lines.push(row);
  };

  CSVExporter.prototype.flush_ = function () {
    if (!this._started) return null;
    var folder = DriveApp.getFolderById(this.cfg.csvFolderId);
    var filename = "webhook_events_" + (this.cfg.nodeId || "gas") + "_" + this._runStamp + ".csv";
    var content = this._lines.join("\n") + "\n";
    var file = folder.createFile(filename, content, MimeType.CSV);
    this._fileId = file.getId();
    return this._fileId;
  };

  return CSVExporter;
})();

