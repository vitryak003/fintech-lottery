// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import "./Lottery.sol";

contract PrizeDistributor {
    Lottery public immutable lottery;
    address public immutable owner;
    uint256 public drawBlock;
    address public winner;
    uint256 public prize;
    uint256 public claimablePrize;
    bool private locked;

    event DrawRequested(uint256 indexed drawBlock);
    event WinnerSelected(address indexed winner, uint256 amount);
    event PrizeClaimed(address indexed winner, address indexed recipient, uint256 amount);

    constructor(address lottery_) {
        require(lottery_.code.length > 0, "Invalid lottery");
        lottery = Lottery(lottery_);
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier nonReentrant() {
        require(!locked, "Reentrant call");
        locked = true;
        _;
        locked = false;
    }

    receive() external payable {
        require(msg.sender == address(lottery), "Only lottery");
    }

    function requestDraw() external onlyOwner {
        lottery.closeEntries();
        drawBlock = block.number + 2;
        emit DrawRequested(drawBlock);
    }

    function finalizeDraw() external nonReentrant {
        require(lottery.state() == Lottery.State.Drawing, "Not drawing");
        require(block.number > drawBlock, "Wait for draw block");
        require(block.number <= drawBlock + 256, "Draw expired");
        bytes32 entropy = blockhash(drawBlock);
        require(entropy != bytes32(0), "Block hash unavailable");
        uint256 index = uint256(keccak256(abi.encode(entropy, address(this))))
            % lottery.getParticipantsCount();
        winner = lottery.participantAt(index);
        prize = lottery.releasePool();
        claimablePrize = prize;
        emit WinnerSelected(winner, prize);
    }

    function claimPrize(address payable recipient) external nonReentrant {
        require(msg.sender == winner, "Only winner");
        require(recipient != address(0), "Invalid recipient");
        uint256 amount = claimablePrize;
        require(amount > 0, "Nothing to claim");
        claimablePrize = 0;
        (bool success,) = recipient.call{value: amount}("");
        require(success, "Prize transfer failed");
        emit PrizeClaimed(msg.sender, recipient, amount);
    }

    function cancelOpenLottery() external onlyOwner {
        require(lottery.state() == Lottery.State.Open, "Not open");
        lottery.cancel();
    }

    function cancelExpiredDraw() external {
        require(lottery.state() == Lottery.State.Drawing, "Not drawing");
        require(block.number > drawBlock + 256, "Draw not expired");
        lottery.cancel();
    }
}
