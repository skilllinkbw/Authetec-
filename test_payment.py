import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"C:\Users\DELL\Documents\GitHub\Authetec-")
from app.engines.payment import PaymentFraudEngine, Transaction, feature_extract

f = feature_extract(Transaction(transaction_id="t1", amount=50000.0,
                                account_balance=1000.0), None)
print("features:", f[:6], "...total", len(f))

eng = PaymentFraudEngine()
res = eng.score_transaction(Transaction(transaction_id="tx-1", amount=50.0,
                                         account_balance=5000.0,
                                         channel="card"),
                            tenant_id="t1")
print("low-risk decision:", res.decision, res.risk_score)

res2 = eng.score_transaction(Transaction(transaction_id="tx-2", amount=200000.0,
                                          account_balance=300.0, channel="crypto"),
                             tenant_id="t1")
print("high-risk decision:", res2.decision, res2.risk_score)
print("reason:", res2.reasons)
print("PAYMENT ENGINE OK")