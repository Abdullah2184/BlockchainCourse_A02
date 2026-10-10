from flask import Blueprint, jsonify

from api.helpers import broadcast, json_object, rejected_payload
from ledger.validation import is_valid_node_address


def create_nodes_blueprint(blockchain):
    blueprint = Blueprint("nodes", __name__)

    @blueprint.get("/nodes")
    def get_nodes():
        return jsonify({"nodes": blockchain.peer_nodes}), 200

    @blueprint.post("/nodes/register")
    def register_nodes():
        values = json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        nodes = values.get("nodes")
        if isinstance(nodes, str):
            nodes = [nodes]
        if not isinstance(nodes, list):
            return rejected_payload(
                "Please supply a node address or list of nodes",
                blockchain,
                status=400,
            )
        if not all(is_valid_node_address(node) for node in nodes):
            return rejected_payload("One or more peer addresses are invalid", blockchain, status=400)
        for node in nodes:
            if node != blockchain.local_address:
                blockchain.register_node(node)

        reports = broadcast(blockchain, "/nodes/update", {"nodes": blockchain.peer_nodes})
        users = blockchain.export_users()["users"]
        reports.extend(broadcast(blockchain, "/users/update", {"users": users}))
        return jsonify({"nodes": blockchain.peer_nodes, "broadcast": reports}), 201

    @blueprint.post("/nodes/update")
    def update_nodes():
        values = json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required", "sync_required": True}), 400
        nodes = values.get("nodes")
        if not isinstance(nodes, list):
            return rejected_payload("A list of nodes is required", blockchain, status=400)
        if not all(is_valid_node_address(node) for node in nodes):
            return rejected_payload("One or more peer addresses are invalid", blockchain)
        for node in nodes:
            if node != blockchain.local_address:
                blockchain.register_node(node)
        return jsonify({"message": "Node list updated"}), 200

    @blueprint.get("/state")
    def state():
        return jsonify(blockchain.export_state()), 200

    @blueprint.get("/nodes/resolve")
    def resolve():
        report = blockchain.synchronize()
        return jsonify({
            "message": "Synchronization complete",
            "changed": report["changed"],
            "peers": report["peers"],
            "chain": blockchain.export_state()["chain"],
        }), 200

    return blueprint
