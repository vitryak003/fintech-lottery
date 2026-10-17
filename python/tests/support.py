import json
import sys
import tempfile
from pathlib import Path

from eth_account import Account
from web3 import Web3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import LotteryClient


class LocalFixture:
    def __init__(self):
        self.web3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
        if self.web3.eth.chain_id != 31337:
            raise RuntimeError("Tests require local Hardhat")
        self.accounts = [Account.create() for _ in range(4)]
        self.owner = self.accounts[0]
        for account in self.accounts:
            response = self.web3.provider.make_request("hardhat_setBalance", [account.address, hex(10**20)])
            if "error" in response:
                raise RuntimeError("Cannot fund test account")
        self.temp = tempfile.TemporaryDirectory()
        self.lottery = self.deploy("Lottery", [10**16])
        self.distributor = self.deploy("PrizeDistributor", [self.lottery.address])
        self.transact(self.lottery.functions.setDistributor(self.distributor.address))
        self.config = Path(self.temp.name) / "contract_addresses.json"
        self.config.write_text(json.dumps({
            "chainId": 31337,
            "Lottery": self.lottery.address,
            "PrizeDistributor": self.distributor.address,
        }), encoding="utf-8")
        self.client = LotteryClient(config_path=self.config)
        self.client.set_key(self.owner.key.hex())

    def artifact(self, name):
        for file in Path("artifacts").rglob(name + ".json"):
            data = json.loads(file.read_text(encoding="utf-8"))
            if data.get("contractName") == name and "bytecode" in data:
                return data
        raise RuntimeError("Artifact missing")

    def transact(self, function):
        tx = function.build_transaction({
            "from": self.owner.address,
            "nonce": self.web3.eth.get_transaction_count(self.owner.address),
            "chainId": 31337,
            "gasPrice": self.web3.eth.gas_price,
        })
        signed = self.owner.sign_transaction(tx)
        receipt = self.web3.eth.wait_for_transaction_receipt(self.web3.eth.send_raw_transaction(signed.raw_transaction))
        if receipt["status"] != 1:
            raise RuntimeError("Test transaction failed")
        return receipt

    def deploy(self, name, args):
        artifact = self.artifact(name)
        factory = self.web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
        receipt = self.transact(factory.constructor(*args))
        return self.web3.eth.contract(address=receipt["contractAddress"], abi=artifact["abi"])

    def populate(self):
        for account in self.accounts[1:3]:
            self.client.set_key(account.key.hex())
            self.client.enter()
        self.client.set_key(self.owner.key.hex())

    def close(self):
        self.client.forget_key()
        self.temp.cleanup()
