# Blockchain Network Assignment Report

## 1. Introduction

This project is a learning-oriented implementation of a small peer-to-peer
blockchain network in Python. It demonstrates a SHA-256-linked ledger,
transactions, a proof-of-work search, HTTP communication between nodes, and
basic longest-chain synchronization. Each node runs as an independent Flask
process and maintains its own in-memory state.

The implementation is intentionally minimal. It illustrates core blockchain
concepts, but its validation, consensus, and security properties are not
sufficient for production use.

## 2. Blockchain Architecture

The application uses a set of nodes that each maintain a local chain. A node
can register peer addresses, accept transactions, mine blocks, broadcast new
transactions and blocks, and request peer chains. The network transport is
HTTP using Flask routes on the receiving side and the `requests` library on
the sending side.

The ledger is a sequence of dictionaries. Each block stores an index,
timestamp, transaction list, proof value, previous block hash, and its own
hash. The hash is SHA-256 over JSON-serialized block fields (sorted by key)
other than the stored hash. This makes changes to hashed block fields
detectable when the hash is recalculated, and each subsequent block refers to
the preceding block's hash.

## 3. System Architecture

The implementation is divided into these modules:

- `block.py`: canonical JSON serialization and block hashing.
- `blockchain.py`: chain state, transactions, mining, validation, peer
  registration, and chain resolution.
- `app.py`: Flask application factory and HTTP endpoints.
- `main.py`: command-line entry point; accepts an optional listening port
  (default `5000`).

Each `Blockchain` instance creates a random node identifier and a genesis
block at startup. The genesis block includes the startup timestamp, so
independently started processes usually produce different genesis hashes.
State is local to that process and is not shared except through API requests.
The project dependencies are declared in `pyproject.toml`.

## 4. Python Implementation

The core is the `Blockchain` class. `new_transaction` appends a dictionary
containing `sender`, `recipient`, and `amount` to the pending pool.
`new_block` copies the pending transactions into a block, sets its index,
timestamp, proof, previous hash, and calculated hash, then clears the pending
pool for non-genesis blocks.

`create_app` accepts an optional blockchain instance, which allows separate
in-process app instances to be created for testing or embedding. HTTP route
handlers use Flask's JSON request and response helpers. Network calls have a
three-second timeout; request exceptions are skipped, so the API response does
not guarantee that a peer received a broadcast.

## 5. Block Structure

A block has the following fields:

| Field | Meaning |
| --- | --- |
| `index` | Position in the chain, starting at zero |
| `timestamp` | Creation time returned by Python's `time()` |
| `transactions` | Transactions included in this block |
| `proof` | Proof value found by the mining search |
| `previous_hash` | Hash of the preceding block |
| `hash` | SHA-256 digest of the sorted JSON representation of all other fields |

The genesis block has index `0`, previous hash consisting of 64 zeroes, and a
proof value of `100`. Its transaction list is empty; it is not a textual
"Genesis Block" transaction.

## 6. Transaction Processing

The `/transaction` endpoint accepts JSON with `sender`, `receiver`, and
`amount`. If a required key is absent, it returns HTTP 400. Otherwise it adds
the transaction to the local pending pool and posts it to each registered
peer's `/transaction/broadcast` endpoint. The peer endpoint avoids adding an
identical transaction already in its pending pool.

The implementation does not check field types, amount range, sender funds,
ownership, signatures, or duplicate transaction identifiers. The local
transaction is stored with a `recipient` field internally, while the HTTP
request uses `receiver`; the endpoint translates between those names before
adding the transaction.

Mining adds a reward transaction with sender `"0"`, the local node identifier
as recipient, and amount `1`. This is an illustrative reward, not a
cryptographically enforced issuance rule.

## 7. Proof of Work

Mining increments a candidate proof from zero. For each candidate it computes
SHA-256 over the UTF-8 bytes of the previous proof, candidate proof, and
previous block hash concatenated as strings. A proof is accepted when this
digest starts with four zeroes. The proof value is stored in the new block.

The difficulty is fixed in the code. This proof condition is not a requirement
that the new block's own hash start with four zeroes, and there is no dynamic
difficulty adjustment.

## 8. P2P Communication

Nodes expose Flask endpoints on their configured ports. The `/nodes/register`
endpoint stores peer addresses. The transaction route broadcasts to peers at
`/transaction/broadcast`; the mining route broadcasts new blocks at
`/block/receive`. A node can retrieve another node's chain at `/blockchain`.

For a local three-node demonstration, start processes on ports 5001, 5002, and
5003, register each node with the other two, then submit and mine a
transaction. Transaction broadcasts can reach all registered nodes, but the
nodes' independently timestamped genesis blocks usually have different
hashes. As a result, peers reject the mined block's direct broadcast because
its previous hash does not match their local genesis. A peer can instead use
`/nodes/resolve` to adopt the miner's strictly longer valid chain. This
architecture does not provide authentication or a resilient peer-discovery
protocol.

## 9. Consensus/Synchronization Mechanism

The `/nodes/resolve` route requests `/blockchain` from every registered peer.
The resolver adopts a candidate only when it is both valid under
`valid_chain` and strictly longer than the current local chain. It returns
whether the local chain was replaced.

This is a basic longest-valid-chain selection rule rather than a robust
consensus protocol. It has no fork-choice tie-breaker, quorum, finality, or
resistance to identity manipulation. Equal-length chains are not compared, and
an invalid local chain is not replaced by a valid chain of the same length.
Because each process starts with a different genesis hash, direct block
broadcasts between independently started nodes usually fail; resolving from a
peer with a longer valid chain can replace the local chain instead.

## 10. Blockchain Validation

The `/blockchain/validate` endpoint calls `is_chain_valid` and reports either
`VALID` or `INVALID`. The chain validator rejects an empty chain, requires the
first block's index to be zero and its previous hash to be 64 zeroes, then
checks each later block's previous-hash link, recalculated hash, and proof
against the previous block.

The checks have important gaps. The genesis block's own hash is not
recalculated, later block indexes are not checked for sequential ordering,
and transaction contents are not validated. Further, `/block/receive` checks
the block's recalculated hash but only invokes full-chain validation when its
previous hash does not match the receiver's current tip. A block that directly
extends that tip can therefore be appended without checking its proof or
index. These gaps mean the endpoint's `VALID` response should be understood
as passing the implemented checks, not as proof that a chain satisfies all
blockchain integrity rules.

Changing a hashed field in a non-genesis block without updating its hash
causes the recalculated hash check to fail. A changed previous hash can also
break the link from its successor. By contrast, the genesis-hash gap means
that changing genesis fields not otherwise checked may go undetected.

## 11. Security Analysis

At least five relevant security issues are:

1. **Sybil attack and node impersonation:** Peer registration accepts
   unauthenticated addresses, and there is no identity verification. An
   attacker able to register or control peer addresses can influence the
   information a node receives.
2. **Double-spending and transaction manipulation:** Transactions are not
   signed and no balances or spending rules are maintained. A sender field
   can be supplied arbitrarily, and the same value can be represented by
   multiple transactions.
3. **Man-in-the-middle attack:** Peer communication uses unencrypted HTTP.
   Network traffic can be observed or modified by an attacker with access to
   the communication path.
4. **Denial of service:** There is no authentication, rate limiting, request
   size limit, or mining resource limit. Repeated requests or expensive work
   can consume node resources.
5. **Weak validation:** Incoming blocks are not fully checked when they
   directly extend a node's current tip, and the chain validator omits
   genesis-hash, index-order, and transaction validation.
6. **Weak consensus and recovery:** The longest-valid-chain rule can be
   influenced by an attacker controlling enough reachable nodes, does not
   handle equal-length forks, and does not repair an invalid local chain using
   an equal-length valid peer copy.
7. **No private-key management:** There are no keys or digital signatures to
   establish transaction ownership or protect users' funds.

The implementation should only be run in a trusted local demonstration
environment until these issues are addressed.

## 12. Experimental Results

The project supports the following reproducible observations:

| Experiment | Expected observation |
| --- | --- |
| Start three processes and register peers | Each node reports its registered peer addresses |
| Submit a transaction to one registered node | It appears in that node's pending pool and is broadcast to peers that accept the request |
| Mine on that node | A block is returned with the pending transaction and mining reward; peers with a different genesis hash reject the direct block broadcast |
| Call `/nodes/resolve` on a peer with a shorter chain | It adopts the miner's strictly longer valid chain |
| Call `/blockchain/validate` on an unmodified locally mined or resolved chain | The chain passes the implemented validation checks |
| Alter a hashed field in a non-genesis block without recalculating its hash | Validation reports `INVALID` |
| Call `/nodes/resolve` with a strictly longer valid peer chain | The local chain is replaced by that peer chain |
| Try to recover an invalid chain from an equally long valid peer chain | The chain is not replaced; resolver only selects a strictly longer candidate |

The equal-length result is a known deviation from the assignment
demonstration's recovery expectation. Also, independent genesis blocks prevent
normal direct block propagation; the longest-chain resolver is the path that
lets a shorter peer catch up. A receiver can append a directly extending block
without fully checking its proof and index. These results follow from the
current implementation and should be included when evaluating its correctness.

## 13. Limitations

- Chain, pending transaction, and peer state are in memory only.
- Independently started nodes usually have different genesis hashes, so they
  reject direct broadcasts of each other's first mined block. A node must
  resolve from a strictly longer valid peer chain to adopt that history.
- The synchronization strategy cannot repair an invalid chain from an
  equal-length peer and does not resolve equal-length forks.
- Block reception and full-chain validation omit integrity checks described
  in Section 10.
- Transaction values and identities are not validated; there are no balances,
  signatures, or replay protection.
- HTTP communication and peer registration are unauthenticated and
  unencrypted.
- Failed broadcasts are ignored, with no acknowledgement or retry.
- The proof-of-work difficulty is fixed, and mining has no cancellation or
  resource controls.
- There is no persistent storage, rate limiting, formal test suite, or
  production deployment configuration.

## 14. Conclusion

The project demonstrates the core flow of a small blockchain application:
transactions enter a pending pool, a node performs a proof-of-work search,
blocks are linked by SHA-256 hashes, and peer nodes attempt to exchange
updates over HTTP. Its modular implementation makes these ideas
straightforward to explore.

It is not a secure or complete implementation of the assignment's full
validation and recovery goals. In particular, block reception needs
unconditional validation and synchronization needs an explicit strategy for
invalid and equal-length chains. Addressing those issues, then adding signed
transactions, persistence, peer authentication, and automated tests, would
be the next steps toward a more complete educational prototype.

## 15. References

1. Course assignment specification, `assignment_requirements.md`, Sections
   1–10 and 15.
2. Python Software Foundation, “hashlib — Secure hashes and message digests,”
   https://docs.python.org/3/library/hashlib.html
3. Pallets Projects, “Flask Documentation,”
   https://flask.palletsprojects.com/
4. Requests Documentation, “Requests: HTTP for Humans,”
   https://requests.readthedocs.io/
5. Nakamoto, S., “Bitcoin: A Peer-to-Peer Electronic Cash System,” 2008,
   https://bitcoin.org/bitcoin.pdf
