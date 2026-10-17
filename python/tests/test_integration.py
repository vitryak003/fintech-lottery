import unittest

from support import LocalFixture, LotteryClient


class IntegrationTests(unittest.TestCase):
    def test_ignition_contracts_and_abi(self):
        client = LotteryClient()
        data = client.snapshot()
        self.assertEqual(data["ticket"], 10**16)
        self.assertEqual(data["state"], 0)
        self.assertEqual(data["participants"], [])

    def test_signed_entry_draw_and_payment(self):
        fixture = LocalFixture()
        self.addCleanup(fixture.close)
        fixture.populate()
        client = fixture.client
        self.assertEqual(client.snapshot()["pool"], 2 * 10**16)
        client.request_draw()
        client.mine_demo_blocks()
        client.finalize_draw()
        data = client.snapshot()
        self.assertIn(data["winner"], [account.address for account in fixture.accounts[1:3]])
        winner = next(account for account in fixture.accounts if account.address == data["winner"])
        client.set_key(winner.key.hex())
        recipient = fixture.accounts[3].address
        before = fixture.web3.eth.get_balance(recipient)
        client.claim(recipient)
        self.assertEqual(fixture.web3.eth.get_balance(recipient), before + 2 * 10**16)
        self.assertEqual(client.snapshot()["claimable"], 0)
        with self.assertRaises(Exception):
            client.claim(recipient)

    def test_cancel_and_refund(self):
        fixture = LocalFixture()
        self.addCleanup(fixture.close)
        fixture.populate()
        fixture.client.cancel()
        recipient = fixture.accounts[3].address
        before = fixture.web3.eth.get_balance(recipient)
        for account in fixture.accounts[1:3]:
            fixture.client.set_key(account.key.hex())
            fixture.client.refund(recipient)
        self.assertEqual(fixture.web3.eth.get_balance(recipient), before + 2 * 10**16)
        self.assertEqual(fixture.client.snapshot()["pool"], 0)

    def test_permissions_and_invalid_key(self):
        fixture = LocalFixture()
        self.addCleanup(fixture.close)
        fixture.populate()
        fixture.client.set_key(fixture.accounts[1].key.hex())
        with self.assertRaises(Exception):
            fixture.client.request_draw()
        with self.assertRaises(ValueError):
            fixture.client.set_key("not-a-private-key")
        self.assertIsNone(fixture.client.account)
        with self.assertRaises(ValueError):
            fixture.client.enter()


if __name__ == "__main__":
    unittest.main()
