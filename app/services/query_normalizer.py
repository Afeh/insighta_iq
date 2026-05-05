"""
Query normalization module.
Ensures that semantically identical queries produce the same cache key.
"""

import json
import hashlib
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from app.services.nlp_parser import ParsedQuery


@dataclass
class NormalizedFilter:
    """
    Canonical representation of a query filter.
    All semantically equivalent queries normalize to the same object.
    """
    gender: Optional[str] = None
    age_group: Optional[str] = None
    country_id: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    both_genders: bool = False
    min_gender_probability: Optional[float] = None
    min_country_probability: Optional[float] = None
    sort_by: Optional[str] = None
    order: str = "asc"
    page: int = 1
    limit: int = 10
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with None values removed."""
        d = asdict(self)
        # Remove None values and defaults for compact representation
        return {k: v for k, v in d.items() if v is not None}
    
    def to_canonical_json(self) -> str:
        """Convert to canonical JSON string for hashing."""
        d = self.to_dict()
        return json.dumps(d, sort_keys=True, separators=(',', ':'))
    
    def to_cache_key(self, prefix: str = "query") -> str:
        """Generate a cache key from the normalized filter."""
        canonical = self.to_canonical_json()
        hash_val = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        return f"{prefix}:{hash_val}"


def normalize_parsed_query(parsed: ParsedQuery) -> NormalizedFilter:
    """
    Normalize a ParsedQuery object to a canonical NormalizedFilter.
    Handles edge cases and ensures deterministic results.
    """
    normalized = NormalizedFilter()
    
    # Normalize gender (handle both_genders case)
    if parsed.both_genders:
        normalized.both_genders = True
        normalized.gender = None
    else:
        normalized.gender = parsed.gender
    
    # Normalize age group
    normalized.age_group = parsed.age_group
    
    # Normalize country
    normalized.country_id = parsed.country_id
    
    # Normalize age ranges
    # Ensure min_age and max_age are always in sorted order
    if parsed.min_age is not None or parsed.max_age is not None:
        min_val = parsed.min_age
        max_val = parsed.max_age
        
        # Swap if needed
        if min_val is not None and max_val is not None and min_val > max_val:
            min_val, max_val = max_val, min_val
        
        normalized.min_age = min_val
        normalized.max_age = max_val
    
    return normalized


def normalize_filter_params(
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
    country_id: Optional[str] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    min_gender_probability: Optional[float] = None,
    min_country_probability: Optional[float] = None,
    sort_by: Optional[str] = None,
    order: Optional[str] = None,
    page: int = 1,
    limit: int = 10,
) -> NormalizedFilter:
    """
    Normalize raw filter parameters to canonical form.
    """
    normalized = NormalizedFilter()
    
    # Normalize gender (case-insensitive)
    if gender is not None:
        normalized.gender = gender.lower()
    
    # Normalize age group
    if age_group is not None:
        normalized.age_group = age_group.lower()
    
    # Normalize country (uppercase)
    if country_id is not None:
        normalized.country_id = country_id.upper()
    
    # Normalize age ranges - swap if needed
    min_val = min_age
    max_val = max_age
    if min_val is not None and max_val is not None and min_val > max_val:
        min_val, max_val = max_val, min_val
    
    normalized.min_age = min_val
    normalized.max_age = max_val
    
    # Normalize probabilities
    if min_gender_probability is not None:
        # Round to 2 decimal places for normalization
        normalized.min_gender_probability = round(min_gender_probability, 2)
    
    if min_country_probability is not None:
        normalized.min_country_probability = round(min_country_probability, 2)
    
    # Normalize sort
    if sort_by is not None:
        normalized.sort_by = sort_by.lower()
    
    if order is not None:
        normalized.order = order.lower()
    
    normalized.page = page
    normalized.limit = limit
    
    return normalized
