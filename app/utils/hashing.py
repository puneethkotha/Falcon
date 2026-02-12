"""Hashing utilities."""
import hashlib
import json
from typing import Any, Dict


def hash_input(data: Dict[str, Any]) -> str:
    """
    Create a deterministic hash of input data for caching.
    
    Args:
        data: Input data dictionary
        
    Returns:
        SHA256 hash of the normalized input
    """
    # Normalize the input by sorting keys and converting to JSON
    normalized = json.dumps(data, sort_keys=True, ensure_ascii=True)
    
    # Create SHA256 hash
    hash_object = hashlib.sha256(normalized.encode())
    return hash_object.hexdigest()


def normalize_text(text: str) -> str:
    """
    Normalize text for consistent caching.
    
    Args:
        text: Input text
        
    Returns:
        Normalized text
    """
    # Strip whitespace and convert to lowercase
    return text.strip().lower()
