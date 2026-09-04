"""Authetec specialized engines."""
from .payment import PaymentFraudEngine, Transaction, feature_extract  # noqa: F401
from .risk import RiskEngine, DEFAULT_SOURCE_WEIGHTS  # noqa: F401
from .document import DocumentEngine, DocumentInput, validate_document  # noqa: F401
from .signature import SignatureEngine, SignatureSample  # noqa: F401
from .face import (  # noqa: F401
    FaceVerificationEngine,
    FaceMatchInput,
    LivenessCheck,
    DeterministicFaceEmbedder,
    cosine_similarity,
    DEFAULT_MATCH_THRESHOLD,
)
from .social import (  # noqa: F401
    SocialTrustEngine,
    SocialProfileInput,
    EXCLUDED_ATTRIBUTES,
)
from .mrz import (  # noqa: F401
    validate_mrz,
    detect_mrz_type,
    extract_mrz_from_text,
    MrzValidationResult,
    compute_check_digit,
    validate_check_digit,
)
from .document_profiles import (  # noqa: F401
    DocumentProfile,
    FieldRule,
    register_profile,
    get_profile,
    get_profile_or_default,
    list_profiles,
)
from .identity_document import (  # noqa: F401
    IdentityDocumentEngine,
    IdentityDocumentInput,
)
from .liveness import (  # noqa: F401
    DeterministicLivenessDetector,
    LivenessDetector,
    LivenessResult,
    PresentationAttack,
    PadMethod,
    get_liveness_detector,
    set_liveness_detector,
)
