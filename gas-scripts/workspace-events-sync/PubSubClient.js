/**
 * PubSubClient
 * Pull/ack/nack via Pub/Sub REST API using the script's OAuth token.
 */

var PubSubClient = (function () {
  function PubSubClient(cfg) {
    this.cfg = cfg;
    this.baseUrl = "https://pubsub.googleapis.com/v1/";
  }

  PubSubClient.prototype._request_ = function (method, path, body) {
    var url = this.baseUrl + path.replace(/^\//, "");
    var token = ScriptApp.getOAuthToken();
    var params = {
      method: method,
      muteHttpExceptions: true,
      headers: {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json"
      }
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
    throw new Error("Pub/Sub API error " + code + ": " + text);
  };

  PubSubClient.prototype.pull_ = function (maxMessages) {
    var body = { maxMessages: maxMessages || this.cfg.maxMessages || 10 };
    var res = this._request_("POST", this.cfg.subscriptionPath + ":pull", body);
    var received = (res && res.receivedMessages) ? res.receivedMessages : [];
    var messages = received.map(function (rm) {
      return {
        ackId: rm.ackId,
        message: rm.message || {}
      };
    });
    return { messages: messages };
  };

  PubSubClient.prototype.ack_ = function (ackIds) {
    if (!ackIds || !ackIds.length) return;
    this._request_("POST", this.cfg.subscriptionPath + ":acknowledge", { ackIds: ackIds });
  };

  PubSubClient.prototype.nackForRetry_ = function (ackIds, ackDeadlineSeconds) {
    if (!ackIds || !ackIds.length) return;
    this._request_("POST", this.cfg.subscriptionPath + ":modifyAckDeadline", {
      ackIds: ackIds,
      ackDeadlineSeconds: ackDeadlineSeconds || this.cfg.ackDeadlineSeconds || 60
    });
  };

  return PubSubClient;
})();

