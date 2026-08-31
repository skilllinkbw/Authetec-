import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"C:\Users\DELL\Documents\GitHub\Authetec-")

from app.engines.document import DocumentEngine, DocumentInput, validate_document, DocumentValidationError
from app.engines.risk import RiskEngine
from app.models.risk import EngineResult

# --- Document engine tests ---
# Valid tiny PNG (1x1 red pixel)
import base64
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
doc = DocumentInput(filename="id_card.png", content=png, declared_content_type="image/png")
try:
    ft = validate_document(png, "image/png")
    print("PNG validated as:", ft)
except DocumentValidationError as e:
    print("validate error:", e)

# Reject executable
try:
    validate_document(b"MZ" + b"\x00" * 200)
    print("ERROR: should have rejected")
except DocumentValidationError as e:
    print("Executable rejected OK:", e)

# Empty/small file
try:
    validate_document(b"")
except DocumentValidationError as e:
    print("Empty rejected OK:", e)

eng = DocumentEngine(tenant_id="acme")
res = eng.verify(doc)
print("doc decision:", res.decision, "score:", res.risk_score, "reason:", res.reasons[0])
print("doc evidence stored:", res.extra.get("stored_evidence_id", "NONE") is not None)

# --- Risk engine tests ---
risk = RiskEngine()
r = risk.aggregate([res], tenant_id="acme")
print("risk:", r.decision, r.risk_score, "signals:", r.contributing_signals)

r2 = risk.aggregate([], tenant_id="acme")
print("empty risk:", r2.decision, r2.risk_score)
print("DOC + RISK ENGINE OK")