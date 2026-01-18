/**
 * EventParser
 * Parses CloudEvents carried via Pub/Sub message attributes + message.data.
 */

var EventParser = (function () {
  function _base64ToString_(b64) {
    if (!b64) return "";
    var bytes = Utilities.base64Decode(String(b64));
    return Utilities.newBlob(bytes).getDataAsString("UTF-8");
  }

  function _safeJsonParse_(s) {
    try {
      return JSON.parse(s);
    } catch (_) {
      return s;
    }
  }

  function parseFromPubSubMessage_(wrapped) {
    // wrapped: { ackId, message: { data, attributes, messageId, publishTime } }
    var msg = wrapped && wrapped.message ? wrapped.message : {};
    var attrs = msg.attributes || {};

    // CloudEvent headers are usually forwarded into attributes as ce-*
    var id = attrs["ce-id"] || attrs["ce_id"] || attrs["ceId"] || msg.messageId || "";
    var type = attrs["ce-type"] || attrs["ce_type"] || "";
    var source = attrs["ce-source"] || attrs["ce_source"] || "";
    var subject = attrs["ce-subject"] || attrs["ce_subject"] || "";
    var time = attrs["ce-time"] || attrs["ce_time"] || msg.publishTime || "";

    var dataStr = _base64ToString_(msg.data);
    var data = _safeJsonParse_(dataStr);

    return {
      id: id || "",
      type: type || "",
      source: source || "",
      subject: subject || "",
      time: time || "",
      data: data,
      raw: {
        attributes: attrs,
        messageId: msg.messageId || "",
        publishTime: msg.publishTime || ""
      }
    };
  }

  function makeIdempotencyKey_(ce) {
    var s = String(ce.id || "") + ":" + String(ce.subject || "") + ":" + String(ce.type || "");
    var digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, s, Utilities.Charset.UTF_8);
    return digest.map(function (b) {
      var v = (b < 0) ? b + 256 : b;
      var hex = v.toString(16);
      return hex.length === 1 ? "0" + hex : hex;
    }).join("");
  }

  return {
    parseFromPubSubMessage_: parseFromPubSubMessage_,
    makeIdempotencyKey_: makeIdempotencyKey_
  };
})();

