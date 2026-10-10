import hmac
import os

from flask import Blueprint, jsonify, request

from api.helpers import broadcast, json_object, rejected_payload


def create_users_blueprint(blockchain):
    blueprint = Blueprint("users", __name__)

    @blueprint.post("/users/register")
    def register_user():
        values = json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        try:
            user_id, changed = blockchain.register_user(values.get("display_name"))
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        reports = []
        if changed:
            user, _ = blockchain.user_balance(user_id)
            reports = broadcast(blockchain, "/users/update", {"users": {user_id: user}})
        _, balance = blockchain.user_balance(user_id)
        return jsonify({"user_id": user_id, "balance": balance, "broadcast": reports}), 201

    @blueprint.post("/users/update")
    def update_users():
        values = json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        try:
            blockchain.merge_users(values.get("users"))
        except ValueError as error:
            return rejected_payload(str(error), blockchain)
        return jsonify({"message": "User registry updated"}), 200

    @blueprint.get("/users")
    def get_users():
        return jsonify(blockchain.export_users()), 200

    @blueprint.post("/users/credit")
    def credit_user():
        admin_token = os.environ.get("BLOCKCHAIN_ADMIN_TOKEN")
        if not admin_token:
            return jsonify({"message": "Administrative credits are disabled"}), 503
        supplied_token = request.headers.get("X-Admin-Token", "")
        if not hmac.compare_digest(supplied_token, admin_token):
            return jsonify({"message": "Administrative authorization required"}), 403
        values = json_object()
        if values is None:
            return jsonify({"message": "A JSON object is required"}), 400
        try:
            transaction = blockchain.new_admin_credit(
                values.get("user_id"),
                values.get("amount"),
                admin_token,
            )
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        reports = broadcast(blockchain, "/transaction/broadcast", transaction)
        return jsonify({"transaction": transaction, "broadcast": reports}), 201

    return blueprint
