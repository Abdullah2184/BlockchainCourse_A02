# 1. Assignment Overview

In this assignment, students will develop a simple peer-to-peer (P2P) blockchain network using Python. The objective is to understand how blockchain nodes communicate with each other, maintain a distributed ledger, create and validate blocks, and achieve basic consensus.

Students will implement a small blockchain network in which multiple Python programs act as independent blockchain nodes.

# 2. Learning Objectives

- Explain the architecture of a blockchain network.
- Implement a basic blockchain using Python.
- Create and validate blocks using cryptographic hashing.
- Implement peer-to-peer communication between blockchain nodes.
- Broadcast transactions and newly mined blocks.
- Implement basic blockchain validation and consensus.
- Understand the role of distributed ledgers in decentralized systems.
- Analyze security limitations of a simple blockchain implementation.

# 3. Problem Statement

Develop a mini decentralized blockchain network consisting of at least three independent nodes. Each node should maintain its own copy of the blockchain and communicate with other nodes over a network.

The system should support:

- Creating transactions
- Broadcasting transactions
- Mining blocks
- Broadcasting newly mined blocks
- Validating blocks
- Synchronizing the blockchain between nodes
- Detecting invalid or tampered blocks

# 4. Functional Requirements

## Part A — Blockchain Implementation

Implement a Block class containing at least:

- Block index
- Timestamp
- Transactions
- Previous block hash
- Nonce
- Current block hash

Use SHA-256 to calculate the block hash.

Example:

import hashlib

def calculate_hash(data):
    return hashlib.sha256(data.encode()).hexdigest()

## Part B — Genesis Block

Create a genesis block that starts the blockchain.

Example:

Block 0
Previous Hash: 0000000000000000
Transactions: Genesis Block

## Part C — Transactions

Implement a transaction structure such as:

transaction = {
    "sender": "Alice",
    "receiver": "Bob",
    "amount": 50
}

A node should be able to create and store pending transactions.

## Part D — Proof of Work

Implement a basic Proof-of-Work mechanism. For example, require the hash to start with four zeros.

while not block_hash.startswith("0000"):
    nonce += 1
    block_hash = calculate_hash(block_data + str(nonce))

## Part E — P2P Network

Create at least three blockchain nodes. Each node should run on a different port:

- Node 1 → localhost:5001
- Node 2 → localhost:5002
- Node 3 → localhost:5003

Students may use Python's socket, Flask, and requests libraries for network communication.

## Part F — Transaction Broadcasting

When Node 1 creates a transaction such as Alice → Bob: 50 coins, it should broadcast the transaction to the other nodes. All nodes should add the transaction to their pending transaction pool.

## Part G — Block Broadcasting

After mining a block, the mining node should broadcast the newly created block to the other nodes.

Receiving nodes must:

1. Verify the previous hash.
2. Recalculate the block hash.
3. Verify Proof of Work.
4. Validate the transactions.
5. Add the block to their local blockchain.

## Part H — Blockchain Synchronization

Implement a mechanism through which a node can request the latest blockchain from another node. For example: Node 1 requests the blockchain → Node 2 returns its blockchain → Node 1 validates it → Node 1 replaces its local chain if the received chain is valid and longer.

# 5. Suggested API Endpoints

| Endpoint | Method | Purpose |
| ---      |  ---   |  ---    |
| /transaction | POST | Create a transaction |
| /transactions | GET | View pending transactions |
| /mine | POST | Mine a new block |
| /blockchain | GET | View blockchain |
| /nodes/register | POST | Register another node |
| /nodes/resolve | GET | Synchronize blockchain |
| /block/receive | POST | Receive a block from another node |

# 6. Example Transaction Request

{
    "sender": "Alice",
    "receiver": "Bob",
    "amount": 100
}

Expected response: {"message": "Transaction added successfully"}

# 7. Blockchain Validation

Create a function:

def is_chain_valid(blockchain):
    # Validate every block
    pass

The function should verify:

- Each block's hash.
- Previous block hash.
- Proof of Work.
- Block ordering.
- Transaction integrity.

If Block 2 is modified, subsequent blocks should become invalid because their previous-hash references no longer match. The program should detect the tampering.

# 8. Demonstration Requirements

1. Start three blockchain nodes: Node 1 (Port 5001), Node 2 (Port 5002), Node 3 (Port 5003).
2. Register the nodes with each other.
3. Create a transaction: Alice → Bob = 100 coins.
4. Broadcast the transaction.
5. Mine a new block.
6. Broadcast the mined block.
7. Display the blockchain on all three nodes.
8. Modify one block manually.
9. Run blockchain validation.
10. Synchronize the nodes again and demonstrate recovery using the valid chain.

Expected validation result after tampering: Blockchain is INVALID.

# 9. Security Analysis

Students must discuss at least five security issues associated with their implementation.

- 51% attack
- Sybil attack
- Double-spending
- Transaction manipulation
- Man-in-the-middle attack
- Node impersonation
- Denial-of-Service attack
- Weak authentication
- Lack of digital signatures
- Private-key management

# 10. Required Report

1. Introduction
2. Blockchain Architecture
3. System Architecture
4. Python Implementation
5. Block Structure
6. Transaction Processing
7. Proof of Work
8. P2P Communication
9. Consensus/Synchronization Mechanism
10. Blockchain Validation
11. Security Analysis
12. Experimental Results
13. Limitations
14. Conclusion
15. References

# 14. Bonus Challenge — 5 Marks

- RSA/ECDSA digital signatures
- Wallet generation
- Public/private key management
- Transaction signatures
- Merkle tree
- Multiple simultaneous transactions
- REST API
- Docker-based blockchain nodes
- Simple web dashboard
- Byzantine/faulty-node simulation
- Proof-of-Stake instead of Proof-of-Work

# 15. Important Restriction

Students must not simply copy an existing blockchain implementation from GitHub or another online source. The submitted implementation should demonstrate the student's understanding of: Cryptography → Blocks → Transactions → P2P Communication → Consensus → Distributed Ledger. Students should be able to explain every major component of their code during the viva.
