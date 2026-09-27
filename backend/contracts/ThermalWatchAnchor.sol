// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ThermalWatchAnchor
 * @notice Stores and verifies tamper-evident SHA-256 evidence package hashes for ThermalWatch AI / IGNIS.
 * @dev Immutable audit ledger on EVM testnet.
 */
contract ThermalWatchAnchor {
    struct AnchorRecord {
        bytes32 evidenceHash;
        uint256 eventId;
        uint256 timestamp;
        address submitter;
        uint256 blockNumber;
    }

    // Mapping from SHA-256 evidence digest (as bytes32) to anchor record
    mapping(bytes32 => AnchorRecord) public anchors;

    // Mapping from event ID to latest evidence hash
    mapping(uint256 => bytes32) public eventLatestAnchor;

    // Total count of anchored evidence records
    uint256 public totalAnchored;

    // Emitted when an evidence package hash is immutably anchored on-chain
    event EvidenceAnchored(
        bytes32 indexed evidenceHash,
        uint256 indexed eventId,
        uint256 timestamp,
        address indexed submitter,
        uint256 blockNumber
    );

    /**
     * @notice Anchor an evidence package hash to the blockchain.
     * @param evidenceHash The 32-byte SHA-256 digest of the canonical evidence package.
     * @param eventId The identifier of the thermal event.
     */
    function anchorEvidence(bytes32 evidenceHash, uint256 eventId) external returns (bool) {
        require(evidenceHash != bytes32(0), "ThermalWatch: Invalid empty hash");
        require(anchors[evidenceHash].timestamp == 0, "ThermalWatch: Evidence already anchored");

        anchors[evidenceHash] = AnchorRecord({
            evidenceHash: evidenceHash,
            eventId: eventId,
            timestamp: block.timestamp,
            submitter: msg.sender,
            blockNumber: block.number
        });

        eventLatestAnchor[eventId] = evidenceHash;
        totalAnchored++;

        emit EvidenceAnchored(
            evidenceHash,
            eventId,
            block.timestamp,
            msg.sender,
            block.number
        );

        return true;
    }

    /**
     * @notice Verify whether an evidence hash exists on-chain and retrieve its provenance.
     * @param evidenceHash The 32-byte SHA-256 digest to verify.
     */
    function verifyEvidence(bytes32 evidenceHash) external view returns (
        bool exists,
        uint256 eventId,
        uint256 timestamp,
        address submitter,
        uint256 blockNumber
    ) {
        AnchorRecord memory record = anchors[evidenceHash];
        if (record.timestamp == 0) {
            return (false, 0, 0, address(0), 0);
        }
        return (
            true,
            record.eventId,
            record.timestamp,
            record.submitter,
            record.blockNumber
        );
    }
}
