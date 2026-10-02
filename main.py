import hashlib #to create hashes for the blocks
import json #to encode and decode blocks when storing and loading
from time import time #to record the time of the block creation

class Blockchain():
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()

        self.new_block(prev_hash=1, proof=100) #create the genesis block

        def new_block(self, proof, prev_hash=None):
            block = {
                'index': len(self.chain) + 1,
                'timestamp': time(),
                'transactions': self.current_transactions,
                'proof': proof,
                'prev_hash': prev_hash or self.hash(self.chain[-1])
            }
            self.current_transactions = []
            self.chain.append(block)
            return block

        def new_transaction(self, sender, recipient, amount):
            self.current_transactions.append({
                'sender': sender,
                'recipient': recipient,
                'amount': amount
            })
            return self.last_block['index'] + 1 #return the index of the block that will hold this transaction

        @staticmethod #static methods are used when we don't need to access any properties of the class
        def hash(block):
            #json.dumps() converts the block to a JSON string, sort_keys=True ensures that the keys are always in the same order, and encode() converts the string to bytes
            block_string = json.dumps(block, sort_keys=True).encode() #encode the block to bytes
            return hashlib.sha256(block_string).hexdigest() #return the hash of the block

        @property #property decorator allows us to access the method as an attribute
        def last_block(self):
            return self.chain[-1] #return the last block in the chain


        def proof_of_work(self, last_proof):
            proof = 0
            while self.valid_proof(last_proof, proof) is False:
                proof += 1
            return proof

        @staticmethod
        def valid_proof(self, last_proof, proof):
            guess = f'{last_proof}{proof}'.encode() #encode combination of last proof and current proof to bytes
            guess_hash = hashlib.sha256(guess).hexdigest() #hash the guess
            return guess_hash[:4] == "0000" #return result of the check

        def valid_chain(self, chain):
            last_block = chain[0]
            for i in range(1, len(chain)):
                print(f'{last_block}')
                print(f'{block}')
                block = chain[i]

                #Check that the hash of the block is correct
                if block['prev_hash'] != self.hash(last_block):
                    return False
                
                #Check that the proof of work is correct
                if not self.valid_proof(last_block['proof'], block['proof']):
                    return False

                last_block = block
            return True

        def resolve_conflicts(self):
            #Resolves conflicts by replacing our chain with the longest one in the network (consensus algorithm)
