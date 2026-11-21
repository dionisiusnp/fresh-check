class FreshCheckError(Exception):
    pass


class ExtractionError(FreshCheckError):
    pass


class VerificationError(FreshCheckError):
    pass


class ScoringError(FreshCheckError):
    pass


class PipelineError(FreshCheckError):
    pass
