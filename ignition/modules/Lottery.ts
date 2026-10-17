import { buildModule } from "@nomicfoundation/hardhat-ignition/modules";

export default buildModule("LotteryModule", (m) => {
  const ticketPrice = m.getParameter("ticketPrice", 10_000_000_000_000_000n);
  const lottery = m.contract("Lottery", [ticketPrice]);
  const distributor = m.contract("PrizeDistributor", [lottery]);
  m.call(lottery, "setDistributor", [distributor]);
  return { lottery, distributor };
});
