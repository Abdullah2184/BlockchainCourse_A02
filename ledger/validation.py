import hashlib
import hmac
import json
import os
import re
from uuid import UUID

from block import hash_block
from ledger.constants import DIFFICULTY, GENESIS_PREVIOUS_HASH, SYSTEM_ACCOUNT


def is_positive_amount(amount) -> bool:
    return isinstance(amount, int) and not isinstance(amount, bool) and amount > 0


def is_valid_user_id(user_id) -> bool:
    if not isinstance(user_id, str) or len(user_id) != 36:
        return False
    try:
        return str(UUID(user_id)) == user_id
    except ValueError:
        return False


def is_valid_users(users) -> bool:
    return (
        isinstance(users, dict)
        and all(
            is_valid_user_id(user_id)
            and isinstance(user, dict)
            and set(user) == {"display_name"}
            and isinstance(user["display_name"], str)
            and bool(user["display_name"].strip())
            for user_id, user in users.items()
        )
    )


def is_valid_node_address(address) -> bool:
    if not isinstance(address, str) or not address.strip() or "/" in address:
        return False
    host, separator, port = address.strip().rpartition(":")
    return bool(
        separator
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host)
        and len(port) <= 5
        and port.isdigit()
        and 1 <= int(port) <= 65535
    )


def is_authorized_credit(transaction, secret=None) -> bool:
    secret = os.environ.get("BLOCKCHAIN_ADMIN_TOKEN") if secret is None else secret
    authorization = transaction.get("authorization")
    if not secret or not isinstance(authorization, str):
        return False
    fields = {
        "transaction_id": transaction["transaction_id"],
        "recipient_id": transaction["recipient_id"],
        "amount": transaction["amount"],
    }
    message = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(authorization, expected)


def validate_transaction(transaction, users, balances, seen_ids, admin_secret=None) -> bool:
    if not isinstance(transaction, dict):
        return False
    required = {"transaction_id", "type", "sender_id", "recipient_id", "amount"}
    expected = required | ({"authorization"} if transaction.get("type") == "credit" else set())
    if set(transaction) != expected:
        return False
    transaction_id = transaction["transaction_id"]
    if not is_valid_user_id(transaction_id) or transaction_id in seen_ids:
        return False
    if not is_positive_amount(transaction["amount"]):
        return False

    kind = transaction["type"]
    sender = transaction["sender_id"]
    recipient = transaction["recipient_id"]
    if not is_valid_user_id(recipient) or recipient not in users:
        return False
    if kind == "credit":
        if sender != SYSTEM_ACCOUNT or not is_authorized_credit(transaction, admin_secret):
            return False
        balances[recipient] = balances.get(recipient, 0) + transaction["amount"]
    elif kind == "transfer":
        if not is_valid_user_id(sender) or sender not in users or sender == recipient:
            return False
        if balances.get(sender, 0) < transaction["amount"]:
            return False
        balances[sender] -= transaction["amount"]
        balances[recipient] = balances.get(recipient, 0) + transaction["amount"]
    else:
        return False

    seen_ids.add(transaction_id)
    return True


def genesis_block() -> dict:
    block = {
        "index": 0,
        "timestamp": 0,
        "transactions": [],
        "proof": 0,
        "previous_hash": GENESIS_PREVIOUS_HASH,
    }
    block["hash"] = hash_block(block)
    return block


def validate_chain(chain, users, admin_secret=None) -> bool:
    if not isinstance(chain, list) or not chain or not is_valid_users(users):
        return False
    if chain[0] != genesis_block():
        return False

    balances = {user_id: 0 for user_id in users}
    seen_ids = set()
    last_block = chain[0]
    for index, block in enumerate(chain[1:], start=1):
        if not isinstance(block, dict):
            return False
        if block.get("index") != index or block.get("previous_hash") != hash_block(last_block):
            return False
        if block.get("hash") != hash_block(block):
            return False
        if not block["hash"].startswith("0" * DIFFICULTY):
            return False
        if not isinstance(block.get("transactions"), list):
            return False
        miner_id = block.get("miner_id")
        if not is_valid_user_id(miner_id) or miner_id not in users:
            return False
        rewards = 0
        for transaction in block["transactions"]:
            if not isinstance(transaction, dict):
                return False
            if transaction.get("type") == "reward":
                transaction_id = transaction.get("transaction_id")
                if (
                    transaction.get("sender_id") != SYSTEM_ACCOUNT
                    or transaction.get("recipient_id") != miner_id
                    or transaction.get("amount") != 1
                    or not is_valid_user_id(transaction_id)
                    or transaction_id in seen_ids
                ):
                    return False
                rewards += 1
                seen_ids.add(transaction_id)
                balances[miner_id] += 1
                continue
            if not validate_transaction(transaction, users, balances, seen_ids, admin_secret):
                return False
        if rewards != 1:
            return False
        last_block = block
    return True


def balances_for_chain(chain, users, admin_secret=None) -> dict[str, int]:
    if not validate_chain(chain, users, admin_secret):
        raise ValueError("Cannot calculate balances from an invalid blockchain")

    balances = {user_id: 0 for user_id in users}
    seen_ids = set()
    for block in chain[1:]:
        for transaction in block["transactions"]:
            if transaction["type"] == "reward":
                transaction_id = transaction["transaction_id"]
                if transaction_id in seen_ids:
                    raise ValueError("Blockchain contains a duplicate transaction identifier")
                seen_ids.add(transaction_id)
                balances[transaction["recipient_id"]] += transaction["amount"]
            elif not validate_transaction(transaction, users, balances, seen_ids, admin_secret):
                raise ValueError("Blockchain contains an invalid transaction")
    return balances


def chain_rank(chain) -> tuple[int, str]:
    work = sum((1 << 256) // (int(block["hash"], 16) + 1) for block in chain[1:])
    return work, chain[-1]["hash"]
