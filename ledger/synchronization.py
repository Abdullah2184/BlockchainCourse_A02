import requests


def synchronize(blockchain) -> dict:
    reports = []
    changed = False
    for node in blockchain.peer_nodes:
        try:
            response = requests.get(f"http://{node}/state", timeout=3)
        except requests.RequestException as error:
            reports.append({"node": node, "status": "error", "message": str(error)})
            continue
        if response.status_code != 200:
            reports.append({"node": node, "status": "rejected", "code": response.status_code})
            continue
        try:
            state_updated = blockchain.merge_state(response.json())
        except (ValueError, requests.RequestException) as error:
            reports.append({"node": node, "status": "rejected", "message": str(error)})
            continue
        changed = changed or state_updated
        reports.append({"node": node, "status": "synchronized", "state_updated": state_updated})
    return {"changed": changed, "peers": reports}
