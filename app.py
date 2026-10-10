import hmac
import os

import requests
from flask import Flask, jsonify, request

from blockchain import Blockchain


def _broadcast(blockchain, path, payload):
    reports = []
    for peer in blockchain.peer_nodes:
        try:
            response = requests.post(f"http://{peer}{path}", json=payload, timeout=3)
        except requests.RequestException as error:
            reports.append({"node": peer, "status": "error", "message": str(error)})
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
    if any(report["status"] == "rejected" for report in reports):
        reports.append({
            "resource": "synchronization",
            "status": "attempted",
            "report": blockchain.synchronize(),
        })
    return reports


def _json_object():
    values = request.get_json(silent=True)
    return values if isinstance(values, dict) else None


def create_app(blockchain_instance: Blockchain) -> Flask:
    app = Flask(__name__)
    chain = blockchain_instance

    @app.route("/transaction", methods=["POST"])
    def create_transaction():
        values = _json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        required = ("sender_id", "recipient_id", "amount")
        if not all(key in values for key in required):
            return jsonify({"message": "sender_id, recipient_id, and amount are required"}), 400
        try:
            transaction = chain.new_transaction(
                values["sender_id"], values["recipient_id"], values["amount"]
            )
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        broadcast = _broadcast(chain, "/transaction/broadcast", transaction)
        return jsonify({
            "message": "Transaction added",
            "transaction": transaction,
            "broadcast": broadcast,
        }), 201

    @app.route("/transaction/broadcast", methods=["POST"])
    def broadcast_transaction():
        transaction = request.get_json(silent=True)
        if not isinstance(transaction, dict):
            return jsonify({"message": "A transaction object is required"}), 400
        transaction_id = transaction.get("transaction_id")
        if isinstance(transaction_id, str) and transaction_id in chain.transaction_ids:
            return jsonify({"message": "Transaction already known"}), 200
        try:
            chain.add_broadcast_transaction(transaction)
        except ValueError as error:
            sync = chain.synchronize()
            return jsonify({"message": str(error), "sync_required": True, "sync": sync}), 409
        return jsonify({"message": "Transaction added"}), 201

    @app.route("/transactions", methods=["GET"])
    def get_transactions():
        return jsonify({"transactions": chain.pending_transactions}), 200

    @app.route("/mine", methods=["POST"])
    def mine_block():
        try:
            block = chain.mine_pending_block()
        except ValueError as error:
            return jsonify({"message": str(error)}), 409
        broadcast = _broadcast(chain, "/block/receive", {"block": block})
        return jsonify({
            "message": "New block forged",
            "block": block,
            "broadcast": broadcast,
        }), 200

    @app.route("/block/receive", methods=["POST"])
    def receive_block():
        values = _json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        block = values.get("block")
        if not isinstance(block, dict):
            return jsonify({"message": "A block object is required"}), 400
        try:
            added = chain.add_block(block)
        except ValueError as error:
            sync = chain.synchronize()
            return jsonify({"message": str(error), "sync_required": True, "sync": sync}), 409
        if not added:
            return jsonify({"message": "Block already known"}), 200
        return jsonify({"message": "Block received and added"}), 201

    @app.route("/blockchain", methods=["GET"])
    def full_chain():
        exported = chain.export_state()
        return jsonify({"chain": exported["chain"], "length": len(exported["chain"])}), 200

    @app.route("/blockchain/validate", methods=["GET"])
    def blockchain_validation():
        valid = chain.is_valid()
        return jsonify({"valid": valid, "status": "VALID" if valid else "INVALID"}), 200

    @app.route("/users/register", methods=["POST"])
    def register_user():
        values = _json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        try:
            user_id, changed = chain.register_user(values.get("display_name"))
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        reports = _broadcast(
            chain,
            "/users/update",
            {"users": {user_id: chain.user_balance(user_id)[0]}},
        ) if changed else []
        _, balance = chain.user_balance(user_id)
        return jsonify({"user_id": user_id, "balance": balance, "broadcast": reports}), 201

    @app.route("/users/update", methods=["POST"])
    def update_users():
        values = _json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        try:
            chain.merge_users(values.get("users"))
        except ValueError as error:
            sync = chain.synchronize()
            return jsonify({"message": str(error), "sync_required": True, "sync": sync}), 409
        return jsonify({"message": "User registry updated"}), 200

    @app.route("/users", methods=["GET"])
    def get_users():
        return jsonify(chain.export_users()), 200

    @app.route("/users/credit", methods=["POST"])
    def credit_user():
        admin_token = os.environ.get("BLOCKCHAIN_ADMIN_TOKEN")
        if not admin_token:
            return jsonify({"message": "Administrative credits are disabled"}), 503
        supplied_token = request.headers.get("X-Admin-Token", "")
        if not hmac.compare_digest(supplied_token, admin_token):
            return jsonify({"message": "Administrative authorization required"}), 403
        values = _json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        try:
            transaction = chain.new_admin_credit(
                values.get("user_id"),
                values.get("amount"),
                admin_token,
            )
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        broadcast = _broadcast(chain, "/transaction/broadcast", transaction)
        return jsonify({"transaction": transaction, "broadcast": broadcast}), 201

    @app.route("/nodes", methods=["GET"])
    def get_nodes():
        return jsonify({"nodes": chain.peer_nodes}), 200

    @app.route("/nodes/register", methods=["POST"])
    def register_nodes():
        values = _json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        nodes = values.get("nodes")
        if isinstance(nodes, str):
            nodes = [nodes]
        if not isinstance(nodes, list):
            return jsonify({"message": "Please supply a node address or list of nodes"}), 400

        if not all(chain._valid_node_address(node) for node in nodes):
            sync = chain.synchronize()
            return jsonify({"message": "One or more peer addresses are invalid", "sync": sync}), 400
        for node in nodes:
            if node != chain.local_address:
                chain.register_node(node)

        reports = []
        reports.extend(_broadcast(chain, "/nodes/update", {"nodes": chain.peer_nodes}))
        reports.extend(_broadcast(chain, "/users/update", {"users": chain.export_users()["users"]}))
        return jsonify({"nodes": chain.peer_nodes, "broadcast": reports}), 201

    @app.route("/nodes/update", methods=["POST"])
    def update_nodes():
        values = _json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required", "sync_required": True}), 400
        nodes = values.get("nodes")
        if not isinstance(nodes, list):
            return jsonify({"message": "A list of nodes is required", "sync_required": True}), 400
        if not all(chain._valid_node_address(node) for node in nodes):
            sync = chain.synchronize()
            return jsonify({"message": "One or more peer addresses are invalid", "sync_required": True, "sync": sync}), 409
        for node in nodes:
            if node != chain.local_address:
                chain.register_node(node)
        return jsonify({"message": "Node list updated"}), 200

    @app.route("/state", methods=["GET"])
    def state():
        return jsonify(chain.export_state()), 200

    @app.route("/nodes/resolve", methods=["GET"])
    def resolve():
        report = chain.synchronize()
        return jsonify({
            "message": "Synchronization complete",
            "changed": report["changed"],
            "peers": report["peers"],
            "chain": chain.export_state()["chain"],
        }), 200

    app.config["BLOCKCHAIN"] = chain
    return app
