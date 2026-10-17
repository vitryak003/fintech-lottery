import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from support import LocalFixture
from app import LotteryApp


class GuiTests(unittest.TestCase):
    def wait(self, app):
        deadline = time.monotonic() + 45
        while app.busy and time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.02)
        app.root.update()
        self.assertFalse(app.busy, "GUI operation timed out")
        self.assertIsNone(app.last_error)

    def load_account(self, app, account):
        app.key_entry.insert(0, account.key.hex())
        self.assertEqual(str(app.key_entry.cget("show")), "*")
        app.load_key()
        self.assertEqual(app.key_entry.get(), "")
        self.wait(app)

    def test_gui_signed_lottery_flow(self):
        fixture = LocalFixture()
        self.addCleanup(fixture.close)
        root = tk.Tk()
        app = LotteryApp(root)
        self.addCleanup(lambda: app.close() if not app.closed else None)
        app.client = fixture.client
        app.refresh()
        with patch("app.messagebox.showerror"):
            self.wait(app)
            for account in fixture.accounts[1:3]:
                self.load_account(app, account)
                app.join_button.invoke()
                self.wait(app)
            self.assertEqual(app.values["count"].get(), "2")
            self.assertTrue(app.participant_list.winfo_ismapped())
            self.assertGreaterEqual(app.participant_list.winfo_width(), 350)
            self.load_account(app, fixture.owner)
            app.draw_button.invoke()
            self.wait(app)
            app.mine_button.invoke()
            self.wait(app)
            app.finish_button.invoke()
            self.wait(app)
            winner = app.client.snapshot()["winner"]
            account = next(item for item in fixture.accounts if item.address == winner)
            self.load_account(app, account)
            app.claim_button.invoke()
            self.wait(app)
            self.assertEqual(app.client.snapshot()["claimable"], 0)
            self.assertEqual(app.key_entry.get(), "")
            log = app.log.get("1.0", "end")
            for item in fixture.accounts:
                self.assertNotIn(item.key.hex(), log)
            try:
                from PIL import ImageGrab
                directory = Path("test-results")
                directory.mkdir(exist_ok=True)
                root.update()
                ImageGrab.grab().save(directory / "lottery-window.png")
            except ImportError:
                pass
            app.forget_key()
            self.wait(app)
            self.assertIsNone(app.client.account)


if __name__ == "__main__":
    unittest.main()
