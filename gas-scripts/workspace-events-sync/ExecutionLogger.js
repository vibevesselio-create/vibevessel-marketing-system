/**
 * ExecutionLogger
 * Best-effort Notion Execution-Logs logging for GAS workflow.
 */

var ExecutionLogger = (function () {
  function ExecutionLogger(cfg) {
    this.cfg = cfg;
    this.notion = new NotionSync(cfg);
  }

  ExecutionLogger.prototype.beginRun_ = function (meta) {
    var runId = "gas_run_" + new Date().toISOString().replace(/[:.]/g, "").replace("Z", "Z");
    try {
      this._execPageId = this.notion.createExecutionLog_(runId, {
        status: "Running",
        started_at: new Date().toISOString(),
        meta: meta || {}
      });
    } catch (_) {}
    return runId;
  };

  ExecutionLogger.prototype.logEvent_ = function (runId, ce, outcome) {
    // Best-effort: keep event logs lightweight in Execution Result JSON (avoid huge volumes).
    // We do not create one Notion page per event here to avoid rate-limit loops.
    return;
  };

  ExecutionLogger.prototype.logRawError_ = function (runId, message, err) {
    try {
      this.notion.createExecutionLog_(runId, {
        status: "Error",
        message: message,
        error: String(err && err.message ? err.message : err),
        at: new Date().toISOString()
      });
    } catch (_) {}
  };

  ExecutionLogger.prototype.endRun_ = function (runId, summary) {
    try {
      this.notion.createExecutionLog_(runId, {
        status: summary && summary.status ? summary.status : "Complete",
        summary: summary || {},
        ended_at: new Date().toISOString()
      });
    } catch (_) {}
  };

  return ExecutionLogger;
})();

