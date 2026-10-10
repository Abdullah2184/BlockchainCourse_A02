import json
from pathlib import Path

from ledger.constants import STATE_VERSION


class NodeStateStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "state.json"

    def exists(self) -> bool:
        return self.state_path.is_file()

    def load(self) -> dict:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to load node state from {self.state_path}: {error}") from error

        required = {"version", "node_id", "nodes", "users", "current_transactions", "chain", "balances"}
        if not isinstance(state, dict) or set(state) != required:
            raise ValueError(f"Node state at {self.state_path} has an unsupported format")
        if state["version"] != STATE_VERSION:
            raise ValueError(f"Node state at {self.state_path} has unsupported version {state['version']!r}")
        return state

    def save(self, state: dict) -> None:
        payload = {"version": STATE_VERSION, **state}
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        temporary_path.replace(self.state_path)
