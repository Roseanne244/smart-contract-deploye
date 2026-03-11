"""
deployer.py — Smart Contract Deployment & Interaction Framework
===============================================================

Author  : Roseanne Park
Purpose : Production-grade Python framework for deploying and
          interacting with Ethereum smart contracts.

Features:
  - Deploy contracts from ABI + bytecode
  - Auto-retry with exponential backoff
  - Gas estimation with safety multiplier
  - Transaction receipt waiting with timeout
  - Deployment history logging (JSON)
  - Multi-network support (Sepolia, Mainnet, Polygon, Arbitrum)
  - ERC-20 / ERC-721 built-in interaction helpers
  - Contract verification via Etherscan API

Usage:
  from src.deployer import ContractDeployer, Network

  deployer = ContractDeployer(network=Network.SEPOLIA, private_key="0x...")
  receipt = deployer.deploy("MyToken", abi, bytecode, constructor_args=["MyToken", "MTK", 1000000])
"""

import os
import json
import time
import logging
from enum import Enum
from typing import Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxReceipt
from eth_account import Account
from eth_account.signers.local import LocalAccount

# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("deployer")

# ─────────────────────────────────────────────
#  Network Configuration
# ─────────────────────────────────────────────

class Network(Enum):
    MAINNET  = "mainnet"
    SEPOLIA  = "sepolia"
    POLYGON  = "polygon"
    ARBITRUM = "arbitrum"
    ANVIL    = "anvil"    # Local development

NETWORK_CONFIG = {
    Network.MAINNET: {
        "rpc":      os.getenv("MAINNET_RPC", "https://eth.llamarpc.com"),
        "chain_id": 1,
        "explorer": "https://etherscan.io",
        "api_url":  "https://api.etherscan.io/api",
    },
    Network.SEPOLIA: {
        "rpc":      os.getenv("SEPOLIA_RPC", "https://rpc.sepolia.org"),
        "chain_id": 11155111,
        "explorer": "https://sepolia.etherscan.io",
        "api_url":  "https://api-sepolia.etherscan.io/api",
    },
    Network.POLYGON: {
        "rpc":      os.getenv("POLYGON_RPC", "https://polygon-rpc.com"),
        "chain_id": 137,
        "explorer": "https://polygonscan.com",
        "api_url":  "https://api.polygonscan.com/api",
    },
    Network.ARBITRUM: {
        "rpc":      os.getenv("ARBITRUM_RPC", "https://arb1.arbitrum.io/rpc"),
        "chain_id": 42161,
        "explorer": "https://arbiscan.io",
        "api_url":  "https://api.arbiscan.io/api",
    },
    Network.ANVIL: {
        "rpc":      "http://127.0.0.1:8545",
        "chain_id": 31337,
        "explorer": "http://localhost",
        "api_url":  "",
    },
}

# ─────────────────────────────────────────────
#  Data Models
# ─────────────────────────────────────────────

@dataclass
class DeploymentRecord:
    """Persisted record of a contract deployment."""
    contract_name: str
    address: str
    tx_hash: str
    deployer: str
    network: str
    block_number: int
    gas_used: int
    gas_price_gwei: float
    deploy_cost_eth: float
    timestamp: str
    constructor_args: list

@dataclass
class GasEstimate:
    gas_limit: int
    gas_price_gwei: float
    max_fee_gwei: float
    priority_fee_gwei: float
    estimated_cost_eth: float
    estimated_cost_usd: float

# ─────────────────────────────────────────────
#  Core Deployer
# ─────────────────────────────────────────────

class ContractDeployer:
    """
    Production-grade contract deployment framework.

    Handles:
    - Network connection + validation
    - Gas estimation with configurable multiplier
    - Transaction signing + broadcasting
    - Receipt confirmation with timeout + retry
    - Deployment history persistence
    - Etherscan verification
    """

    # Gas safety multiplier — add 20% buffer to gas estimates
    GAS_MULTIPLIER   = 1.20
    # Max blocks to wait for confirmation
    CONFIRMATION_TIMEOUT = 300  # seconds
    # Deployment history file
    HISTORY_FILE = "deployments.json"

    def __init__(
        self,
        network: Network,
        private_key: Optional[str] = None,
        etherscan_key: Optional[str] = None,
    ):
        config = NETWORK_CONFIG[network]
        self.network     = network
        self.config      = config
        self.etherscan_key = etherscan_key or os.getenv("ETHERSCAN_API_KEY", "")

        # Initialize web3
        self.w3 = Web3(Web3.HTTPProvider(config["rpc"]))

        # POA middleware for Polygon/BSC
        if network in (Network.POLYGON,):
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to {network.value}: {config['rpc']}")

        # Validate chain ID
        actual_chain_id = self.w3.eth.chain_id
        expected_chain_id = config["chain_id"]
        if actual_chain_id != expected_chain_id:
            raise ValueError(
                f"Chain ID mismatch: expected {expected_chain_id}, got {actual_chain_id}"
            )

        # Setup account
        pk = private_key or os.getenv("PRIVATE_KEY")
        if not pk:
            raise ValueError("Private key required. Set PRIVATE_KEY env var.")
        self.account: LocalAccount = Account.from_key(pk)

        log.info(f"✅ Connected to {network.value} (chain {actual_chain_id})")
        log.info(f"📬 Deployer: {self.account.address}")
        log.info(f"💰 Balance:  {self._get_balance_eth():.6f} ETH")

    def _get_balance_eth(self) -> float:
        balance_wei = self.w3.eth.get_balance(self.account.address)
        return float(self.w3.from_wei(balance_wei, "ether"))

    # ─────────────────────────────────────────────
    #  Gas Estimation
    # ─────────────────────────────────────────────

    def estimate_gas(
        self,
        contract_factory,
        constructor_args: list,
    ) -> GasEstimate:
        """
        Estimate deployment gas with safety buffer.
        Uses EIP-1559 fee model if available.
        """
        try:
            estimated = contract_factory.constructor(*constructor_args).estimate_gas(
                {"from": self.account.address}
            )
        except Exception as e:
            log.warning(f"Gas estimation failed: {e}. Using fallback 3,000,000")
            estimated = 3_000_000

        gas_limit = int(estimated * self.GAS_MULTIPLIER)

        # Try EIP-1559 first
        try:
            latest = self.w3.eth.get_block("latest")
            base_fee = latest.get("baseFeePerGas", 0)
            priority_fee = self.w3.eth.max_priority_fee
            max_fee = base_fee * 2 + priority_fee

            base_gwei    = float(self.w3.from_wei(base_fee, "gwei"))
            priority_gwei = float(self.w3.from_wei(priority_fee, "gwei"))
            max_gwei     = float(self.w3.from_wei(max_fee, "gwei"))
            gas_price_gwei = base_gwei + priority_gwei

        except Exception:
            gas_price     = self.w3.eth.gas_price
            gas_price_gwei = float(self.w3.from_wei(gas_price, "gwei"))
            max_gwei      = gas_price_gwei
            priority_gwei = 0.0

        cost_wei = gas_limit * int(self.w3.to_wei(gas_price_gwei, "gwei"))
        cost_eth = float(self.w3.from_wei(cost_wei, "ether"))

        return GasEstimate(
            gas_limit=gas_limit,
            gas_price_gwei=gas_price_gwei,
            max_fee_gwei=max_gwei,
            priority_fee_gwei=priority_gwei,
            estimated_cost_eth=cost_eth,
            estimated_cost_usd=cost_eth * 3200,  # rough USD
        )

    # ─────────────────────────────────────────────
    #  Deploy
    # ─────────────────────────────────────────────

    def deploy(
        self,
        contract_name: str,
        abi: list,
        bytecode: str,
        constructor_args: Optional[list] = None,
        gas_multiplier: float = 1.20,
    ) -> tuple[str, TxReceipt]:
        """
        Deploy a contract to the network.

        Args:
            contract_name:    Human-readable name for logging/history
            abi:              Contract ABI (list of dicts)
            bytecode:         Compiled contract bytecode (hex string)
            constructor_args: Arguments to pass to constructor
            gas_multiplier:   Safety buffer for gas limit

        Returns:
            Tuple of (contract_address, tx_receipt)

        Raises:
            ValueError: If deployment fails or times out
        """
        constructor_args = constructor_args or []
        log.info(f"🚀 Deploying {contract_name} to {self.network.value}...")
        log.info(f"   Constructor args: {constructor_args}")

        # Build contract factory
        contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)

        # Estimate gas
        estimate = self.estimate_gas(contract, constructor_args)
        log.info(f"⛽ Gas limit:    {estimate.gas_limit:,}")
        log.info(f"⛽ Gas price:    {estimate.gas_price_gwei:.2f} Gwei")
        log.info(f"⛽ Est. cost:    {estimate.estimated_cost_eth:.6f} ETH (≈${estimate.estimated_cost_usd:.2f})")

        # Check balance
        balance = self._get_balance_eth()
        if balance < estimate.estimated_cost_eth:
            raise ValueError(
                f"Insufficient balance: have {balance:.6f} ETH, need {estimate.estimated_cost_eth:.6f} ETH"
            )

        # Build transaction
        nonce = self.w3.eth.get_transaction_count(self.account.address)

        tx_params: dict[str, Any] = {
            "from":     self.account.address,
            "nonce":    nonce,
            "gas":      estimate.gas_limit,
            "chainId":  self.config["chain_id"],
        }

        # EIP-1559 fees if supported
        try:
            latest = self.w3.eth.get_block("latest")
            if "baseFeePerGas" in latest:
                tx_params["maxFeePerGas"]         = int(self.w3.to_wei(estimate.max_fee_gwei, "gwei"))
                tx_params["maxPriorityFeePerGas"] = int(self.w3.to_wei(estimate.priority_fee_gwei + 0.5, "gwei"))
            else:
                tx_params["gasPrice"] = int(self.w3.to_wei(estimate.gas_price_gwei, "gwei"))
        except Exception:
            tx_params["gasPrice"] = int(self.w3.to_wei(estimate.gas_price_gwei, "gwei"))

        # Build + sign + send
        tx = contract.constructor(*constructor_args).build_transaction(tx_params)
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        log.info(f"📡 TX sent: 0x{tx_hash.hex()}")
        log.info(f"   Explorer: {self.config['explorer']}/tx/0x{tx_hash.hex()}")
        log.info("⏳ Waiting for confirmation...")

        # Wait for receipt with timeout
        receipt = self._wait_for_receipt(tx_hash)

        if receipt["status"] == 0:
            raise ValueError(f"❌ Deployment FAILED. TX: 0x{tx_hash.hex()}")

        contract_address = receipt["contractAddress"]
        gas_used         = receipt["gasUsed"]
        block_number     = receipt["blockNumber"]

        gas_price_wei  = tx_params.get("gasPrice") or tx_params.get("maxFeePerGas", 0)
        cost_eth       = float(self.w3.from_wei(gas_used * gas_price_wei, "ether"))

        log.info(f"✅ {contract_name} deployed!")
        log.info(f"   Address:  {contract_address}")
        log.info(f"   Block:    {block_number:,}")
        log.info(f"   Gas used: {gas_used:,}")
        log.info(f"   Cost:     {cost_eth:.6f} ETH")

        # Save deployment record
        record = DeploymentRecord(
            contract_name=contract_name,
            address=contract_address,
            tx_hash=f"0x{tx_hash.hex()}",
            deployer=self.account.address,
            network=self.network.value,
            block_number=block_number,
            gas_used=gas_used,
            gas_price_gwei=estimate.gas_price_gwei,
            deploy_cost_eth=cost_eth,
            timestamp=datetime.now(timezone.utc).isoformat(),
            constructor_args=constructor_args,
        )
        self._save_deployment(record)

        return contract_address, receipt

    def _wait_for_receipt(self, tx_hash: bytes, poll_interval: float = 2.0) -> TxReceipt:
        """Poll for transaction receipt with exponential backoff."""
        start = time.time()
        wait  = poll_interval

        while True:
            elapsed = time.time() - start
            if elapsed > self.CONFIRMATION_TIMEOUT:
                raise TimeoutError(
                    f"Transaction not confirmed after {self.CONFIRMATION_TIMEOUT}s"
                )

            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None:
                    return receipt
            except Exception:
                pass

            log.info(f"  ⏳ Waiting... ({elapsed:.0f}s)")
            time.sleep(wait)
            wait = min(wait * 1.5, 15.0)  # Exponential backoff, max 15s

    # ─────────────────────────────────────────────
    #  Contract Interaction Helpers
    # ─────────────────────────────────────────────

    def get_contract(self, address: str, abi: list):
        """Get a deployed contract instance for interaction."""
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=abi
        )

    def call(self, contract, function_name: str, *args) -> Any:
        """Call a read-only (view) function."""
        fn = getattr(contract.functions, function_name)
        return fn(*args).call()

    def send(
        self,
        contract,
        function_name: str,
        *args,
        value_eth: float = 0.0,
    ) -> TxReceipt:
        """Send a state-changing transaction to a contract function."""
        fn = getattr(contract.functions, function_name)
        nonce = self.w3.eth.get_transaction_count(self.account.address)

        tx = fn(*args).build_transaction({
            "from":    self.account.address,
            "nonce":   nonce,
            "value":   self.w3.to_wei(value_eth, "ether"),
            "chainId": self.config["chain_id"],
        })

        # Gas estimation with buffer
        estimated_gas = self.w3.eth.estimate_gas(tx)
        tx["gas"] = int(estimated_gas * self.GAS_MULTIPLIER)

        signed  = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._wait_for_receipt(tx_hash)

        log.info(f"✅ {function_name}() | Gas: {receipt['gasUsed']:,} | Block: {receipt['blockNumber']:,}")
        return receipt

    # ─────────────────────────────────────────────
    #  Deployment History
    # ─────────────────────────────────────────────

    def _save_deployment(self, record: DeploymentRecord):
        """Append deployment record to history JSON file."""
        history = self._load_history()
        history.append(asdict(record))
        with open(self.HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
        log.info(f"📝 Deployment recorded in {self.HISTORY_FILE}")

    def _load_history(self) -> list:
        if Path(self.HISTORY_FILE).exists():
            with open(self.HISTORY_FILE) as f:
                return json.load(f)
        return []

    def list_deployments(self, network_filter: Optional[str] = None) -> list:
        """List all past deployments, optionally filtered by network."""
        history = self._load_history()
        if network_filter:
            history = [h for h in history if h["network"] == network_filter]
        return history

    # ─────────────────────────────────────────────
    #  Etherscan Verification
    # ─────────────────────────────────────────────

    def verify_contract(
        self,
        contract_address: str,
        contract_name: str,
        source_code: str,
        compiler_version: str = "v0.8.20+commit.a1b79de6",
        constructor_abi: str = "",
    ) -> bool:
        """
        Verify contract source code on Etherscan.
        Requires ETHERSCAN_API_KEY environment variable.
        """
        if not self.etherscan_key:
            log.warning("No Etherscan API key — skipping verification")
            return False

        api_url = self.config["api_url"]
        if not api_url:
            log.warning(f"No Etherscan API for {self.network.value}")
            return False

        import requests
        payload = {
            "apikey":              self.etherscan_key,
            "module":              "contract",
            "action":              "verifysourcecode",
            "contractaddress":     contract_address,
            "sourceCode":          source_code,
            "codeformat":          "solidity-single-file",
            "contractname":        contract_name,
            "compilerversion":     compiler_version,
            "optimizationUsed":    "1",
            "runs":                "200",
            "constructorArguements": constructor_abi,
        }

        resp = requests.post(api_url, data=payload, timeout=30)
        result = resp.json()

        if result.get("status") == "1":
            guid = result.get("result")
            log.info(f"✅ Verification submitted. GUID: {guid}")
            log.info(f"   Check: {self.config['explorer']}/address/{contract_address}#code")
            return True
        else:
            log.error(f"❌ Verification failed: {result.get('result')}")
            return False
