import json
from pathlib import Path

from eth_account import Account
from web3 import Web3


BASE = Path(__file__).resolve().parent


class LotteryClient:
    def __init__(self, rpc_url="http://127.0.0.1:8545", config_path=None):
        self.web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 8}))
        if not self.web3.is_connected():
            raise ConnectionError("Hardhat недоступний. Запустіть npm run node.")
        if self.web3.eth.chain_id != 31337:
            raise ValueError("Дозволена лише локальна мережа Hardhat 31337.")
        config = json.loads(Path(config_path or BASE / "contract_addresses.json").read_text(encoding="utf-8"))
        if config["chainId"] != 31337:
            raise ValueError("Некоректна мережа у файлі адрес.")
        self.contracts = {}
        for name in ("Lottery", "PrizeDistributor"):
            address = Web3.to_checksum_address(config[name])
            if not self.web3.eth.get_code(address):
                raise ValueError("Контракти не знайдено. Виконайте npm run deploy.")
            abi = json.loads((BASE / "abi" / f"{name}.json").read_text(encoding="utf-8"))
            self.contracts[name] = self.web3.eth.contract(address=address, abi=abi)
        self.lottery = self.contracts["Lottery"]
        self.distributor = self.contracts["PrizeDistributor"]
        if self.lottery.functions.distributor().call() != self.distributor.address:
            raise ValueError("Адреси контрактів не пов'язані. Повторіть експорт.")
        if self.distributor.functions.lottery().call() != self.lottery.address:
            raise ValueError("Некоректний зв'язок контрактів.")
        self.account = None

    def set_key(self, private_key):
        self.account = None
        try:
            account = Account.from_key(private_key.strip())
        except Exception:
            raise ValueError("Некоректний приватний ключ.") from None
        self.account = account
        return account.address

    def forget_key(self):
        self.account = None

    def snapshot(self):
        f = self.lottery.functions
        d = self.distributor.functions
        address = self.account.address if self.account else None
        return {
            "state": f.state().call(),
            "ticket": f.ticketPrice().call(),
            "pool": f.prizePool().call(),
            "participants": f.getParticipants().call(),
            "owner": d.owner().call(),
            "winner": d.winner().call(),
            "claimable": d.claimablePrize().call(),
            "prize": d.prize().call(),
            "draw_block": d.drawBlock().call(),
            "block": self.web3.eth.block_number,
            "account": address,
            "balance": self.web3.eth.get_balance(address) if address else 0,
            "contribution": f.contributions(address).call() if address else 0,
        }

    def send(self, function, value=0):
        if self.account is None:
            raise ValueError("Спочатку введіть приватний ключ тестового акаунта.")
        address = self.account.address
        transaction = function.build_transaction({
            "from": address,
            "value": value,
            "chainId": 31337,
            "nonce": self.web3.eth.get_transaction_count(address, "pending"),
            "gasPrice": self.web3.eth.gas_price,
        })
        transaction["gas"] = int(transaction["gas"] * 1.2)
        signed = self.account.sign_transaction(transaction)
        tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt["status"] != 1:
            raise RuntimeError("Транзакцію відхилено блокчейном.")
        return Web3.to_hex(tx_hash)

    def enter(self):
        return self.send(self.lottery.functions.enter(), self.lottery.functions.ticketPrice().call())

    def request_draw(self):
        return self.send(self.distributor.functions.requestDraw())

    def finalize_draw(self):
        return self.send(self.distributor.functions.finalizeDraw())

    def claim(self, recipient):
        return self.send(self.distributor.functions.claimPrize(Web3.to_checksum_address(recipient)))

    def cancel(self):
        return self.send(self.distributor.functions.cancelOpenLottery())

    def cancel_expired(self):
        return self.send(self.distributor.functions.cancelExpiredDraw())

    def refund(self, recipient):
        return self.send(self.lottery.functions.refund(Web3.to_checksum_address(recipient)))

    def mine_demo_blocks(self):
        if self.web3.eth.chain_id != 31337:
            raise ValueError("Дозволена лише локальна мережа Hardhat.")
        response = self.web3.provider.make_request("hardhat_mine", ["0x3"])
        if "error" in response:
            raise RuntimeError("Не вдалося створити тестові блоки.")
        return "Створено 3 порожні блоки Hardhat."
