import hashlib
from time import time
from uuid import uuid4

import requests

from block import hash_block


class Blockchain:
    def __init__(self):
        self.chain = [] # Store the list of blocks in the blockchain
        self.current_transactions = [] # Store the current list of transactions
        self.nodes = set() # Store the addresses of other nodes in the network
        self.node_id = str(uuid4()).replace("-", "") # Generate a unique identifier for the node
        self.new_block(proof=100, previous_hash="0" * 64, is_genesis=True) #Creating the genesis block

    def new_block(self, proof, previous_hash=None, is_genesis=False):
        block = {
            "index": len(self.chain),
            "timestamp": time(),
            "transactions": list(self.current_transactions),
            "proof": proof,
            "previous_hash": previous_hash or self.hash(self.last_block),
        }
        block["hash"] = self.hash(block)

        if not is_genesis:
            self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        transaction = {
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
        }
        self.current_transactions.append(transaction)
        return self.last_block["index"] + 1

    @staticmethod
    def hash(block):
        return hash_block(block)

    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_block):
        last_proof = last_block["proof"]
        last_hash = last_block.get("hash") or self.hash(last_block)
        proof = 0
        while not self.valid_proof(last_proof, proof, last_hash):
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
        guess = f"{last_proof}{proof}{last_hash}".encode("utf-8")
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash.startswith("0000")

    def register_node(self, address):
        address = address.strip()
        if address:
            self.nodes.add(address)
        return address

    def valid_chain(self, chain):
        if not chain:
            return False

        if chain[0].get("index") != 0:
            return False
        if chain[0].get("previous_hash") != "0" * 64:
            return False

        last_block = chain[0]
        for block in chain[1:]:
            if block.get("previous_hash") != self.hash(last_block):
                return False
            if block.get("hash") != self.hash(block):
                return False
            if not self.valid_proof(last_block["proof"], block["proof"], last_block.get("hash") or self.hash(last_block)):
                return False
            last_block = block

        return True

    def is_chain_valid(self):
        return self.valid_chain(self.chain)

    def resolve_conflicts(self):
        neighbors = list(self.nodes)
        max_length = len(self.chain)
        new_chain = None

        for node in neighbors:
            try:
                response = requests.get(f"http://{node}/blockchain", timeout=3)
            except requests.RequestException:
                continue

            if response.status_code != 200:
                continue

            payload = response.json()
            candidate = payload.get("chain")
            if not isinstance(candidate, list):
                continue

            if len(candidate) > max_length and self.valid_chain(candidate):
                max_length = len(candidate)
                new_chain = candidate

        if new_chain is not None:
            self.chain = new_chain
            return True
        return False


def is_chain_valid(blockchain):
    return blockchain.is_chain_valid()
