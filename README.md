# Blockchain Network Assignment

This project implements a simple three-node blockchain network in Python using Flask and requests.

## Requirements

- Python 3.10+
- Flask
- requests

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Start nodes

Run three independent nodes on different ports:

```bash
python main.py 5001
python main.py 5002
python main.py 5003
```

## Register nodes

Use the following request to register peers:

```bash
curl -X POST http://localhost:5001/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5002","localhost:5003"]}'
curl -X POST http://localhost:5002/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5001","localhost:5003"]}'
curl -X POST http://localhost:5003/nodes/register -H "Content-Type: application/json" -d '{"nodes":["localhost:5001","localhost:5002"]}'
```

## Create a transaction

```bash
curl -X POST http://localhost:5001/transaction -H "Content-Type: application/json" -d '{"sender":"Alice","receiver":"Bob","amount":100}'
```

## Mine a block

```bash
curl -X POST http://localhost:5001/mine
```

## View the blockchain

```bash
curl http://localhost:5001/blockchain
curl http://localhost:5002/blockchain
curl http://localhost:5003/blockchain
```

## Validate and synchronize

```bash
curl http://localhost:5001/blockchain/validate
curl http://localhost:5001/nodes/resolve
```

## Project structure

The blockchain logic has been split into modular components for easier maintenance:

- `block.py` – hashing helpers for block data
- `blockchain.py` – blockchain validation, mining, and peer synchronization logic
- `app.py` – Flask routes and API endpoints
- `network.py` – compatibility wrapper that re-exports the app and blockchain instance
- `main.py` – node startup script

## Notes

- The project implements a simple SHA-256-based blockchain.
- Blocks are mined using a proof-of-work requirement of four leading zeroes.
- Each node keeps a local copy of the blockchain and can synchronize with peers.
- The chain can be validated to detect tampering.
 