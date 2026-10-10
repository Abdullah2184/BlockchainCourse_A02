# Blockchain Network Assignment Report

## 1. Introduction

This project is a Python educational prototype of a peer-to-peer blockchain
network. Each node exposes an HTTP API, maintains a local copy of the chain,
stores UUID-identified accounts and integer balances, validates and mines
blocks, broadcasts updates, and periodically synchronizes from peers.

The implementation demonstrates ledger and networking concepts; it is not a
production cryptocurrency, a secure payment system, or a Byzantine-fault
tolerant consensus protocol.

## 2. Blockchain Architecture

Each node maintains a deterministic genesis block, ordered blocks linked by
SHA-256 hashes, pending transactions, a user registry, peer addresses, and
balances derived from the chain. A transaction has a UUID transaction
identifier, type, sender ID, recipient ID, and positive integer amount.
Transfers require a registered sender and recipient and sufficient available
balance. New accounts have zero balance.

Mining adds pending transactions and exactly one fixed reward of one unit to
the block's miner account. The node validates the candidate chain and
recomputes balances before committing its new local state. It then broadcasts
the block to peers.

## 3. System Architecture

Implementation responsibilities are separated into modules:

- `block.py`: stable JSON representation and SHA-256 block hashing.
- `ledger/constants.py`: fixed proof-of-work difficulty, system account,
  genesis previous hash, and state schema version.
- `ledger/validation.py`: account and peer address checks, transaction
  authorization, whole-chain validation, balance calculation, and
  cumulative-work ranking.
- `ledger/storage.py`: `NodeStateStore`, a versioned JSON store using
  `pathlib` paths and atomic temporary-file replacement.
- `ledger/synchronization.py`: peer state requests, failures/rejection reports,
  and synchronization orchestration.
- `ledger/blockchain.py`: the stateful `Blockchain` application service,
  coordinating account/peer registration, transactions, mining, persistence,
  validation, and state merge.
- `api/helpers.py`: shared request parsing, outbound broadcasts, and
  synchronization on rejected payloads.
- `api/transactions.py`, `api/blocks.py`, `api/users.py`, and `api/nodes.py`:
  focused Flask blueprints for the HTTP resources.
- `app.py`: Flask application factory that assembles the blueprints around an
  explicitly supplied `Blockchain` instance.
- `main.py`: command-line startup, per-node data directory selection, and
  periodic synchronization.

Each node should use a unique data directory. By default the command-line
entry point uses `data/node-{port}/state.json`; `--data-dir` allows a custom
path. The persisted state includes node identity, peers, users, pending
transactions, chain, and derived balances.

## 4. Python Implementation

The `Blockchain` service serializes mutations through a reentrant lock. It
delegates persistence to `NodeStateStore` and validation to standalone
functions in `ledger/validation.py`. HTTP behavior is kept out of that service
and split across Flask blueprints. `create_app(blockchain)` requires a node
instance, making ownership of persistent state explicit and avoiding implicit
shared process-global node state.

State files carry a schema version. Writes serialize to a neighboring
temporary file and replace `state.json` after the write completes. Loads
check the schema, node and user identifiers, peer formats, chain validity,
pending transaction validity, and that stored balances match the balances
recalculated from the chain. Invalid or unsupported persisted data raises an
error instead of silently starting a replacement identity.

## 5. Block Structure

Every block contains:

| Field | Meaning |
| --- | --- |
| `index` | Sequential chain position, beginning at zero |
| `timestamp` | Block creation time |
| `miner_id` | UUID of the account receiving the block reward |
| `transactions` | Transfers, authorized credits, and one reward |
| `proof` | Nonce-like integer included in the hashed block data |
| `previous_hash` | Hash of the preceding block |
| `hash` | SHA-256 digest of sorted JSON for all other block fields |

The genesis block has a fixed timestamp, proof `0`, no transactions, and a
previous hash of 64 zeroes. Having the same genesis block allows independent
nodes to accept compatible block broadcasts.

## 6. Transaction Processing

`POST /users/register` creates a UUID account with a display name and zero
balance. Display names are labels, not account identifiers or proof of
ownership. `POST /transaction` accepts `sender_id`, `recipient_id`, and
`amount`. It assigns a transaction UUID, validates the identifiers and
positive integer amount, reserves pending outgoing value when checking
available balance, persists the pending transaction, and reports its peer
broadcast results.

`POST /transaction/broadcast` checks the transaction identifier against both
the pending pool and chain, verifies users and amount, and repeats balance
checks before storing a new pending transaction. Duplicate transaction IDs
are not added.

Optional funding is provided by `POST /users/credit`. The operator must set
`BLOCKCHAIN_ADMIN_TOKEN` on every node and provide the matching
`X-Admin-Token` header. The credit transaction is authenticated with an HMAC
over its ID, recipient ID, and amount, and is then broadcast and committed
only as part of a mined block. Every validating node must have the same
administrator token configured for blocks containing credits to validate.

## 7. Proof of Work

Mining creates a candidate block header with index, timestamp, miner UUID,
transactions, proof, and previous block hash. It increments the proof until
the SHA-256 hash of the complete candidate block data has four leading zeroes.
That candidate hash is stored as the block hash. Chain validation recalculates
the hash from the stored block data and checks the difficulty condition.

The difficulty is a fixed constant. This implementation has no dynamic
difficulty adjustment and no mining cancellation or resource limit.

## 8. P2P Communication

Nodes expose Flask routes for transactions, blocks, user registries, node
registries, and state export. Outbound HTTP calls use the `requests` library
with a timeout. Broadcast replies are reported per peer as accepted, rejected,
or error, including HTTP status when available. Rejections trigger a
synchronization attempt.

`GET /state` exports a peer's chain, user registry, and node addresses.
`GET /nodes/resolve` requests this state from registered peers, validates it,
and merges accepted updates. The application starts a synchronization worker
on process startup and repeats it every 30 seconds.

## 9. Consensus/Synchronization Mechanism

Peer state is structurally checked before merge. User IDs and records must
have valid formats and must not conflict with existing records; peer
addresses must be valid host-and-port values. Candidate chains are validated
against the merged user registry. A locally invalid chain can be replaced
with a valid peer chain. Otherwise, the node compares cumulative proof-of-work
and uses the tip hash as a deterministic tie-break.

This is a better-defined fork-choice heuristic than chain length alone, but
it is not consensus in the distributed-systems sense. Peers are unauthenticated,
there is no quorum or finality, and the model does not prevent a sufficiently
powerful or dishonest peer group from influencing the selected history.

## 10. Blockchain Validation

The validator checks the fixed genesis block, each block's sequence index,
previous-hash link, recomputed SHA-256 hash, and four-zero proof-of-work
threshold. It also checks that the miner account is registered and that each
block contains exactly one reward of one unit for that miner.

Transactions are checked for required fields, UUID transaction IDs, duplicate
IDs, positive integer amounts, registered account IDs, sufficient balance,
and authorized credit HMACs. Balances are replayed in order from the chain.
Incoming blocks are appended only if the full candidate chain validates.
Rejected blocks do not commit balances; balances are recomputed only after a
valid block is accepted.

## 11. Security Analysis

1. **Account impersonation and unauthorized transfers:** UUIDs identify
   accounts but do not prove who controls them. The transfer endpoint accepts
   a sender UUID without a digital signature, so a caller can attempt to
   transfer another user's funds. This is the most significant remaining
   transaction-security gap.
2. **Administrator-token compromise:** The same shared secret is used by all
   validating nodes. A leaked token permits authorized-looking credit
   transactions, and differing tokens cause nodes to reject credit-bearing
   blocks.
3. **Peer impersonation and Sybil behavior:** Peer registration and state
   exchange do not authenticate node identities. A malicious peer can provide
   conflicting or strategically selected valid chain state.
4. **Man-in-the-middle attacks:** Node communication is plain HTTP without
   transport encryption, so traffic can be observed or modified on the
   network path.
5. **Denial of service:** There is no rate limit or request-size policy.
   Mining is CPU work and incoming API requests are not authenticated.
6. **Replay and transaction-level authorization:** UUID transaction IDs
   prevent accidental duplicate inclusion in one chain, but there is no user
   signature or nonce proving that a transfer was authorized by its sender.
7. **Persistence scope:** Atomic replacement protects against ordinary
   partial writes but does not coordinate multiple processes pointed at the
   same node directory. Separate node directories are required.

The prototype should only be used in a trusted local environment.

## 12. Experimental Results

The implementation was exercised with standard-library unit tests and
three in-process Flask test clients using separate temporary directories:

| Experiment | Observed result |
| --- | --- |
| Register peers and a UUID account | User records propagate to registered peers |
| Attempt credit with wrong admin token | Request is rejected with HTTP 403 |
| Authorize credit, mine, and broadcast block | Peers accept the block and derive the same funded balance |
| Submit transfer over available balance or malformed recipient | Request is rejected |
| Mine a valid transfer | Each peer's derived sender balance is reduced consistently |
| Restart each `Blockchain` from its own directory | Node identity, ledger, and balances are restored |
| Submit a block with an invalid proof | Receiver rejects it and retains the settled balance |
| Synchronize a new node from an existing peer | Valid chain, users, and peer state are imported |
| Recalculate a block hash after changing its proof | Chain validation still rejects it because the proof does not meet the required difficulty |

The committed unit tests cover deterministic genesis/mining hashes, balance
replay and persistence, invalid proof rejection, state-merge rejection, and
the user-registration API. The three-node test-client check also exercised
peer registration, user propagation, authorized credit, transfer/block
broadcasts, restart persistence, and a late node's state synchronization.
These checks do not constitute a real multi-process network or a comprehensive
security test suite.

## 13. Limitations

- No cryptographic user keys or signatures protect transfers; account IDs can
  be copied and used by arbitrary callers.
- Admin credits depend on a shared token, which must match on all nodes.
- HTTP peers and peer registration are unauthenticated. Peer discovery and
  trust are not resilient to malicious participants.
- The JSON store is per node and requires each node process to use a unique
  data directory. It is not a database and has no cross-process locking.
- Fork choice uses cumulative proof-of-work plus a deterministic hash tie
  break, without quorum, finality, or Byzantine agreement.
- Difficulty is fixed at four leading zeroes; there are no fee rules,
  adjustable difficulty, mining limits, or durable retry queues.
- Periodic synchronization is best-effort and depends on reachable peers.
- The focused integration checks use in-process test clients; a complete
  automated test suite and deployment hardening remain future work.

## 14. Conclusion

The application now separates HTTP route concerns from ledger behavior and
separates validation, persistence, and synchronization from the central
blockchain service. The focused modules make the implementation easier to
inspect and extend. Nodes persist independent state, validate transactions
against ledger-derived balances, report broadcast results, and synchronize
validated peer state using cumulative work rather than length alone.

These improvements do not make the prototype safe for real funds. Signed
transactions, authenticated peer communication, a durable multi-process store,
formal consensus/finality, and a broad automated test suite are the most
important next steps.

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
