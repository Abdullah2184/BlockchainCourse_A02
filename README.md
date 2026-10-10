# Educational Blockchain Network

A Python learning project that runs independent HTTP nodes with a SHA-256
proof-of-work ledger, UUID-based user records, integer account balances, and
peer synchronization. Each node persists its own state to a separate JSON
file.

This prototype is for local learning and experimentation only. User IDs are
not credentials, transactions are not signed, peer traffic is unauthenticated
HTTP, and it must not be used to hold real funds.

## Project structure

- [`block.py`](./block.py): deterministic JSON serialization and SHA-256 block
  hashing.
- [`ledger/blockchain.py`](./ledger/blockchain.py): ledger state, transaction
  pool, mining, user/peer updates, state merge, and balance commits.
- [`ledger/validation.py`](./ledger/validation.py): UUID, peer, transaction,
  block-chain and balance validation, plus cumulative-work ranking.
- [`ledger/storage.py`](./ledger/storage.py): versioned, atomic JSON state
  persistence using `pathlib`.
- [`ledger/synchronization.py`](./ledger/synchronization.py): peer state
  requests and synchronization reports.
- [`api/transactions.py`](./api/transactions.py): transaction submission and
  transaction-pool routes.
- [`api/blocks.py`](./api/blocks.py): mining, block reception, chain viewing,
  and validation routes.
- [`api/users.py`](./api/users.py): UUID user registry and protected credit
  route.
- [`api/nodes.py`](./api/nodes.py): peer registry and state synchronization
  routes.
- [`api/helpers.py`](./api/helpers.py): common JSON parsing and peer broadcast
  reporting.
- [`app.py`](./app.py): Flask application factory that assembles the route
  blueprints.
- [`main.py`](./main.py): command-line node startup and periodic synchronization.

## Setup

Requires Python 3.10 or newer.

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

For macOS or Linux, activate with:

```bash
source .venv/bin/activate
```

Install the project and its dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

## Start three nodes

Each node uses a data directory derived from its port by default:
`data/node-5001/state.json`, `data/node-5002/state.json`, and
`data/node-5003/state.json`. State survives restarts. Set the same
administrator token in each node's shell before starting it if administrator
credits are required.

```bash
export BLOCKCHAIN_ADMIN_TOKEN='use-a-local-demo-secret'
python main.py 5001
```

Run the same export and start command in two other terminals, changing the
port to `5002` and `5003`. On PowerShell, set the variable with
`$env:BLOCKCHAIN_ADMIN_TOKEN = 'use-a-local-demo-secret'`.

An alternate state location can be selected with `--data-dir`:

```bash
python main.py 5001 --data-dir ./node-data/node-5001
```

Start all nodes before registering peers. Register the other two nodes at each
node; request failures and peer rejections are returned in the response's
`broadcast` report.

```bash
curl -X POST http://localhost:5001/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5002","localhost:5003"]}'
curl -X POST http://localhost:5002/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5001","localhost:5003"]}'
curl -X POST http://localhost:5003/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5001","localhost:5002"]}'
```

## Create users, fund, transfer, and mine

User display names are labels only. Registration returns a UUID `user_id`;
transactions must refer to that ID. New accounts begin with a zero balance.
For this demo, fund an account using the administrator endpoint, then mine to
commit the credit. The administrator token must be configured consistently on
every node so all nodes can validate the credit when validating a block.

```bash
curl -X POST http://localhost:5001/users/register -H "Content-Type: application/json" -d '{"display_name":"Alice"}'
```

Copy the returned `user_id` into the credit request:

```bash
curl -X POST http://localhost:5001/users/credit -H "Content-Type: application/json" -H "X-Admin-Token: use-a-local-demo-secret" -d '{"user_id":"ALICE_UUID","amount":100}'
curl -X POST http://localhost:5001/mine
```

Register another user (for example, Bob) and copy both UUIDs. Submit a
transfer and mine a block to settle it:

```bash
curl -X POST http://localhost:5001/transaction -H "Content-Type: application/json" -d '{"sender_id":"ALICE_UUID","recipient_id":"BOB_UUID","amount":25}'
curl -X POST http://localhost:5001/mine
```

The API reserves pending outgoing amounts when checking available balance.
Settled balances are recalculated from the accepted chain; a rejected block
does not change a node's balances.

## Inspect and synchronize nodes

```bash
curl http://localhost:5001/users
curl http://localhost:5001/transactions
curl http://localhost:5001/blockchain
curl http://localhost:5001/blockchain/validate
curl http://localhost:5002/nodes
curl http://localhost:5002/nodes/resolve
```

Nodes use the same deterministic genesis block, so compatible blocks can be
broadcast directly. Synchronization validates peer registries and complete
chains, then prefers the valid chain with greater cumulative proof-of-work
(using a deterministic tip-hash tie-break). Invalid incoming block/state data
is rejected and prompts an attempt to synchronize from registered peers.
Periodic synchronization runs at startup and every 30 seconds.

## Run tests

Run the standard-library unit tests from the project root:

```bash
python -m unittest discover -s tests -v
```

## API reference

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/transaction` | POST | Create a transfer using sender/recipient UUIDs; broadcast it to peers |
| `/transaction/broadcast` | POST | Validate and store a peer's pending transaction |
| `/transactions` | GET | View the pending transaction pool |
| `/mine` | POST | Mine pending transactions with one node reward and broadcast the block |
| `/block/receive` | POST | Validate and append a peer block |
| `/blockchain` | GET | View the node's current chain |
| `/blockchain/validate` | GET | Validate hashes, work, ordering, rewards, and transactions |
| `/users/register` | POST | Create a UUID account with an initial zero balance |
| `/users` | GET | View registered users and settled balances |
| `/users/update` | POST | Merge a peer's validated user records |
| `/users/credit` | POST | Create an admin-authorized credit; requires `X-Admin-Token` |
| `/nodes/register` | POST | Add one or more `host:port` peers |
| `/nodes` | GET | View registered peers |
| `/nodes/update` | POST | Merge peer addresses |
| `/state` | GET | Export the peer list, user registry, and blockchain for sync |
| `/nodes/resolve` | GET | Request and validate state from peers |

## Review findings and limitations

- UUIDs identify accounts, but they do not authenticate their owners. The
  transfer API accepts a sender UUID without a signature or other proof of
  control, so a caller can attempt to spend another account's balance.
- Administrator credits rely on a shared secret configured on every node.
  A credit is accepted during chain validation only when the node has the
  matching secret; do not expose the token or endpoint to untrusted networks.
- Peer registration accepts unauthenticated peer addresses and synchronization
  trusts valid cumulative-work chains. A malicious peer or network participant
  can influence peer lists or availability; this is not a Byzantine consensus
  protocol.
- Peer communication uses HTTP without transport encryption. There is no
  request authentication, rate limiting, or robust public deployment
  configuration.
- Persistent state is local JSON, not a replicated database. Its atomic rename
  prevents partial-file writes in ordinary operation, but it does not provide
  multi-process locking for two node processes pointed at the same data
  directory. Use a unique directory per node.
- Proof-of-work difficulty is fixed at four leading zeroes. There is no
  difficulty adjustment, transaction fee, or finality.
- Periodic sync reports peer failures but does not retry individual broadcast
  messages with a durable queue.

Potential improvements include signed transactions with key management,
authenticated/encrypted peer connections, stricter peer admission, rate
limits, a database-backed state store, formal fork/finality rules, and
automated multi-process tests.
