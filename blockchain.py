import hashlib
import hmac
import json
import logging
import os
import re
from copy import deepcopy
from pathlib import Path
from functools import wraps
from threading import RLock
from time import time
from uuid import UUID, uuid4

import requests

from block import hash_block


logger = logging.getLogger(__name__)
DIFFICULTY = 4
SYSTEM_ACCOUNT = "SYSTEM"
GENESIS_PREVIOUS_HASH = "0" * 64
STATE_VERSION = 1


def _locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class Blockchain:
    def __init__(self, data_dir):
        self._lock = RLock()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "state.json"

        if self.state_path.exists():
            self._load_state()
        else:
            self.node_id = str(uuid4())
            self.nodes = set()
            self.users = {self.node_id: {"display_name": f"Node {self.node_id[:8]}"}}
            self.current_transactions = []
            self.chain = [self._create_genesis_block()]
            self.balances = self._balances_for_chain(self.chain, self.users)
            self._save_state()

    @staticmethod
    def _create_genesis_block():
        block = {
            "index": 0,
            "timestamp": 0,
            "transactions": [],
            "proof": 0,
            "previous_hash": GENESIS_PREVIOUS_HASH,
        }
        block["hash"] = hash_block(block)
        return block

    @property
    @_locked
    def last_block(self):
        return self.chain[-1]

    @property
    @_locked
    def transaction_ids(self):
        return {
            transaction["transaction_id"]
            for block in self.chain
            for transaction in block["transactions"]
        } | {transaction["transaction_id"] for transaction in self.current_transactions}

    @property
    @_locked
    def peer_nodes(self):
        return tuple(sorted(self.nodes))

    @property
    @_locked
    def pending_transactions(self):
        return list(self.current_transactions)

    @staticmethod
    def _is_positive_amount(amount):
        return isinstance(amount, int) and not isinstance(amount, bool) and amount > 0

    @staticmethod
    def _valid_user_id(user_id):
        if not isinstance(user_id, str) or len(user_id) != 36:
            return False
        try:
            return str(UUID(user_id)) == user_id
        except ValueError:
            return False

    @classmethod
    def _valid_users(cls, users):
        return (
            isinstance(users, dict)
            and all(
                cls._valid_user_id(user_id)
                and isinstance(user, dict)
                and set(user) == {"display_name"}
                and isinstance(user["display_name"], str)
                and bool(user["display_name"].strip())
                for user_id, user in users.items()
            )
        )

    @staticmethod
    def _valid_node_address(address):
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

    def _transaction_valid(self, transaction, users, balances, seen_ids):
        if not isinstance(transaction, dict):
            return False
        required = {"transaction_id", "type", "sender_id", "recipient_id", "amount"}
        expected = required | ({"authorization"} if transaction.get("type") == "credit" else set())
        if set(transaction) != expected:
            return False
        transaction_id = transaction["transaction_id"]
        if not self._valid_user_id(transaction_id) or transaction_id in seen_ids:
            return False
        if not self._is_positive_amount(transaction["amount"]):
            return False

        kind = transaction["type"]
        sender = transaction["sender_id"]
        recipient = transaction["recipient_id"]
        if not self._valid_user_id(recipient):
            return False
        if kind == "credit":
            if sender != SYSTEM_ACCOUNT or not self._credit_authorized(transaction):
                return False
            balances[recipient] = balances.get(recipient, 0) + transaction["amount"]
        elif kind == "reward":
            return False
        elif kind == "transfer":
            if not self._valid_user_id(sender) or sender not in users or sender == recipient:
                return False
            if balances.get(sender, 0) < transaction["amount"]:
                return False
            balances[sender] -= transaction["amount"]
            balances[recipient] = balances.get(recipient, 0) + transaction["amount"]
        else:
            return False

        seen_ids.add(transaction_id)
        return True

    @staticmethod
    def _credit_authorized(transaction):
        secret = os.environ.get("BLOCKCHAIN_ADMIN_TOKEN")
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

    @_locked
    def _balances_for_chain(self, chain, users):
        if not self.valid_chain(chain, users):
            raise ValueError("Cannot calculate balances from an invalid blockchain")
        balances = {user_id: 0 for user_id in users}
        seen_ids = set()
        for block in chain[1:]:
            for transaction in block["transactions"]:
                if transaction["type"] == "reward":
                    transaction_id = transaction["transaction_id"]
                    recipient_id = transaction["recipient_id"]
                    if transaction_id in seen_ids:
                        raise ValueError("Blockchain contains a duplicate transaction identifier")
                    seen_ids.add(transaction_id)
                    balances[recipient_id] += transaction["amount"]
                    continue
                if not self._transaction_valid(transaction, users, balances, seen_ids):
                    raise ValueError("Blockchain contains an invalid transaction")
        return balances

    def _load_state(self):
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to load node state from {self.state_path}: {error}") from error

        required = {"version", "node_id", "nodes", "users", "current_transactions", "chain", "balances"}
        if not isinstance(state, dict) or set(state) != required:
            raise ValueError(f"Node state at {self.state_path} has an unsupported format")
        if state["version"] != STATE_VERSION:
            raise ValueError(f"Node state at {self.state_path} has unsupported version {state['version']!r}")
        if not self._valid_user_id(state["node_id"]):
            raise ValueError(f"Node state at {self.state_path} has an invalid node id")
        if not self._valid_users(state["users"]):
            raise ValueError(f"Node state at {self.state_path} has invalid user data")
        if state["node_id"] not in state["users"]:
            raise ValueError(f"Node state at {self.state_path} is missing its node account")
        if not isinstance(state["nodes"], list) or not all(self._valid_node_address(node) for node in state["nodes"]):
            raise ValueError(f"Node state at {self.state_path} has invalid peer data")
        if not isinstance(state["current_transactions"], list) or not isinstance(state["chain"], list):
            raise ValueError(f"Node state at {self.state_path} has invalid ledger data")
        if not self.valid_chain(state["chain"], state["users"]):
            raise ValueError(f"Node state at {self.state_path} contains an invalid blockchain")

        self.node_id = state["node_id"]
        self.nodes = set(state["nodes"])
        self.users = state["users"]
        self.chain = state["chain"]
        self.current_transactions = []
        self.balances = self._balances_for_chain(self.chain, self.users)
        seen_ids = self.transaction_ids
        for transaction in state["current_transactions"]:
            self._validate_pending_transaction(transaction, seen_ids)
            seen_ids.add(transaction["transaction_id"])
            self.current_transactions.append(transaction)

        if state["balances"] != self.balances:
            raise ValueError(f"Persisted balances at {self.state_path} do not match the blockchain")

    @_locked
    def _save_state(self):
        state = {
            "version": STATE_VERSION,
            "node_id": self.node_id,
            "nodes": sorted(self.nodes),
            "users": self.users,
            "current_transactions": self.current_transactions,
            "chain": self.chain,
            "balances": self.balances,
        }
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")
        temporary_path.replace(self.state_path)

    def _validate_pending_transaction(self, transaction, seen_ids=None):
        known_ids = self.transaction_ids if seen_ids is None else seen_ids
        if not isinstance(transaction, dict):
            raise ValueError("Transaction payload has an invalid shape")
        required = {"transaction_id", "type", "sender_id", "recipient_id", "amount"}
        expected = required | ({"authorization"} if transaction.get("type") == "credit" else set())
        if set(transaction) != expected:
            raise ValueError("Transaction payload has an invalid shape")
        if not self._valid_user_id(transaction["transaction_id"]) or transaction["transaction_id"] in known_ids:
            raise ValueError("Transaction identifier is invalid or already known")
        if not self._is_positive_amount(transaction["amount"]):
            raise ValueError("Transaction amount must be a positive integer")
        if not self._valid_user_id(transaction["recipient_id"]) or transaction["recipient_id"] not in self.users:
            raise ValueError("Recipient identifier is not registered on this node")
        if transaction["type"] == "transfer":
            if (
                not self._valid_user_id(transaction["sender_id"])
                or transaction["sender_id"] not in self.users
            ):
                raise ValueError("Sender identifier is not registered on this node")
            if transaction["sender_id"] == transaction["recipient_id"]:
                raise ValueError("Sender and recipient must be different")
            pending_outgoing = sum(
                pending["amount"]
                for pending in self.current_transactions
                if pending["type"] == "transfer" and pending["sender_id"] == transaction["sender_id"]
            )
            if self.balances.get(transaction["sender_id"], 0) - pending_outgoing < transaction["amount"]:
                raise ValueError("Insufficient available balance")
        elif transaction["type"] == "credit":
            if transaction["sender_id"] != SYSTEM_ACCOUNT or not self._credit_authorized(transaction):
                raise ValueError("Administrative credit authorization is invalid")
        else:
            raise ValueError("Transaction type or sender is invalid")

    @_locked
    def revalidate_pending_transactions(self):
        pending = self.current_transactions
        self.current_transactions = []
        seen_ids = {
            transaction["transaction_id"]
            for block in self.chain
            for transaction in block["transactions"]
        }
        for transaction in pending:
            try:
                self._validate_pending_transaction(transaction, seen_ids)
            except ValueError as error:
                logger.warning(
                    "Discarding pending transaction %s after chain update: %s",
                    transaction.get("transaction_id"),
                    error,
                )
                continue
            self.current_transactions.append(transaction)
            seen_ids.add(transaction["transaction_id"])

    @_locked
    def new_transaction(self, sender_id, recipient_id, amount):
        transaction = {
            "transaction_id": str(uuid4()),
            "type": "transfer",
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "amount": amount,
        }
        self._validate_pending_transaction(transaction)
        self.current_transactions.append(transaction)
        self._save_state()
        return transaction

    @_locked
    def new_admin_credit(self, recipient_id, amount, secret):
        transaction_id = str(uuid4())
        fields = {
            "transaction_id": transaction_id,
            "recipient_id": recipient_id,
            "amount": amount,
        }
        message = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
        authorization = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        transaction = {
            "transaction_id": transaction_id,
            "type": "credit",
            "sender_id": SYSTEM_ACCOUNT,
            "recipient_id": recipient_id,
            "amount": amount,
            "authorization": authorization,
        }
        self._validate_pending_transaction(transaction)
        self.current_transactions.append(transaction)
        self._save_state()
        return transaction

    @_locked
    def register_user(self, display_name, user_id=None):
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("Display name must not be empty")
        user_id = user_id or str(uuid4())
        if not self._valid_user_id(user_id):
            raise ValueError("User identifier must be a UUID")
        user = {"display_name": display_name.strip()}
        if user_id in self.users and self.users[user_id] != user:
            raise ValueError("User identifier is already registered with different data")
        changed = user_id not in self.users
        self.users[user_id] = user
        self.balances.setdefault(user_id, 0)
        if changed:
            self._save_state()
        return user_id, changed

    @_locked
    def merge_users(self, users):
        if not self._valid_users(users):
            raise ValueError("User registry payload is invalid")
        for user_id, user in users.items():
            if user_id in self.users and self.users[user_id] != user:
                raise ValueError(f"Conflicting data for user identifier {user_id}")
        changed = any(user_id not in self.users for user_id in users)
        if changed:
            self.users.update(users)
            for user_id in users:
                self.balances.setdefault(user_id, 0)
            self._save_state()
        return changed

    @_locked
    def register_node(self, address):
        if not self._valid_node_address(address):
            raise ValueError("Peer must be an address in host:port format")
        address = address.strip()
        changed = address not in self.nodes
        if changed:
            self.nodes.add(address)
            self._save_state()
        return changed

    @_locked
    def add_broadcast_transaction(self, transaction):
        self._validate_pending_transaction(transaction)
        self.current_transactions.append(transaction)
        self._save_state()

    @_locked
    def add_block(self, block):
        if any(existing.get("hash") == block.get("hash") for existing in self.chain):
            return False
        candidate_chain = self.chain + [block]
        if not self.valid_chain(candidate_chain, self.users):
            raise ValueError("Block failed chain, proof-of-work, or transaction validation")

        self.chain = candidate_chain
        included_ids = {transaction["transaction_id"] for transaction in block["transactions"]}
        self.current_transactions = [
            transaction for transaction in self.current_transactions
            if transaction["transaction_id"] not in included_ids
        ]
        self.balances = self._balances_for_chain(self.chain, self.users)
        self.revalidate_pending_transactions()
        self._save_state()
        return True

    @_locked
    def mine_pending_block(self):
        transactions = list(self.current_transactions)
        reward = {
            "transaction_id": str(uuid4()),
            "type": "reward",
            "sender_id": SYSTEM_ACCOUNT,
            "recipient_id": self.node_id,
            "amount": 1,
        }
        transactions.append(reward)
        candidate = {
            "index": len(self.chain),
            "timestamp": time(),
            "miner_id": self.node_id,
            "transactions": transactions,
            "proof": 0,
            "previous_hash": hash_block(self.last_block),
        }
        while True:
            block_hash = hash_block(candidate)
            if block_hash.startswith("0" * DIFFICULTY):
                candidate["hash"] = block_hash
                break
            candidate["proof"] += 1

        new_chain = self.chain + [candidate]
        if not self.valid_chain(new_chain, self.users):
            raise ValueError("Locally mined block failed validation")
        self.chain = new_chain
        self.current_transactions = []
        self.balances = self._balances_for_chain(self.chain, self.users)
        self._save_state()
        return candidate

    @_locked
    def valid_chain(self, chain, users=None):
        users = users if users is not None else self.users
        if not isinstance(chain, list) or not chain:
            return False
        genesis = self._create_genesis_block()
        if chain[0] != genesis:
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
            if not self._valid_user_id(miner_id) or miner_id not in users:
                return False
            rewards = 0
            for transaction in block["transactions"]:
                if not isinstance(transaction, dict):
                    return False
                if transaction.get("type") == "reward":
                    if (
                        transaction.get("sender_id") != SYSTEM_ACCOUNT
                        or transaction.get("recipient_id") != block["miner_id"]
                        or transaction.get("amount") != 1
                    ):
                        return False
                    rewards += 1
                    if (
                        not self._valid_user_id(transaction.get("transaction_id"))
                        or transaction["transaction_id"] in seen_ids
                    ):
                        return False
                    seen_ids.add(transaction["transaction_id"])
                    balances[block["miner_id"]] = balances.get(block["miner_id"], 0) + 1
                    continue
                if not self._transaction_valid(transaction, users, balances, seen_ids):
                    return False
            if rewards != 1:
                return False
            last_block = block
        return True

    @staticmethod
    def _chain_rank(chain):
        work = sum(
            (1 << 256) // (int(block["hash"], 16) + 1)
            for block in chain[1:]
        )
        return (work, chain[-1]["hash"])

    @_locked
    def merge_state(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Peer state must be a JSON object")
        users = payload.get("users")
        nodes = payload.get("nodes")
        candidate = payload.get("chain")
        if not self._valid_users(users):
            raise ValueError("Peer state has an invalid user registry")
        if not isinstance(nodes, list) or not all(self._valid_node_address(node) for node in nodes):
            raise ValueError("Peer state has an invalid node list")
        merged_users = dict(self.users)
        for user_id, user in users.items():
            if user_id in merged_users and merged_users[user_id] != user:
                raise ValueError(f"Conflicting data for user identifier {user_id}")
            merged_users[user_id] = user
        if not self.valid_chain(candidate, merged_users):
            raise ValueError("Peer state contains an invalid blockchain")

        changed = self.merge_users(users)
        for node in nodes:
            if node != self.local_address and node not in self.nodes:
                self.nodes.add(node)
                changed = True

        if (
            not self.valid_chain(self.chain, self.users)
            or self._chain_rank(candidate) > self._chain_rank(self.chain)
        ):
            self.chain = candidate
            chain_transaction_ids = {
                transaction["transaction_id"]
                for block in self.chain
                for transaction in block["transactions"]
            }
            self.current_transactions = [
                transaction for transaction in self.current_transactions
                if transaction["transaction_id"] not in chain_transaction_ids
            ]
            self.balances = self._balances_for_chain(self.chain, self.users)
            self.revalidate_pending_transactions()
            changed = True

        if changed:
            self._save_state()
        return changed

    @property
    def local_address(self):
        return getattr(self, "_local_address", None)

    @local_address.setter
    def local_address(self, address):
        self._local_address = address

    @_locked
    def export_state(self):
        return {
            "chain": deepcopy(self.chain),
            "users": deepcopy(self.users),
            "nodes": list(sorted(self.nodes)),
        }

    @_locked
    def export_users(self):
        return {"users": deepcopy(self.users), "balances": deepcopy(self.balances)}

    @_locked
    def user_balance(self, user_id):
        return self.users[user_id], self.balances[user_id]

    @_locked
    def is_valid(self):
        return self.valid_chain(self.chain, self.users)

    def synchronize(self):
        reports = []
        changed = False
        with self._lock:
            neighbors = sorted(self.nodes)
        for node in neighbors:
            try:
                response = requests.get(f"http://{node}/state", timeout=3)
            except requests.RequestException as error:
                reports.append({"node": node, "status": "error", "message": str(error)})
                continue
            if response.status_code != 200:
                reports.append({"node": node, "status": "rejected", "code": response.status_code})
                continue
            try:
                merged = self.merge_state(response.json())
            except (ValueError, requests.RequestException) as error:
                reports.append({"node": node, "status": "rejected", "message": str(error)})
                continue
            changed = changed or merged
            reports.append({"node": node, "status": "synchronized", "state_updated": merged})
        return {"changed": changed, "peers": reports}
