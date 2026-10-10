from flask import Blueprint, jsonify

from api.helpers import broadcast, json_object, rejected_payload


def create_transaction_blueprint(blockchain):
    blueprint = Blueprint("transactions", __name__)

    @blueprint.post("/transaction")
    def create_transaction():
        values = json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        required = ("sender_id", "recipient_id", "amount")
        if not all(key in values for key in required):
            return jsonify({"message": "sender_id, recipient_id, and amount are required"}), 400
        try:
            transaction = blockchain.new_transaction(
                values["sender_id"], values["recipient_id"], values["amount"]
            )
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        reports = broadcast(blockchain, "/transaction/broadcast", transaction)
        return jsonify({
            "message": "Transaction added",
            "transaction": transaction,
            "broadcast": reports,
        }), 201

    @blueprint.post("/transaction/broadcast")
    def broadcast_transaction():
        transaction = json_object()
        if transaction is None:
            return jsonify({"message": "A transaction object is required"}), 400
        transaction_id = transaction.get("transaction_id")
        if isinstance(transaction_id, str) and transaction_id in blockchain.transaction_ids:
            return jsonify({"message": "Transaction already known"}), 200
        try:
            blockchain.add_broadcast_transaction(transaction)
        except ValueError as error:
            return rejected_payload(str(error), blockchain)
        return jsonify({"message": "Transaction added"}), 201

    @blueprint.get("/transactions")
    def get_transactions():
        return jsonify({"transactions": blockchain.pending_transactions}), 200

    return blueprint
