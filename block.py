import hashlib
import json


def hash_block(block):
    payload = {key: value for key, value in block.items() if key != "hash"}
    block_string = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(block_string).hexdigest()
