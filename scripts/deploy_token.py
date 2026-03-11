"""
scripts/deploy_token.py
=======================
Example: Deploy an ERC-20 token using ContractDeployer.

Usage:
  export PRIVATE_KEY=0x...
  export SEPOLIA_RPC=https://rpc.sepolia.org
  python scripts/deploy_token.py
"""

import json
from src.deployer import ContractDeployer, Network

# ─────────────────────────────────────────────
#  Minimal ERC-20 ABI (just what we need)
# ─────────────────────────────────────────────
ERC20_ABI = json.loads("""[
  {
    "inputs": [
      {"name": "name_", "type": "string"},
      {"name": "symbol_", "type": "string"},
      {"name": "initialSupply", "type": "uint256"}
    ],
    "stateMutability": "nonpayable",
    "type": "constructor"
  },
  {
    "inputs": [{"name": "account", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [
      {"name": "to", "type": "address"},
      {"name": "amount", "type": "uint256"}
    ],
    "name": "transfer",
    "outputs": [{"name": "", "type": "bool"}],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [],
    "name": "totalSupply",
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [],
    "name": "name",
    "outputs": [{"name": "", "type": "string"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [],
    "name": "symbol",
    "outputs": [{"name": "", "type": "string"}],
    "stateMutability": "view",
    "type": "function"
  }
]""")

# Compiled bytecode (from solc or Hardhat artifact)
# This is a placeholder — replace with actual compiled bytecode
ERC20_BYTECODE = "0x..."


def main():
    # ─── 1. Initialize deployer ───
    deployer = ContractDeployer(
        network=Network.SEPOLIA,
        # private_key="0x..." or set PRIVATE_KEY env var
    )

    # ─── 2. Deploy ───
    contract_address, receipt = deployer.deploy(
        contract_name="RoseCoin",
        abi=ERC20_ABI,
        bytecode=ERC20_BYTECODE,
        constructor_args=[
            "RoseCoin",        # name
            "RSC",             # symbol
            1_000_000 * 10**18 # initialSupply (1M tokens)
        ],
    )

    print(f"\n🎉 RoseCoin deployed at: {contract_address}")
    print(f"   TX: {receipt['transactionHash'].hex()}")

    # ─── 3. Read contract state ───
    contract = deployer.get_contract(contract_address, ERC20_ABI)

    name         = deployer.call(contract, "name")
    symbol       = deployer.call(contract, "symbol")
    total_supply = deployer.call(contract, "totalSupply")

    print(f"\n📊 Contract Info:")
    print(f"   Name:         {name}")
    print(f"   Symbol:       {symbol}")
    print(f"   Total Supply: {total_supply / 10**18:,.0f} {symbol}")

    # ─── 4. Verify on Etherscan (optional) ───
    # deployer.verify_contract(
    #     contract_address=contract_address,
    #     contract_name="RoseCoin",
    #     source_code=open("contracts/RoseCoin.sol").read(),
    # )

    # ─── 5. View deployment history ───
    history = deployer.list_deployments(network_filter="sepolia")
    print(f"\n📋 Total Sepolia deployments: {len(history)}")


if __name__ == "__main__":
    main()
