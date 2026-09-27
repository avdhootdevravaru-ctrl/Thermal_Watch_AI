"""Deploy ThermalWatchAnchor contract to EVM Testnet (e.g. Sepolia).

Usage:
  python scripts/deploy_anchor_contract.py

Requires BLOCKCHAIN_RPC_URL and BLOCKCHAIN_PRIVATE_KEY in .env.
Prints deployed contract address and updates configuration instructions.
"""

import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from web3 import Web3
from eth_account import Account


def deploy():
    print("=== DEPLOY THERMALWATCH ANCHOR CONTRACT ===")
    rpc_url = settings.BLOCKCHAIN_RPC_URL
    priv_key = settings.BLOCKCHAIN_PRIVATE_KEY

    if not rpc_url:
        print("ERROR: BLOCKCHAIN_RPC_URL is not set.")
        sys.exit(1)

    if not priv_key:
        print("ERROR: BLOCKCHAIN_PRIVATE_KEY is not set.")
        print("Please configure a funded testnet account in .env to deploy.")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"ERROR: Cannot connect to RPC at {rpc_url}")
        sys.exit(1)

    acct = Account.from_key(priv_key)
    print(f"Network:  {settings.BLOCKCHAIN_NETWORK} (Chain ID: {settings.BLOCKCHAIN_CHAIN_ID})")
    print(f"Deployer: {acct.address}")

    balance = w3.eth.get_balance(acct.address)
    print(f"Balance:  {w3.from_wei(balance, 'ether')} ETH")

    if balance == 0:
        print("ERROR: Deployer account has 0 ETH on testnet.")
        print(f"Request Sepolia faucet ETH for {acct.address} at https://sepoliafaucet.com or https://faucets.chain.link")
        sys.exit(1)

    artifact_path = Path(__file__).resolve().parent.parent / "contracts" / "EvidenceRegistry.json"
    if not artifact_path.exists():
        artifact_path = Path(__file__).resolve().parent.parent / "contracts" / "ThermalWatchAnchor.json"
    if not artifact_path.exists():
        print("ERROR: compiled artifact not found in contracts/. Run compilation first.")
        sys.exit(1)

    with open(artifact_path, "r") as f:
        artifact = json.load(f)

    abi = artifact["abi"]
    bytecode = artifact["bin"]

    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(acct.address, "pending")
    gas_price = w3.eth.gas_price

    tx = Contract.constructor().build_transaction({
        "from": acct.address,
        "nonce": nonce,
        "gasPrice": int(gas_price * 1.2),
        "chainId": settings.BLOCKCHAIN_CHAIN_ID,
    })

    try:
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
    except Exception:
        tx["gas"] = 800000

    signed = w3.eth.account.sign_transaction(tx, private_key=priv_key)
    print("Broadcasting deployment transaction...")
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hex = tx_hash.hex()
    if not tx_hex.startswith("0x"):
        tx_hex = f"0x{tx_hex}"
    print(f"Tx Hash:  {tx_hex}")
    print("Waiting for transaction confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    contract_address = receipt["contractAddress"]

    print("\n CONTRACT DEPLOYED SUCCESSFULLY!")
    print(f"Contract Address: {contract_address}")
    print(f"Block Number:     {receipt['blockNumber']}")
    print(f"Gas Used:         {receipt['gasUsed']}")
    print(f"Explorer URL:     {settings.BLOCKCHAIN_EXPLORER_ADDRESS_URL}{contract_address}")
    print("\nNext step: Set BLOCKCHAIN_CONTRACT_ADDRESS in .env:")
    print(f"BLOCKCHAIN_CONTRACT_ADDRESS={contract_address}")
    print("BLOCKCHAIN_ENABLED=true")


if __name__ == "__main__":
    deploy()
