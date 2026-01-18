/**
 * Google Workspace Events → Pub/Sub → Notion + CSV (Apps Script)
 * =============================================================
 *
 * Complementary Apps Script implementation of the Python Workspace Events workflow:
 * - Pull Workspace Events messages from Pub/Sub (pull subscription)
 * - Parse CloudEvents (ce- attributes + JSON payload)
 * - Idempotency (short-term) to reduce duplicates
 * - Route Drive file events to Notion (upsert file metadata into a target DB)
 * - Export each processed event into CSV files on Google Drive
 * - Log each run/event to Notion Execution-Logs
 *
 * This folder is designed for deployment via Google Apps Script API (no clasp required),
 * but remains compatible with clasp-style project layout.
 *
 * Required Script Properties:
 * - NOTION_TOKEN
 * - LOG_ENV (DEV|PROD) [optional]
 * - GCP_PROJECT_ID
 * - PUBSUB_SUBSCRIPTION_NAME (e.g. "seren-media-sync") OR PUBSUB_SUBSCRIPTION_PATH (full)
 * - WORKSPACE_EVENTS_CSV_FOLDER_ID (Drive folder id for CSV exports)
 *
 * Optional Script Properties:
 * - NOTION_VERSION (default: 2025-09-03)
 * - NOTION_WORKSPACE_DATABASES_NAME (default: "Workspace-Databases")
 * - NOTION_EXECUTION_LOGS_NAME (default: "Execution-Logs")
 * - WORKSPACE_EVENTS_MAX_MESSAGES (default: 10)
 * - WORKSPACE_EVENTS_ACK_DEADLINE_SECONDS (default: 60)
 * - WORKSPACE_EVENTS_NODE_ID (default: "gas")
 */

function workspaceEvents_runOnce() {
  const cfg = WorkspaceEventsConfig.getConfig_();
  const exec = new ExecutionLogger(cfg);
  const startedAt = new Date();

  const runId = exec.beginRun_({
    scriptName: "GAS Workspace Events Sync",
    nodeId: cfg.nodeId,
    meta: {
      projectId: cfg.projectId,
      subscriptionPath: cfg.subscriptionPath,
      maxMessages: cfg.maxMessages
    }
  });

  let pulled = 0;
  let acked = 0;
  let failed = 0;

  try {
    const pubsub = new PubSubClient(cfg);
    const pullResult = pubsub.pull_(cfg.maxMessages);
    pulled = pullResult.messages.length;

    if (!pullResult.messages.length) {
      exec.endRun_(runId, {
        status: "Complete",
        summary: "No messages available",
        metrics: { pulled, acked, failed, durationMs: new Date() - startedAt }
      });
      return { ok: true, pulled, acked, failed };
    }

    const csv = new CSVExporter(cfg);
    const notion = new NotionSync(cfg);
    const drive = new DriveHandler(cfg, notion);

    const ackIdsToAck = [];
    const ackIdsToNack = [];

    pullResult.messages.forEach(function (m) {
      const ackId = m.ackId;
      try {
        const ce = EventParser.parseFromPubSubMessage_(m);
        const idKey = EventParser.makeIdempotencyKey_(ce);
        if (IdempotencyCache.isDuplicate_(idKey, cfg.idempotencyTtlSeconds)) {
          // Duplicate: still ack, but mark as duplicate.
          csv.appendEvent_(ce, {
            processed: true,
            error: "Duplicate event (idempotency cache hit)"
          });
          exec.logEvent_(runId, ce, { status: "Complete", error: "Duplicate event (idempotency cache hit)" });
          ackIdsToAck.push(ackId);
          return;
        }

        // Route event
        const outcome = drive.handle_(ce);
        csv.appendEvent_(ce, {
          processed: outcome.ok,
          error: outcome.ok ? "" : (outcome.error || "Unknown error")
        });
        exec.logEvent_(runId, ce, { status: outcome.ok ? "Complete" : "Error", error: outcome.error || "" });

        if (outcome.ok) {
          ackIdsToAck.push(ackId);
        } else {
          ackIdsToNack.push(ackId);
          failed++;
        }
      } catch (e) {
        failed++;
        try {
          exec.logRawError_(runId, "Event processing exception", e);
        } catch (_) {}
        ackIdsToNack.push(ackId);
      }
    });

    if (ackIdsToAck.length) {
      pubsub.ack_(ackIdsToAck);
      acked += ackIdsToAck.length;
    }
    if (ackIdsToNack.length) {
      pubsub.nackForRetry_(ackIdsToNack, cfg.ackDeadlineSeconds);
    }

    var csvFileId = null;
    try {
      csvFileId = csv.flush_();
    } catch (e) {
      // Don't fail the run if CSV flush fails.
      csvFileId = null;
    }

    exec.endRun_(runId, {
      status: failed ? "Partial" : "Complete",
      summary: failed ? "Processed with some failures" : "Processed successfully",
      metrics: { pulled, acked, failed, csvFileId: csvFileId, durationMs: new Date() - startedAt }
    });
    return { ok: failed === 0, pulled, acked, failed };
  } catch (e) {
    try {
      exec.endRun_(runId, {
        status: "Error",
        summary: "Fatal error",
        error: String(e && e.message ? e.message : e),
        metrics: { pulled, acked, failed, durationMs: new Date() - startedAt }
      });
    } catch (_) {}
    throw e;
  }
}

/**
 * Creates a time-driven trigger for this workflow.
 * @param {number} minutes Interval minutes (default 5).
 */
function workspaceEvents_installTrigger(minutes) {
  const m = minutes || 5;
  // Remove existing triggers for the same handler to avoid duplicates.
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction && t.getHandlerFunction() === "workspaceEvents_runOnce") {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger("workspaceEvents_runOnce").timeBased().everyMinutes(m).create();
  return { ok: true, everyMinutes: m };
}

function workspaceEvents_uninstallTrigger() {
  let removed = 0;
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction && t.getHandlerFunction() === "workspaceEvents_runOnce") {
      ScriptApp.deleteTrigger(t);
      removed++;
    }
  });
  return { ok: true, removed };
}

