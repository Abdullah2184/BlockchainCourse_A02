from flask import Blueprint, jsonify

from api.helpers import broadcast, json_object, rejected_payload


def create_blocks_blueprint(blockchain):
    blueprint = Blueprint("blocks", __name__)

    @blueprint.post("/mine")
    def mine_block():
        try:
            block = blockchain.mine_pending_block()
        except ValueError as error:
            return jsonify({"message": str(error)}), 409
        reports = broadcast(blockchain, "/block/receive", {"block": block})
        return jsonify({
            "message": "New block forged",
            "block": block,
            "broadcast": reports,
        }), 200

    @blueprint.post("/block/receive")
    def receive_block():
        values = json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        block = values.get("block")
        if not isinstance(block, dict):
            return jsonify({"message": "A block object is required"}), 400
        try:
            added = blockchain.add_block(block)
        except ValueError as error:
            return rejected_payload(str(error), blockchain)
        if not added:
            return jsonify({"message": "Block already known"}), 200
        return jsonify({"message": "Block received and added"}), 201

    @blueprint.get("/blockchain")
    def full_chain():
        exported = blockchain.export_state()
        return jsonify({"chain": exported["chain"], "length": len(exported["chain"])}), 200

    @blueprint.get("/blockchain/validate")
    def blockchain_validation():
        valid = blockchain.is_valid()
        return jsonify({"valid": valid, "status": "VALID" if valid else "INVALID"}), 200

    return blueprint
