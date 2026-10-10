from flask import Flask

from api.blocks import create_blocks_blueprint
from api.nodes import create_nodes_blueprint
from api.transactions import create_transaction_blueprint
from api.users import create_users_blueprint
from ledger.blockchain import Blockchain


def create_app(blockchain: Blockchain) -> Flask:
    app = Flask(__name__)
    app.register_blueprint(create_transaction_blueprint(blockchain))
    app.register_blueprint(create_blocks_blueprint(blockchain))
    app.register_blueprint(create_users_blueprint(blockchain))
    app.register_blueprint(create_nodes_blueprint(blockchain))
    app.config["BLOCKCHAIN"] = blockchain
    return app
