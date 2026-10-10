import argparse
import logging
import threading
from pathlib import Path

from app import create_app
from ledger.blockchain import Blockchain
 

def _synchronize_periodically(blockchain, stop_event):
    while not stop_event.is_set():
        try:
            report = blockchain.synchronize()
            for peer_report in report["peers"]:
                if peer_report["status"] == "error":
                    logging.warning("Periodic sync with %s failed: %s", peer_report["node"], peer_report["message"])
                elif peer_report["status"] == "rejected":
                    logging.warning("Periodic sync with %s was rejected: %s", peer_report["node"], peer_report.get("message"))
        except Exception:
            logging.exception("Periodic blockchain synchronization failed")
        if stop_event.wait(30):
            break


def main():
    parser = argparse.ArgumentParser(description="Run a blockchain node.")
    parser.add_argument("port", nargs="?", type=int, default=5000)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    data_dir = args.data_dir or project_dir / "data" / f"node-{args.port}"
    blockchain = Blockchain(data_dir=data_dir)
    blockchain.local_address = f"localhost:{args.port}"
    app = create_app(blockchain)

    stop_event = threading.Event()
    sync_thread = threading.Thread(
        target=_synchronize_periodically,
        args=(blockchain, stop_event),
        name=f"blockchain-sync-{args.port}",
        daemon=True,
    )
    sync_thread.start()
    try:
        app.run(host="0.0.0.0", port=args.port, debug=False)
    finally:
        stop_event.set()
        sync_thread.join(timeout=2)


if __name__ == "__main__":
    main()
