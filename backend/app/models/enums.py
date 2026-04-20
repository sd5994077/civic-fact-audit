from enum import StrEnum


class StatementSourceType(StrEnum):
    speech = 'speech'
    interview = 'interview'
    social = 'social'
    debate = 'debate'
    press_release = 'press_release'


class ClaimStatus(StrEnum):
    draft = 'draft'
    reviewed = 'reviewed'
    published = 'published'


class SourceClass(StrEnum):
    primary = 'primary'
    secondary = 'secondary'


class Verdict(StrEnum):
    supported = 'supported'
    mixed = 'mixed'
    unsupported = 'unsupported'
    insufficient = 'insufficient'
