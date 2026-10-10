import requests
from flask import jsonify, request


def json_object():
    values = request.get_json(silent=True)
    return values if isinstance(values, dict) else None


def broadcast(blockchain, path, payload):
    reports = []
    for peer in blockchain.peer_nodes:
        try:
            response = requests.post(f"http://{peer}{path}", json=payload, timeout=3)
        except requests.RequestException as error:
            reports.append({
                "resource": path,
                "node": peer,
                "status": "error",
                "message": str(error),
            })
            continue

        try:
            message = response.json().get("message")
        except (ValueError, AttributeError):
            message = response.text[:200]
        reports.append({
            "resource": path,
            "node": peer,
            "status": "accepted" if 200 <= response.status_code < 300 else "rejected",
            "code": response.status_code,
            "message": message,
        })
    if any(report["status"] in {"rejected", "error"} for report in reports):
        reports.append({
            "resource": "synchronization",
            "status": "attempted",
            "report": blockchain.synchronize(),
        })
    return reports


def rejected_payload(message, blockchain, status=409):
    sync = blockchain.synchronize()
    return jsonify({"message": message, "sync_required": True, "sync": sync}), status
