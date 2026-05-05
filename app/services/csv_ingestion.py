"""
CSV Data Ingestion Service
Handles streaming CSV processing, validation, and batch insertion.
"""

import csv
import io
import asyncio
from typing import Tuple, Dict, List, Optional, BinaryIO
from dataclasses import dataclass
from uuid_extensions import uuid7str
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.profile_models import Profile
from app.services.nlp_parser import COUNTRY_MAP
from app.utils.round_up import round_up


REVERSE_COUNTRY_MAP = {code: name.title() for name, code in COUNTRY_MAP.items()}

BATCH_SIZE = 1000  # Insert in batches of 1000 rows
MAX_FILE_SIZE = 200 * 1024 * 1024  # 100 MB max file size

VALID_GENDERS = {"male", "female"}
VALID_AGE_GROUPS = {"child", "teenager", "adult", "senior"}


@dataclass
class CSVValidationResult:
    """Result of CSV row validation."""
    valid: bool
    error: Optional[str] = None
    profile: Optional[Profile] = None


class CSVIngestionError(Exception):
    """Raised when CSV ingestion encounters a fatal error."""
    pass


def _validate_age(age_value: str, row_num: int) -> Optional[int]:
    """Validate and parse age value."""
    try:
        age = int(age_value.strip())
        if age < 0 or age > 150:
            return None
        return age
    except (ValueError, AttributeError):
        return None


def _validate_gender(gender_value: str) -> Optional[str]:
    """Validate and normalize gender value."""
    if not gender_value:
        return None
    gender_lower = gender_value.strip().lower()
    if gender_lower in VALID_GENDERS:
        return gender_lower
    return None


def _validate_country_id(country_id_value: str) -> Optional[str]:
    """Validate and normalize country ID."""
    if not country_id_value:
        return None
    country_id_upper = country_id_value.strip().upper()
    if len(country_id_upper) == 2 and country_id_upper in REVERSE_COUNTRY_MAP:
        return country_id_upper
    return None


def _validate_age_group(age_group_value: str) -> Optional[str]:
    """Validate age group value."""
    if not age_group_value:
        return None
    age_group_lower = age_group_value.strip().lower()
    if age_group_lower in VALID_AGE_GROUPS:
        return age_group_lower
    return None


def _validate_probability(prob_value: str) -> Optional[float]:
    """Validate and parse probability value."""
    try:
        prob = float(prob_value.strip())
        if prob < 0.0 or prob > 1.0:
            return None
        return prob
    except (ValueError, AttributeError):
        return None


def _validate_csv_row(
    row: Dict[str, str],
    row_num: int,
    db: Session
) -> Tuple[CSVValidationResult, Optional[str]]:
    """
    Validate a single CSV row.
    
    Returns:
        Tuple of (validation_result, skip_reason)
        If validation passes, skip_reason is None.
        If validation fails, skip_reason explains why.
    """
    # Check required fields
    required_fields = {"name", "gender", "age", "country_id", "age_group"}
    row_keys = set(row.keys())
    
    if not required_fields.issubset(row_keys):
        missing = required_fields - row_keys
        return (
            CSVValidationResult(valid=False, error=f"Missing fields: {missing}"),
            "missing_fields"
        )
    
    # Extract and normalize fields
    name = row.get("name", "").strip()
    gender = row.get("gender", "").strip()
    age_str = row.get("age", "").strip()
    country_id = row.get("country_id", "").strip()
    age_group = row.get("age_group", "").strip()
    gender_prob = row.get("gender_probability", "0.5").strip()
    country_prob = row.get("country_probability", "0.5").strip()
    country_name = row.get("country_name", "").strip()
    
    # Validate name
    if not name or len(name) > 255:
        return (
            CSVValidationResult(valid=False, error="Invalid or missing name"),
            "invalid_name"
        )
    
    # Check for duplicate name
    existing = db.query(Profile).filter(
        func.lower(Profile.name) == name.lower()
    ).first()
    if existing:
        return (
            CSVValidationResult(valid=False, error="Duplicate name"),
            "duplicate_name"
        )
    
    # Validate gender
    validated_gender = _validate_gender(gender)
    if not validated_gender:
        return (
            CSVValidationResult(valid=False, error="Invalid gender"),
            "invalid_gender"
        )
    
    # Validate age
    validated_age = _validate_age(age_str, row_num)
    if validated_age is None:
        return (
            CSVValidationResult(valid=False, error="Invalid age"),
            "invalid_age"
        )
    
    # Validate country_id
    validated_country = _validate_country_id(country_id)
    if not validated_country:
        return (
            CSVValidationResult(valid=False, error="Invalid country ID"),
            "invalid_country"
        )
    
    # Validate age_group
    validated_age_group = _validate_age_group(age_group)
    if not validated_age_group:
        return (
            CSVValidationResult(valid=False, error="Invalid age group"),
            "invalid_age_group"
        )
    
    # Validate probabilities
    validated_gender_prob = _validate_probability(gender_prob)
    if validated_gender_prob is None:
        validated_gender_prob = 0.5
    
    validated_country_prob = _validate_probability(country_prob)
    if validated_country_prob is None:
        validated_country_prob = 0.5
    
    # Get country name from map if not provided
    if not country_name:
        country_name = REVERSE_COUNTRY_MAP.get(validated_country, "Unknown")
    
    # Create profile object
    profile = Profile(
        id=uuid7str(),
        name=name,
        gender=validated_gender,
        gender_probability=validated_gender_prob,
        age=validated_age,
        age_group=validated_age_group,
        country_id=validated_country,
        country_name=country_name,
        country_probability=validated_country_prob,
        created_at=datetime.now(timezone.utc)
    )
    
    return (
        CSVValidationResult(valid=True, profile=profile),
        None
    )


async def ingest_csv_file(
    db: Session,
    file_content: bytes,
    filename: str = "upload.csv"
) -> Dict:
    """
    Ingest a CSV file with streaming processing and batch insertion.
    
    Expected CSV columns:
    - name (required): Profile name
    - gender (required): "male" or "female"
    - age (required): Integer age
    - country_id (required): 2-letter country code
    - age_group (required): "child", "teenager", "adult", or "senior"
    - gender_probability (optional): Float 0-1, default 0.9
    - country_probability (optional): Float 0-1, default 0.9
    - country_name (optional): Full country name
    
    Returns:
        Dictionary with ingestion results:
        {
            "status": "success",
            "total_rows": int,
            "inserted": int,
            "skipped": int,
            "reasons": {
                "duplicate_name": int,
                "invalid_age": int,
                ...
            }
        }
    """
    if len(file_content) > MAX_FILE_SIZE:
        raise CSVIngestionError(f"File size exceeds {MAX_FILE_SIZE} bytes")
    
    results = {
        "status": "success",
        "total_rows": 0,
        "inserted": 0,
        "skipped": 0,
        "reasons": {}
    }
    
    batch = []
    total_rows = 0
    
    try:
        # Decode file content
        try:
            text_content = file_content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text_content = file_content.decode('latin-1')
            except UnicodeDecodeError:
                raise CSVIngestionError("Unable to decode file (UTF-8 or Latin-1)")
        
        # Parse CSV
        csv_file = io.StringIO(text_content)
        reader = csv.DictReader(csv_file)
        
        if reader.fieldnames is None:
            raise CSVIngestionError("Empty CSV file")
        
        # Process rows
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (skip header)
            total_rows += 1
            
            # Validate row
            validation, skip_reason = _validate_csv_row(row, row_num, db)
            
            if not validation.valid:
                results["skipped"] += 1
                if skip_reason:
                    results["reasons"][skip_reason] = results["reasons"].get(skip_reason, 0) + 1
                continue
            
            # Add to batch
            batch.append(validation.profile)
            
            # Insert batch when it reaches batch size
            if len(batch) >= BATCH_SIZE:
                db.add_all(batch)
                db.commit()
                results["inserted"] += len(batch)
                batch = []
        
        # Insert remaining rows
        if batch:
            db.add_all(batch)
            db.commit()
            results["inserted"] += len(batch)
        
        results["total_rows"] = total_rows
        
    except CSVIngestionError:
        raise
    except Exception as e:
        # Rollback any pending transaction
        db.rollback()
        raise CSVIngestionError(f"Error processing CSV: {str(e)}")
    
    results["status"] = "success"
    return results


async def validate_csv_structure(file_content: bytes) -> Tuple[bool, Optional[str]]:
    """
    Quick validation of CSV file structure without processing all rows.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        text_content = file_content.decode('utf-8')
    except UnicodeDecodeError:
        return False, "Invalid file encoding (UTF-8 required)"
    
    try:
        csv_file = io.StringIO(text_content)
        reader = csv.DictReader(csv_file)
        
        if reader.fieldnames is None:
            return False, "Empty CSV file"
        
        required_fields = {"name", "gender", "age", "country_id", "age_group"}
        if not required_fields.issubset(set(reader.fieldnames)):
            missing = required_fields - set(reader.fieldnames)
            return False, f"Missing required columns: {missing}"
        
        return True, None
        
    except Exception as e:
        return False, f"Error parsing CSV: {str(e)}"
