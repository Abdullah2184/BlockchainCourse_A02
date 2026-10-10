# Blockchain Network Assignment

A small, educational blockchain network implemented in Python. Each running
process hosts an HTTP API and keeps its own in-memory chain, pending
transactions, and peer list. Nodes broadcast transactions and attempt to
broadcast mined blocks over HTTP, and can ask peers for a longer valid chain.

This is a demonstration project, not a production cryptocurrency or a secure
distributed ledger. See [Current limitations](#current-limitations) before
using it outside a local learning environment.

## Guided overview

The main pieces are:

- [`block.py`](./block.py) serializes block data in a stable key order and
  calculates a SHA-256 hash, excluding the block's stored `hash` field.
- [`blockchain.py`](./blockchain.py) creates the genesis block, stores
  transactions, performs proof of work, checks chains, and requests chains from
  registered peers.
- [`app.py`](./app.py) exposes the Flask HTTP API and broadcasts transactions
  and newly mined blocks to registered peers.
- [`network.py`](./network.py) re-exports the app and its default blockchain
  instance for compatibility.
- [`main.py`](./main.py) starts one node. Each process gets a distinct node
  identifier and its own in-memory state.

The lifecycle is: start nodes → register peers → submit a transaction → mine a
block → inspect and validate chains → request synchronization. A mined block
includes the pending transactions and a reward transaction for the mining
node. The proof-of-work search hashes the previous proof, candidate proof, and
previous block hash until the result has four leading zeroes.

## Requirements and setup

- Python 3.10 or newer
- Dependencies are declared in [`pyproject.toml`](./pyproject.toml)

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux, activate it with:

```bash
source .venv/bin/activate
```

Install the project and its dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

## Run a three-node demonstration

Open three terminals in the project directory and start one node in each:

```bash
python main.py 5001
python main.py 5002
python main.py 5003
```

Each node listens on `0.0.0.0` at its selected port. The following HTTP
examples use Bash and `curl`.

Register each node with the other two:

```bash
curl -X POST http://localhost:5001/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5002","localhost:5003"]}'
curl -X POST http://localhost:5002/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5001","localhost:5003"]}'
curl -X POST http://localhost:5003/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5001","localhost:5002"]}'
```

Submit Alice's transaction to node 1. It is added locally and broadcast to its
registered peers:

```bash
curl -X POST http://localhost:5001/transaction -H "Content-Type: application/json" -d '{"sender":"Alice","receiver":"Bob","amount":100}'
```

Mine on node 1. The new block, including the transaction and mining reward, is
broadcast to the registered peers. Because each process creates its own
timestamped genesis block, the peers' genesis hashes usually differ; they
therefore reject node 1's directly broadcast block:

```bash
curl -X POST http://localhost:5001/mine
```

Ask nodes 2 and 3 to resolve against their peers. Since node 1 now has a
strictly longer valid chain, they can adopt its complete chain:

```bash
curl http://localhost:5002/nodes/resolve
curl http://localhost:5003/nodes/resolve
```

Inspect pending transactions and chain copies:

```bash
curl http://localhost:5001/transactions
curl http://localhost:5001/blockchain
curl http://localhost:5002/blockchain
curl http://localhost:5003/blockchain
```

Check a node's local chain and ask it to resolve conflicts with peers:

```bash
curl http://localhost:5001/blockchain/validate
curl http://localhost:5002/nodes/resolve
```

For the assignment's tampering demonstration, change a non-genesis block in a
node's local chain and call `/blockchain/validate`; a changed block hash or
broken link should be reported as `INVALID`. The current conflict resolver
only replaces a local chain with a *strictly longer* valid peer chain, so an
equally long healthy copy will not repair a tampered copy. See the report for
the full behavior and security analysis.

## API reference

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/transaction` | POST | Add a transaction and broadcast it to registered peers |
| `/transaction/broadcast` | POST | Add a received transaction unless it is already pending |
| `/transactions` | GET | Return the pending transactions |
| `/mine` | POST | Mine a block, add a mining reward, and broadcast the block |
| `/block/receive` | POST | Attempt to validate and append a peer's block |
| `/blockchain` | GET | Return the local chain and its length |
| `/blockchain/validate` | GET | Validate the local chain and return `VALID` or `INVALID` |
| `/nodes/register` | POST | Register one node or a list of node addresses |
| `/nodes/resolve` | GET | Request peer chains and adopt a longer valid chain |

## Current limitations

- All state is held in process memory; restarting a node loses its chain,
  pending transactions, and registered peers.
- Each process creates a timestamped genesis block independently, so nodes
  usually have different genesis hashes and reject each other's directly
  broadcast blocks. A node can catch up by adopting a strictly longer valid
  peer chain through `/nodes/resolve`.
- Chain synchronization uses a longest-valid-chain rule. It does not replace
  an equally long local chain, even when the local chain is invalid.
- Block reception does not fully validate proof of work and block sequence
  when a block directly extends the local tip. The full-chain validator also
  does not check the genesis block's hash, every block index, or transaction
  contents.
- Transactions are only checked for the presence of `sender`, `receiver`, and
  `amount`. There are no signatures, balance checks, or replay protection.
- Peer addresses and API requests are unauthenticated; traffic is plain HTTP.
- Network broadcast failures are ignored, and the sender does not confirm that
  peers accepted a broadcast.
- The proof of work is fixed at four leading zeroes and is based on proof
  values and the prior hash, not a hash of the new block header.
- The HTTP service is intended for local demonstrations, not internet-facing
  use. There is no rate limiting, persistent storage, or robust concurrent
  state management.

## Potential enhancements

1. Validate every incoming block unconditionally, including index, previous
   hash, proof of work, genesis rules, and transaction structure.
2. Define recovery behavior for invalid chains and equal-length forks; compare
   chain validity before length and make tie-breaking deterministic.
3. Add signed transactions, public-key identities, balance rules, and replay
   protection.
4. Persist chains and peer configuration, and protect shared state when
   handling concurrent API requests.
5. Add peer authentication, HTTPS, request limits, and explicit logging or
   reporting of failed broadcasts.
6. Add automated tests for multi-node propagation, malformed input, tampering,
   and synchronization edge cases.

## Report

See [REPORT.md](./REPORT.md) for the assignment report, covering the
architecture, implementation, validation, security analysis, experimental
results, limitations, and references.
