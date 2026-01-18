/**
 * WorkspaceEventsConfig
 * Central configuration for GAS Workspace Events workflow.
 */

var WorkspaceEventsConfig = (function () {
  function _getScriptProps() {
    return PropertiesService.getScriptProperties();
  }

  function _getInt_(key, fallback) {
    var raw = _getScriptProps().getProperty(key);
    if (raw === null || raw === undefined || raw === "") return fallback;
    var n = parseInt(raw, 10);
    return isNaN(n) ? fallback : n;
  }

  function _getStr_(key, fallback) {
    var v = _getScriptProps().getProperty(key);
    if (v === null || v === undefined || v === "") return fallback;
    return String(v);
  }

  function _require_(key) {
    var v = _getScriptProps().getProperty(key);
    if (!v) throw new Error("Missing required Script Property: " + key);
    return String(v);
  }

  function _computeSubscriptionPath_(projectId, subscriptionName) {
    return "projects/" + projectId + "/subscriptions/" + subscriptionName;
  }

  function getConfig_() {
    var env = _getStr_("LOG_ENV", "DEV");

    var notionToken = _require_("NOTION_TOKEN");
    var projectId = _require_("GCP_PROJECT_ID");

    var subscriptionPath = _getStr_("PUBSUB_SUBSCRIPTION_PATH", "");
    if (!subscriptionPath) {
      var subscriptionName = _require_("PUBSUB_SUBSCRIPTION_NAME");
      subscriptionPath = _computeSubscriptionPath_(projectId, subscriptionName);
    }

    var csvFolderId = _require_("WORKSPACE_EVENTS_CSV_FOLDER_ID");

    // Loop-guard property names (must match Python + webhook server)
    var serenAutomationSourceProperty = _getStr_(
      "SEREN_AUTOMATION_SOURCE_PROPERTY",
      "Seren Automation Source"
    );
    var serenAutomationEventIdProperty = _getStr_(
      "SEREN_AUTOMATION_EVENT_ID_PROPERTY",
      "Seren Automation Event ID"
    );
    var serenAutomationNodeIdProperty = _getStr_(
      "SEREN_AUTOMATION_NODE_ID_PROPERTY",
      "Seren Automation Node"
    );

    // Ignore Drive artifacts that can create loops (Notion webhook CSV logs, our own exports, etc)
    var ignorePrefixesRaw = _getStr_(
      "WORKSPACE_EVENTS_IGNORE_NAME_PREFIXES",
      "webhook_events_,workspace_events_,notion_database_webhooks_"
    );
    var ignoreNamePrefixes = ignorePrefixesRaw
      .split(",")
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return !!s; });

    return {
      env: env,
      notionToken: notionToken,
      notionVersion: _getStr_("NOTION_VERSION", "2025-09-03"),
      projectId: projectId,
      subscriptionPath: subscriptionPath,
      maxMessages: _getInt_("WORKSPACE_EVENTS_MAX_MESSAGES", 10),
      ackDeadlineSeconds: _getInt_("WORKSPACE_EVENTS_ACK_DEADLINE_SECONDS", 60),
      nodeId: _getStr_("WORKSPACE_EVENTS_NODE_ID", "gas"),
      automationSourceValue: _getStr_("WORKSPACE_EVENTS_AUTOMATION_SOURCE_VALUE", "gas_workspace_events"),
      idempotencyTtlSeconds: _getInt_("WORKSPACE_EVENTS_IDEMPOTENCY_TTL_SECONDS", 900),
      csvFolderId: csvFolderId,
      serenAutomationSourceProperty: serenAutomationSourceProperty,
      serenAutomationEventIdProperty: serenAutomationEventIdProperty,
      serenAutomationNodeIdProperty: serenAutomationNodeIdProperty,
      ignoreNamePrefixes: ignoreNamePrefixes
    };
  }

  return {
    getConfig_: getConfig_
  };
})();

