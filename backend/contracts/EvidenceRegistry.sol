// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title EvidenceRegistry
 * @notice Minimal gas-efficient evidence anchoring registry for ThermalWatch AI / IGNIS.
 * @dev Stores SHA-256 hashes of canonical evidence packages on EVM testnet.
 */
contract EvidenceRegistry {
    // Mapping from SHA-256 evidence digest (as bytes32) to anchor timestamp
    mapping(bytes32 => uint256) public anchoredAt;

    // Mapping from evidence digest to submitter address
    mapping(bytes32 => address) public submitters;

    // Mapping from evidence digest to block number
    mapping(bytes32 => uint256) public blockNumbers;

    // Total count of anchored evidence records
    uint256 public totalAnchored;

    event EvidenceAnchored(
        bytes32 indexed evidenceHash,
        uint256 timestamp,
        address indexed submitter
    );

    /**
     * @notice Anchor an evidence package hash to the blockchain.
     * @param evidenceHash The 32-byte SHA-256 digest of the evidence package.
     */
    function anchorEvidence(bytes32 evidenceHash) external {
        require(evidenceHash != bytes32(0), "Invalid empty hash");
        require(anchoredAt[evidenceHash] == 0, "Already anchored");

        anchoredAt[evidenceHash] = block.timestamp;
        submitters[evidenceHash] = msg.sender;
        blockNumbers[evidenceHash] = block.number;
        totalAnchored++;

        emit EvidenceAnchored(
            evidenceHash,
            block.timestamp,
            msg.sender
        );
    }

    /**
     * @notice Check whether an evidence hash has been anchored.
     * @param evidenceHash The 32-byte SHA-256 digest to verify.
     */
    function isAnchored(bytes32 evidenceHash) external view returns (bool) {
        return anchoredAt[evidenceHash] != 0;
    }

    /**
     * @notice Retrieve complete anchor record for an evidence hash.
     * @param evidenceHash The 32-byte SHA-256 digest.
     */
    function getAnchor(bytes32 evidenceHash) external view returns (
        bool exists,
        uint256 timestamp,
        address submitter,
        uint256 blockNumber
    ) {
        uint256 ts = anchoredAt[evidenceHash];
        if (ts == 0) {
            return (false, 0, address(0), 0);
        }
        return (true, ts, submitters[evidenceHash], blockNumbers[evidenceHash]);
    }
}
