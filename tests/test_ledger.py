import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from block import hash_block
from ledger.blockchain import Blockchain
from ledger.validation import validate_chain


class BlockchainTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = Path(self.temp_dir.name) / "node"
        self.blockchain = Blockchain(self.data_dir)

    def test_genesis_is_deterministic_and_mined_header_meets_difficulty(self):
        other = Blockchain(Path(self.temp_dir.name) / "other")
        self.assertEqual(self.blockchain.chain[0], other.chain[0])

        block = self.blockchain.mine_pending_block()

        self.assertEqual(block["hash"], hash_block({key: value for key, value in block.items() if key != "hash"}))
        self.assertTrue(block["hash"].startswith("0000"))
        self.assertTrue(validate_chain(self.blockchain.chain, self.blockchain.users))

    def test_balances_are_validated_and_restored_from_the_chain(self):
        with patch.dict(os.environ, {"BLOCKCHAIN_ADMIN_TOKEN": "test-secret"}):
            alice_id, _ = self.blockchain.register_user("Alice")
            bob_id, _ = self.blockchain.register_user("Bob")
            self.blockchain.new_admin_credit(alice_id, 100, "test-secret")
            self.blockchain.mine_pending_block()
            self.blockchain.new_transaction(alice_id, bob_id, 25)
            self.blockchain.mine_pending_block()

            restored = Blockchain(self.data_dir)

            self.assertEqual(restored.balances[alice_id], 75)
            self.assertEqual(restored.balances[bob_id], 25)
            with self.assertRaisesRegex(ValueError, "Insufficient available balance"):
                restored.new_transaction(alice_id, bob_id, 76)

    def test_rehashed_block_with_insufficient_proof_is_invalid(self):
        self.blockchain.mine_pending_block()
        block = self.blockchain.chain[-1]
        block["proof"] += 1
        block["hash"] = hash_block({key: value for key, value in block.items() if key != "hash"})

        self.assertFalse(self.blockchain.valid_chain(self.blockchain.chain))

    def test_state_merge_rejects_invalid_chain_without_replacing_local_state(self):
        source = Blockchain(Path(self.temp_dir.name) / "source")
        source.mine_pending_block()
        valid_tip = self.blockchain.last_block["hash"]
        invalid_state = source.export_state()
        invalid_state["chain"][-1]["proof"] += 1

        with self.assertRaisesRegex(ValueError, "invalid blockchain"):
            self.blockchain.merge_state(invalid_state)
        self.assertEqual(self.blockchain.last_block["hash"], valid_tip)

    def test_user_api_uses_explicit_node_and_returns_uuid(self):
        client = create_app(self.blockchain).test_client()

        response = client.post("/users/register", json={"display_name": "Alice"})

        self.assertEqual(response.status_code, 201)
        user_id = response.get_json()["user_id"]
        self.assertTrue(self.blockchain._valid_user_id(user_id))
        self.assertEqual(response.get_json()["balance"], 0)


if __name__ == "__main__":
    unittest.main()
