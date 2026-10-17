import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { network } from "hardhat";

describe("Lottery and PrizeDistributor", async () => {
  const { viem, networkHelpers } = await network.connect();
  const wallets = await viem.getWalletClients();
  const client = await viem.getPublicClient();
  const fee = 10_000_000_000_000_000n;

  async function fixture() {
    const lottery = await viem.deployContract("Lottery", [fee]);
    const distributor = await viem.deployContract("PrizeDistributor", [lottery.address]);
    await lottery.write.setDistributor([distributor.address]);
    return { lottery, distributor };
  }

  async function populated() {
    const pair = await fixture();
    for (const wallet of wallets.slice(1, 3)) {
      await pair.lottery.write.enter({ account: wallet.account, value: fee });
    }
    return pair;
  }

  async function completed() {
    const pair = await populated();
    await pair.distributor.write.requestDraw();
    await networkHelpers.mine(3);
    await pair.distributor.write.finalizeDraw({ account: wallets[4].account });
    const winner = await pair.distributor.read.winner();
    const winnerWallet = wallets.find(w => w.account.address.toLowerCase() === winner.toLowerCase())!;
    return { ...pair, winner, winnerWallet };
  }

  it("sets price, owner and the linked distributor", async () => {
    const { lottery, distributor } = await fixture();
    assert.equal(await lottery.read.ticketPrice(), fee);
    assert.equal((await lottery.read.distributor()).toLowerCase(), distributor.address.toLowerCase());
    assert.equal((await distributor.read.owner()).toLowerCase(), wallets[0].account.address.toLowerCase());
    assert.equal(await lottery.read.state(), 0);
  });

  it("records two distinct participants and their Ether", async () => {
    const { lottery } = await populated();
    assert.equal(await lottery.read.getParticipantsCount(), 2n);
    assert.equal(await lottery.read.prizePool(), 2n * fee);
    assert.equal(await client.getBalance({ address: lottery.address }), 2n * fee);
    assert.equal(await lottery.read.contributions([wallets[1].account.address]), fee);
  });

  it("rejects zero, underpayment and overpayment", async () => {
    const { lottery } = await fixture();
    for (const value of [0n, fee - 1n, fee + 1n]) {
      await assert.rejects(lottery.write.enter({ value }), /Wrong ticket price/);
    }
    assert.equal(await lottery.read.getParticipantsCount(), 0n);
  });

  it("rejects a second ticket from the same address", async () => {
    const { lottery } = await populated();
    await assert.rejects(lottery.write.enter({ account: wallets[1].account, value: fee }), /Already entered/);
    assert.equal(await lottery.read.prizePool(), 2n * fee);
  });

  it("requires at least two participants", async () => {
    const { lottery, distributor } = await fixture();
    await assert.rejects(distributor.write.requestDraw(), /Need two participants/);
    await lottery.write.enter({ value: fee });
    await assert.rejects(distributor.write.requestDraw(), /Need two participants/);
  });

  it("allows only the owner to request a draw or cancel an open lottery", async () => {
    const { distributor } = await populated();
    await assert.rejects(distributor.write.requestDraw({ account: wallets[1].account }), /Only owner/);
    await assert.rejects(distributor.write.cancelOpenLottery({ account: wallets[1].account }), /Only owner/);
  });

  it("prevents bypassing the distributor", async () => {
    const { lottery } = await populated();
    await assert.rejects(lottery.write.closeEntries(), /Only distributor/);
    await assert.rejects(lottery.write.releasePool(), /Only distributor/);
    await assert.rejects(lottery.write.cancel(), /Only distributor/);
  });

  it("prevents replacing the distributor", async () => {
    const { lottery, distributor } = await fixture();
    await assert.rejects(lottery.write.setDistributor([distributor.address]), /Already configured/);
    await assert.rejects(lottery.write.setDistributor([distributor.address], { account: wallets[1].account }), /Only owner/);
  });

  it("freezes entries and waits for the future block", async () => {
    const { lottery, distributor } = await populated();
    await distributor.write.requestDraw();
    await assert.rejects(lottery.write.enter({ value: fee }), /Entries closed/);
    await assert.rejects(distributor.write.finalizeDraw(), /Wait for draw block/);
    await assert.rejects(distributor.write.cancelOpenLottery(), /Not open/);
  });

  it("selects a participant and moves the entire accounted pool", async () => {
    const { lottery, distributor, winner } = await completed();
    const participants = await lottery.read.getParticipants();
    assert.ok(participants.some(p => p.toLowerCase() === winner.toLowerCase()));
    assert.equal(await lottery.read.state(), 2);
    assert.equal(await lottery.read.prizePool(), 0n);
    assert.equal(await distributor.read.claimablePrize(), 2n * fee);
    assert.equal(await client.getBalance({ address: lottery.address }), 0n);
    assert.equal(await client.getBalance({ address: distributor.address }), 2n * fee);
    await assert.rejects(distributor.write.finalizeDraw(), /Not drawing/);
  });

  it("pays the exact prize to the winner's chosen recipient once", async () => {
    const { distributor, winnerWallet } = await completed();
    const recipient = wallets[5].account.address;
    const before = await client.getBalance({ address: recipient });
    await distributor.write.claimPrize([recipient], { account: winnerWallet.account });
    assert.equal(await client.getBalance({ address: recipient }), before + 2n * fee);
    assert.equal(await distributor.read.claimablePrize(), 0n);
    await assert.rejects(distributor.write.claimPrize([recipient], { account: winnerWallet.account }), /Nothing to claim/);
  });

  it("rejects a prize claim by anyone except the winner", async () => {
    const { distributor } = await completed();
    await assert.rejects(distributor.write.claimPrize([wallets[0].account.address]), /Only winner/);
  });

  it("preserves the prize when a recipient rejects Ether", async () => {
    const { lottery, distributor, winnerWallet } = await completed();
    await assert.rejects(distributor.write.claimPrize([lottery.address], { account: winnerWallet.account }), /Prize transfer failed/);
    assert.equal(await distributor.read.claimablePrize(), 2n * fee);
  });

  it("refunds cancelled entries without allowing double refunds", async () => {
    const { lottery, distributor } = await populated();
    await distributor.write.cancelOpenLottery();
    const recipient = wallets[6].account.address;
    const before = await client.getBalance({ address: recipient });
    await lottery.write.refund([recipient], { account: wallets[1].account });
    assert.equal(await client.getBalance({ address: recipient }), before + fee);
    assert.equal(await lottery.read.prizePool(), fee);
    await assert.rejects(lottery.write.refund([recipient], { account: wallets[1].account }), /Nothing to refund/);
    await lottery.write.refund([recipient], { account: wallets[2].account });
    assert.equal(await lottery.read.prizePool(), 0n);
  });

  it("rejects refunds before cancellation", async () => {
    const { lottery } = await populated();
    await assert.rejects(lottery.write.refund([wallets[1].account.address], { account: wallets[1].account }), /Not cancelled/);
  });

  it("allows anyone to cancel an expired draw and recover deposits", async () => {
    const { lottery, distributor } = await populated();
    await distributor.write.requestDraw();
    await assert.rejects(distributor.write.cancelExpiredDraw(), /Draw not expired/);
    await networkHelpers.mine(259);
    await assert.rejects(distributor.write.finalizeDraw(), /Draw expired/);
    await distributor.write.cancelExpiredDraw({ account: wallets[7].account });
    assert.equal(await lottery.read.state(), 3);
    await lottery.write.refund([wallets[1].account.address], { account: wallets[1].account });
  });

  it("preserves a deposit when a refund recipient rejects Ether", async () => {
    const { lottery, distributor } = await populated();
    await distributor.write.cancelOpenLottery();
    await assert.rejects(lottery.write.refund([lottery.address], { account: wallets[1].account }), /Refund failed/);
    assert.equal(await lottery.read.contributions([wallets[1].account.address]), fee);
    assert.equal(await lottery.read.prizePool(), 2n * fee);
  });
});
