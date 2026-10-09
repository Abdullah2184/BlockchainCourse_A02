from flask import Flask, jsonify, request

from blockchain import Blockchain


def create_app(blockchain_instance=None):
    app = Flask(__name__)
    blockchain = blockchain_instance or Blockchain()

    @app.route("/transaction", methods=["POST"])
    def create_transaction():
        values = request.get_json(silent=True) or {}
        required = ["sender", "receiver", "amount"]

        if not all(key in values for key in required):
            return jsonify({"message": "Missing values"}), 400

        index = blockchain.new_transaction(values["sender"], values["receiver"], values["amount"])
        transaction_payload = {
            "sender": values["sender"],
            "receiver": values["receiver"],
            "amount": values["amount"],
        }

        for peer in list(blockchain.nodes):
            try:
                import requests
                requests.post(f"http://{peer}/transaction/broadcast", json=transaction_payload, timeout=3)
            except requests.RequestException:
                continue

        return jsonify({"message": "Transaction added successfully", "index": index}), 201

    @app.route("/transaction/broadcast", methods=["POST"])
    def broadcast_transaction():
        values = request.get_json(silent=True) or {}
        required = ["sender", "receiver", "amount"]

        if not all(key in values for key in required):
            return jsonify({"message": "Missing values"}), 400

        transaction = {
            "sender": values["sender"],
            "receiver": values["receiver"],
            "amount": values["amount"],
        }

        if transaction not in blockchain.current_transactions:
            blockchain.current_transactions.append(transaction)
            return jsonify({"message": "Transaction added successfully"}), 201

        return jsonify({"message": "Transaction already known"}), 200

    @app.route("/transactions", methods=["GET"])
    def get_transactions():
        return jsonify({"transactions": blockchain.current_transactions}), 200

    @app.route("/mine", methods=["POST"])
    def mine_block():
        last_block = blockchain.last_block
        proof = blockchain.proof_of_work(last_block)
        blockchain.new_transaction(sender="0", recipient=blockchain.node_id, amount=1)
        previous_hash = blockchain.hash(last_block)
        block = blockchain.new_block(proof, previous_hash)

        for peer in list(blockchain.nodes):
            try:
                import requests
                requests.post(f"http://{peer}/block/receive", json={"block": block}, timeout=3)
            except requests.RequestException:
                continue

        return jsonify({
            "message": "New Block Forged",
            "index": block["index"],
            "transactions": block["transactions"],
            "proof": block["proof"],
            "previous_hash": block["previous_hash"],
            "hash": block["hash"],
        }), 200

    @app.route("/block/receive", methods=["POST"])
    def receive_block():
        values = request.get_json(silent=True) or {}
        block = values.get("block")

        if not isinstance(block, dict):
            return jsonify({"message": "Missing block data"}), 400

        if block.get("hash") != Blockchain.hash(block):
            return jsonify({"message": "Block hash mismatch"}), 400

        if len(blockchain.chain) > 0 and block.get("previous_hash") != blockchain.hash(blockchain.last_block):
            if not blockchain.valid_chain(blockchain.chain + [block]):
                return jsonify({"message": "Invalid block"}), 400

        if any(existing.get("hash") == block.get("hash") for existing in blockchain.chain):
            return jsonify({"message": "Block already known"}), 200

        blockchain.chain.append(block)
        blockchain.current_transactions = []
        return jsonify({"message": "Block received and added"}), 201

    @app.route("/blockchain", methods=["GET"])
    def full_chain():
        return jsonify({"chain": blockchain.chain, "length": len(blockchain.chain)}), 200

    @app.route("/blockchain/validate", methods=["GET"])
    def blockchain_validation():
        valid = blockchain.is_chain_valid()
        return jsonify({"valid": valid, "status": "VALID" if valid else "INVALID"}), 200

    @app.route("/nodes/register", methods=["POST"])
    def register_nodes():
        values = request.get_json(silent=True) or {}
        nodes = values.get("nodes")
        if nodes is None:
            if isinstance(values.get("node"), str):
                nodes = [values["node"]]
            else:
                return jsonify({"message": "Error: Please supply a valid list of nodes"}), 400

        if isinstance(nodes, str):
            nodes = [nodes]

        for node in nodes:
            blockchain.register_node(node)

        return jsonify({
            "message": "New nodes have been added",
            "total_nodes": sorted(list(blockchain.nodes)),
        }), 201

    @app.route("/nodes/resolve", methods=["GET"])
    def consensus():
        replaced = blockchain.resolve_conflicts()
        if replaced:
            return jsonify({"message": "Our chain was replaced", "chain": blockchain.chain}), 200
        return jsonify({"message": "Our chain is authoritative", "chain": blockchain.chain}), 200

    return app


blockchain = Blockchain()
app = create_app(blockchain)
