// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

contract Lottery {
    enum State { Open, Drawing, Finished, Cancelled }

    address public immutable owner;
    uint256 public immutable ticketPrice;
    address public distributor;
    State public state;
    uint256 public prizePool;
    address[] private participants;
    mapping(address => uint256) public contributions;
    bool private locked;

    event Entered(address indexed participant, uint256 amount);
    event DistributorConfigured(address indexed distributor);
    event EntriesClosed(uint256 participantsCount);
    event PoolReleased(uint256 amount);
    event Cancelled();
    event Refunded(address indexed participant, address indexed recipient, uint256 amount);

    constructor(uint256 ticketPrice_) {
        require(ticketPrice_ > 0, "Invalid ticket price");
        owner = msg.sender;
        ticketPrice = ticketPrice_;
    }

    modifier onlyDistributor() {
        require(msg.sender == distributor, "Only distributor");
        _;
    }

    modifier nonReentrant() {
        require(!locked, "Reentrant call");
        locked = true;
        _;
        locked = false;
    }

    function setDistributor(address distributor_) external {
        require(msg.sender == owner, "Only owner");
        require(distributor == address(0), "Already configured");
        require(distributor_.code.length > 0, "Invalid distributor");
        distributor = distributor_;
        emit DistributorConfigured(distributor_);
    }

    function enter() external payable {
        require(distributor != address(0), "Not configured");
        require(state == State.Open, "Entries closed");
        require(msg.value == ticketPrice, "Wrong ticket price");
        require(contributions[msg.sender] == 0, "Already entered");
        participants.push(msg.sender);
        contributions[msg.sender] = msg.value;
        prizePool += msg.value;
        emit Entered(msg.sender, msg.value);
    }

    function getParticipants() external view returns (address[] memory) {
        return participants;
    }

    function getParticipantsCount() external view returns (uint256) {
        return participants.length;
    }

    function participantAt(uint256 index) external view returns (address) {
        return participants[index];
    }

    function closeEntries() external onlyDistributor {
        require(state == State.Open, "Entries closed");
        require(participants.length >= 2, "Need two participants");
        state = State.Drawing;
        emit EntriesClosed(participants.length);
    }

    function releasePool() external onlyDistributor nonReentrant returns (uint256 amount) {
        require(state == State.Drawing, "Not drawing");
        state = State.Finished;
        amount = prizePool;
        prizePool = 0;
        (bool success,) = payable(distributor).call{value: amount}("");
        require(success, "Pool transfer failed");
        emit PoolReleased(amount);
    }

    function cancel() external onlyDistributor {
        require(state == State.Open || state == State.Drawing, "Already ended");
        state = State.Cancelled;
        emit Cancelled();
    }

    function refund(address payable recipient) external nonReentrant {
        require(state == State.Cancelled, "Not cancelled");
        require(recipient != address(0), "Invalid recipient");
        uint256 amount = contributions[msg.sender];
        require(amount > 0, "Nothing to refund");
        contributions[msg.sender] = 0;
        prizePool -= amount;
        (bool success,) = recipient.call{value: amount}("");
        require(success, "Refund failed");
        emit Refunded(msg.sender, recipient, amount);
    }
}
