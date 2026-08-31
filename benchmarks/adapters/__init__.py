"""Authetec Benchmark Adapters — wrapping external benchmark repos."""
from .lightgbm_fraud_adapter import LightGBMFraudAdapter
from .ensemble_fraud_adapter import EnsembleFraudAdapter
from .fraud_risk_pipeline_adapter import FraudRiskPipelineAdapter
from .insurance_fraud_adapter import InsuranceFraudAdapter
from .graph_fraud_adapter import GraphFraudAdapter
from .identity_duplicate_adapter import IdentityDuplicateAdapter

ALL_ADAPTERS = {
    "lightgbm_fraud": LightGBMFraudAdapter,
    "ensemble_fraud": EnsembleFraudAdapter,
    "fraud_risk_pipeline": FraudRiskPipelineAdapter,
    "insurance_fraud": InsuranceFraudAdapter,
    "graph_fraud": GraphFraudAdapter,
    "identity_duplicate": IdentityDuplicateAdapter,
}

__all__ = ["ALL_ADAPTERS"] + list(ALL_ADAPTERS.keys())