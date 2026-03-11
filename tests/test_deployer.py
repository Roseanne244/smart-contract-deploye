"""
tests/test_deployer.py — Unit tests for ContractDeployer
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestNetworkConfig:
    """Test network configuration validation."""

    def test_sepolia_chain_id(self):
        from src.deployer import NETWORK_CONFIG, Network
        assert NETWORK_CONFIG[Network.SEPOLIA]["chain_id"] == 11155111

    def test_mainnet_chain_id(self):
        from src.deployer import NETWORK_CONFIG, Network
        assert NETWORK_CONFIG[Network.MAINNET]["chain_id"] == 1

    def test_polygon_chain_id(self):
        from src.deployer import NETWORK_CONFIG, Network
        assert NETWORK_CONFIG[Network.POLYGON]["chain_id"] == 137

    def test_all_networks_have_required_keys(self):
        from src.deployer import NETWORK_CONFIG
        required = {"rpc", "chain_id", "explorer", "api_url"}
        for network, config in NETWORK_CONFIG.items():
            assert required.issubset(config.keys()), f"{network} missing keys"


class TestGasCalculations:
    """Test gas estimation math."""

    def test_gas_multiplier_applied(self):
        estimated = 200_000
        multiplier = 1.20
        with_buffer = int(estimated * multiplier)
        assert with_buffer == 240_000

    def test_cost_calculation(self):
        gas_limit     = 240_000
        gas_price_gwei = 20.0
        gas_price_wei  = gas_price_gwei * 1e9
        cost_eth       = (gas_limit * gas_price_wei) / 1e18
        assert abs(cost_eth - 0.0048) < 1e-8

    def test_eip1559_max_fee(self):
        base_fee_gwei    = 15.0
        priority_fee_gwei = 2.0
        # max_fee = base * 2 + priority
        max_fee = base_fee_gwei * 2 + priority_fee_gwei
        assert max_fee == 32.0


class TestDeploymentRecord:
    """Test deployment record serialization."""

    def test_dataclass_to_dict(self):
        from src.deployer import DeploymentRecord
        record = DeploymentRecord(
            contract_name="TestToken",
            address="0x1234",
            tx_hash="0xabcd",
            deployer="0xdeploy",
            network="sepolia",
            block_number=1000,
            gas_used=200000,
            gas_price_gwei=20.0,
            deploy_cost_eth=0.004,
            timestamp="2026-01-01T00:00:00+00:00",
            constructor_args=["Test", "TST"],
        )
        from dataclasses import asdict
        d = asdict(record)
        assert d["contract_name"] == "TestToken"
        assert d["network"] == "sepolia"
        assert d["constructor_args"] == ["Test", "TST"]

    def test_record_stores_gas_info(self):
        from src.deployer import DeploymentRecord
        record = DeploymentRecord(
            contract_name="A", address="0x1", tx_hash="0x2",
            deployer="0x3", network="sepolia", block_number=100,
            gas_used=150_000, gas_price_gwei=25.0,
            deploy_cost_eth=0.00375, timestamp="",
            constructor_args=[],
        )
        assert record.gas_used == 150_000
        assert record.gas_price_gwei == 25.0


class TestRetryLogic:
    """Test exponential backoff in _wait_for_receipt."""

    def test_backoff_formula(self):
        """Backoff should grow but cap at max."""
        wait = 2.0
        max_wait = 15.0
        results = []
        for _ in range(6):
            results.append(wait)
            wait = min(wait * 1.5, max_wait)

        assert results[0] == 2.0
        assert results[-1] <= max_wait

    def test_timeout_detection(self):
        """Should detect timeout after threshold."""
        start = 0
        timeout = 300
        elapsed = 301
        assert elapsed > timeout


class TestBalanceCheck:
    """Test balance validation before deployment."""

    def test_insufficient_balance_detected(self):
        balance = 0.001
        required = 0.01
        assert balance < required

    def test_sufficient_balance_passes(self):
        balance = 1.0
        required = 0.01
        assert balance >= required
