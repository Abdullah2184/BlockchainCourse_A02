1. Fix the proof of work to use the current block hash (header data), not the previous block proof.
2. No need strict backward compatibility. Remove unnecessary redirects. Maintain code functionality.
3. Transactions should be based on unique identifiers, not names, and these identifiers should be stored in each 
    node,  broadcast when updated and cross-checked when transactions are created and broadcast.
4. Add failed broadcast reports, so nodes know if their block or data has been rejected. If user list, node list 
    or blockchain has been rejected, it can request other nodes for their versions so that it can update its own. This update functionality should run periodically to so that valid users are not rejected on outdated nodes.
5. Add lightweight persistent storage to validate and manage user balances. This data is individual 
    to each node and should be updated after each transaction block is created. Functions more similar to a bank balance, not like the bitcoin UTXO-model. Rejected blocks should revert updates (perform the reverse) since these transactions have not been performed.
6. Lightweight storage should also be used to allow nodes to preserve state across sessions. Should also be able 
    to request for updated user lists, node lists and blockchain to get upto speed in a new session. All this will be used to update its own storage.
7. Improve resolve functionality for all broadcasts (user lists, node lists, blockchain, etc). Use a better, more 
    secure approach than just length checks.