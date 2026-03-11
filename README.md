# 🚀 Smart Contract Deployer

A **production-grade Python framework** for deploying and interacting with Ethereum smart contracts. Handles gas estimation, transaction signing, receipt confirmation, multi-network support, deployment history, and Etherscan verification.

> Built as a Python alternative to Hardhat/Foundry deployment scripts — full control, no JS required.

---

## Features

| Feature | Description |
|---------|-------------|
| 🌐 Multi-network | Mainnet, Sepolia, Polygon, Arbitrum, Anvil (local) |
| ⛽ Smart gas | EIP-1559 support + 20% safety buffer |
| 🔄 Auto-retry | Exponential backoff for receipt confirmation |
| 📝 History | All deployments saved to `deployments.json` |
| 🔍 Verification | Etherscan source verification via API |
| 🛡️ Safety checks | Balance check before deploy, chain ID validation |
| 📊 Logging | Structured logs with timestamps |

---

## Installation

```bash
git clone https://github.com/Roseanne244/smart-contract-deployer.git
cd smart-contract-deployer

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

---

## Quick Start

```python
from src.deployer import ContractDeployer, Network

# Initialize for Sepolia testnet
deployer = ContractDeployer(
    network=Network.SEPOLIA,
    private_key="0x..."  # or set PRIVATE_KEY env var
)

# Deploy contract
address, receipt = deployer.deploy(
    contract_name="RoseCoin",
    abi=abi,           # from Hardhat/Foundry artifact
    bytecode=bytecode,
    constructor_args=["RoseCoin", "RSC", 1_000_000 * 10**18]
)

# Interact with deployed contract
contract = deployer.get_contract(address, abi)
balance = deployer.call(contract, "balanceOf", "0x...")
deployer.send(contract, "transfer", "0x...", 1000 * 10**18)
```

---

## Supported Networks

| Network | Chain ID | Explorer |
|---------|----------|---------|
| Ethereum Mainnet | 1 | etherscan.io |
| Sepolia Testnet | 11155111 | sepolia.etherscan.io |
| Polygon | 137 | polygonscan.com |
| Arbitrum One | 42161 | arbiscan.io |
| Anvil (local) | 31337 | localhost |

---

## Environment Variables

```bash
cp .env.example .env
```

```env
PRIVATE_KEY=0x...
MAINNET_RPC=https://eth.llamarpc.com
SEPOLIA_RPC=https://rpc.sepolia.org
POLYGON_RPC=https://polygon-rpc.com
ARBITRUM_RPC=https://arb1.arbitrum.io/rpc
ETHERSCAN_API_KEY=your_key
```

---

## Deployment History

Every successful deployment is automatically saved:

```json
[
  {
    "contract_name": "RoseCoin",
    "address": "0x1234...abcd",
    "tx_hash": "0xabcd...1234",
    "deployer": "0xYourAddress",
    "network": "sepolia",
    "block_number": 7842910,
    "gas_used": 1284920,
    "gas_price_gwei": 5.2,
    "deploy_cost_eth": 0.006681,
    "timestamp": "2026-01-01T12:00:00+00:00",
    "constructor_args": ["RoseCoin", "RSC", 1000000000000000000000000]
  }
]
```

```python
# Query history
history = deployer.list_deployments(network_filter="sepolia")
```

---

## Run Tests

```bash
pip install pytest
pytest tests/ -v
```

```
tests/test_deployer.py::TestNetworkConfig::test_sepolia_chain_id      PASSED
tests/test_deployer.py::TestNetworkConfig::test_all_networks_have_keys PASSED
tests/test_deployer.py::TestGasCalculations::test_gas_multiplier       PASSED
tests/test_deployer.py::TestGasCalculations::test_cost_calculation     PASSED
tests/test_deployer.py::TestDeploymentRecord::test_dataclass_to_dict   PASSED
tests/test_deployer.py::TestRetryLogic::test_backoff_formula           PASSED

10 passed in 0.09s
```

---

## Project Structure

```
smart-contract-deployer/
├── src/
│   └── deployer.py           ← Core deployment framework
├── scripts/
│   └── deploy_token.py       ← Example: deploy ERC-20
├── tests/
│   └── test_deployer.py      ← Unit tests
├── abi/
│   └── ERC20.json            ← Standard ABI files
├── requirements.txt
├── .env.example
└── README.md
```

---

## Tech Stack

`Python 3.11+` `web3.py` `eth-account` `python-dotenv` `pytest`

---

## License

MIT
