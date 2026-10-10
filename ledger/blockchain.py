import hashlib
import hmac
import json
import logging
from copy import deepcopy
from functools import wraps
from pathlib import Path
from threading import RLock
from time import time
from uuid import uuid4

from block import hash_block
from ledger.constants import DIFFICULTY, SYSTEM_ACCOUNT
from ledger.storage import NodeStateStore
from ledger.synchronization import synchronize
from ledger.validation import (
    balances_for_chain,
    chain_rank,
    genesis_block,
    is_authorized_credit,
    is_positive_amount,
    is_valid_node_address,
    is_valid_user_id,
    is_valid_users,
    validate_chain,
)


logger = logging.getLogger(__name__)


def _locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class Blockchain:
    def __init__(self, data_dir: Path):
        self._lock = RLock()
        self.store = NodeStateStore(data_dir)
        self.data_dir = self.store.data_dir
        self.state_path = self.store.state_path

        if self.store.exists():
            self._load_state()
        else:
            self.node_id = str(uuid4())
            self.nodes = set()
            self.users = {self.node_id: {"display_name": f"Node {self.node_id[:8]}"}}
            self.current_transactions = []
            self.chain = [genesis_block()]
            self.balances = balances_for_chain(self.chain, self.users)
            self._save_state()

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
        return deepcopy(self.current_transactions)

    @staticmethod
    def _valid_user_id(user_id):
        return is_valid_user_id(user_id)

    @staticmethod
    def _valid_node_address(address):
        return is_valid_node_address(address)

    def _load_state(self):
        state = self.store.load()
        if not is_valid_user_id(state["node_id"]):
            raise ValueError(f"Node state at {self.state_path} has an invalid node id")
        if not is_valid_users(state["users"]):
            raise ValueError(f"Node state at {self.state_path} has invalid user data")
        if state["node_id"] not in state["users"]:
            raise ValueError(f"Node state at {self.state_path} is missing its node account")
        if not isinstance(state["nodes"], list) or not all(is_valid_node_address(node) for node in state["nodes"]):
            raise ValueError(f"Node state at {self.state_path} has invalid peer data")
        if not isinstance(state["current_transactions"], list) or not isinstance(state["chain"], list):
            raise ValueError(f"Node state at {self.state_path} has invalid ledger data")
        if not validate_chain(state["chain"], state["users"]):
            raise ValueError(f"Node state at {self.state_path} contains an invalid blockchain")

        self.node_id = state["node_id"]
        self.nodes = set(state["nodes"])
        self.users = state["users"]
        self.chain = state["chain"]
        self.balances = balances_for_chain(self.chain, self.users)
        self.current_transactions = []
        seen_ids = self.transaction_ids
        for transaction in state["current_transactions"]:
            self._validate_pending_transaction(transaction, seen_ids)
            seen_ids.add(transaction["transaction_id"])
            self.current_transactions.append(transaction)
        if state["balances"] != self.balances:
            raise ValueError(f"Persisted balances at {self.state_path} do not match the blockchain")

    @_locked
    def _save_state(self):
        self.store.save({
            "node_id": self.node_id,
            "nodes": sorted(self.nodes),
            "users": self.users,
            "current_transactions": self.current_transactions,
            "chain": self.chain,
            "balances": self.balances,
        })

    def _validate_pending_transaction(self, transaction, seen_ids=None):
        known_ids = self.transaction_ids if seen_ids is None else seen_ids
        if not isinstance(transaction, dict):
            raise ValueError("Transaction payload has an invalid shape")
        required = {"transaction_id", "type", "sender_id", "recipient_id", "amount"}
        expected = required | ({"authorization"} if transaction.get("type") == "credit" else set())
        if set(transaction) != expected:
            raise ValueError("Transaction payload has an invalid shape")
        if not is_valid_user_id(transaction["transaction_id"]) or transaction["transaction_id"] in known_ids:
            raise ValueError("Transaction identifier is invalid or already known")
        if not is_positive_amount(transaction["amount"]):
            raise ValueError("Transaction amount must be a positive integer")
        recipient = transaction["recipient_id"]
        if not is_valid_user_id(recipient) or recipient not in self.users:
            raise ValueError("Recipient identifier is not registered on this node")
        if transaction["type"] == "transfer":
            sender = transaction["sender_id"]
            if not is_valid_user_id(sender) or sender not in self.users:
                raise ValueError("Sender identifier is not registered on this node")
            if sender == recipient:
                raise ValueError("Sender and recipient must be different")
            pending_outgoing = sum(
                pending["amount"]
                for pending in self.current_transactions
                if pending["type"] == "transfer" and pending["sender_id"] == sender
            )
            if self.balances.get(sender, 0) - pending_outgoing < transaction["amount"]:
                raise ValueError("Insufficient available balance")
        elif transaction["type"] == "credit":
            if transaction["sender_id"] != SYSTEM_ACCOUNT or not is_authorized_credit(transaction):
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
        return deepcopy(transaction)

    @_locked
    def new_admin_credit(self, recipient_id, amount, secret):
        transaction_id = str(uuid4())
        fields = {"transaction_id": transaction_id, "recipient_id": recipient_id, "amount": amount}
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
        return deepcopy(transaction)

    @_locked
    def register_user(self, display_name, user_id=None):
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("Display name must not be empty")
        user_id = user_id or str(uuid4())
        if not is_valid_user_id(user_id):
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
        if not is_valid_users(users):
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
        if not is_valid_node_address(address):
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
        self.current_transactions.append(deepcopy(transaction))
        self._save_state()

    @_locked
    def add_block(self, block):
        if any(existing.get("hash") == block.get("hash") for existing in self.chain):
            return False
        candidate_chain = self.chain + [block]
        if not validate_chain(candidate_chain, self.users):
            raise ValueError("Block failed chain, proof-of-work, or transaction validation")

        self.chain = candidate_chain
        included_ids = {transaction["transaction_id"] for transaction in block["transactions"]}
        self.current_transactions = [
            transaction for transaction in self.current_transactions
            if transaction["transaction_id"] not in included_ids
        ]
        self.balances = balances_for_chain(self.chain, self.users)
        self.revalidate_pending_transactions()
        self._save_state()
        return True

    @_locked
    def mine_pending_block(self):
        transactions = list(self.current_transactions)
        transactions.append({
            "transaction_id": str(uuid4()),
            "type": "reward",
            "sender_id": SYSTEM_ACCOUNT,
            "recipient_id": self.node_id,
            "amount": 1,
        })
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
        if not validate_chain(new_chain, self.users):
            raise ValueError("Locally mined block failed validation")
        self.chain = new_chain
        self.current_transactions = []
        self.balances = balances_for_chain(self.chain, self.users)
        self._save_state()
        return deepcopy(candidate)

    @_locked
    def valid_chain(self, chain, users=None):
        return validate_chain(chain, users if users is not None else self.users)

    @_locked
    def merge_state(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Peer state must be a JSON object")
        users = payload.get("users")
        nodes = payload.get("nodes")
        candidate = payload.get("chain")
        if not is_valid_users(users):
            raise ValueError("Peer state has an invalid user registry")
        if not isinstance(nodes, list) or not all(is_valid_node_address(node) for node in nodes):
            raise ValueError("Peer state has an invalid node list")
        merged_users = dict(self.users)
        for user_id, user in users.items():
            if user_id in merged_users and merged_users[user_id] != user:
                raise ValueError(f"Conflicting data for user identifier {user_id}")
            merged_users[user_id] = user
        if not validate_chain(candidate, merged_users):
            raise ValueError("Peer state contains an invalid blockchain")

        changed = False
        new_users = {user_id: user for user_id, user in users.items() if user_id not in self.users}
        if new_users:
            self.users.update(new_users)
            for user_id in new_users:
                self.balances.setdefault(user_id, 0)
            changed = True
        for node in nodes:
            if node != self.local_address and node not in self.nodes:
                self.nodes.add(node)
                changed = True

        if (
            not validate_chain(self.chain, self.users)
            or chain_rank(candidate) > chain_rank(self.chain)
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
            self.balances = balances_for_chain(self.chain, self.users)
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
        return {"chain": deepcopy(self.chain), "users": deepcopy(self.users), "nodes": list(sorted(self.nodes))}

    @_locked
    def export_users(self):
        return {"users": deepcopy(self.users), "balances": deepcopy(self.balances)}

    @_locked
    def user_balance(self, user_id):
        return deepcopy(self.users[user_id]), self.balances[user_id]

    @_locked
    def is_valid(self):
        return validate_chain(self.chain, self.users)

    def synchronize(self):
        return synchronize(self)
