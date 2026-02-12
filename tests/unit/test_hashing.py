"""Test hashing utilities."""
import pytest
from app.utils.hashing import hash_input, normalize_text


def test_hash_input_deterministic():
    """Test that hash_input produces consistent hashes."""
    data1 = {"text": "hello world"}
    data2 = {"text": "hello world"}
    
    hash1 = hash_input(data1)
    hash2 = hash_input(data2)
    
    assert hash1 == hash2


def test_hash_input_different_for_different_data():
    """Test that different inputs produce different hashes."""
    data1 = {"text": "hello world"}
    data2 = {"text": "goodbye world"}
    
    hash1 = hash_input(data1)
    hash2 = hash_input(data2)
    
    assert hash1 != hash2


def test_hash_input_key_order_independent():
    """Test that key order doesn't affect hash."""
    data1 = {"text": "hello", "id": 123}
    data2 = {"id": 123, "text": "hello"}
    
    hash1 = hash_input(data1)
    hash2 = hash_input(data2)
    
    assert hash1 == hash2


def test_normalize_text_lowercase():
    """Test that normalize_text converts to lowercase."""
    text = "Hello World"
    normalized = normalize_text(text)
    
    assert normalized == "hello world"


def test_normalize_text_strips_whitespace():
    """Test that normalize_text strips whitespace."""
    text = "  hello world  "
    normalized = normalize_text(text)
    
    assert normalized == "hello world"


def test_normalize_text_combined():
    """Test normalize_text with multiple transformations."""
    text = "  Hello WORLD  "
    normalized = normalize_text(text)
    
    assert normalized == "hello world"
