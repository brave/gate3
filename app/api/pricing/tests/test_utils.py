import pytest

from app.api.pricing.utils import chunk_sequence


def test_chunk_sequence_empty():
    result = chunk_sequence([], 3)
    assert result == []


def test_chunk_sequence_exact_chunks():
    sequence = [1, 2, 3, 4, 5, 6]
    result = chunk_sequence(sequence, 3)
    assert result == [[1, 2, 3], [4, 5, 6]]


def test_chunk_sequence_with_remainder():
    sequence = [1, 2, 3, 4, 5]
    result = chunk_sequence(sequence, 3)
    assert result == [[1, 2, 3], [4, 5]]


def test_chunk_sequence_single_chunk():
    sequence = [1, 2]
    result = chunk_sequence(sequence, 3)
    assert result == [[1, 2]]


def test_chunk_sequence_different_types():
    sequence = ["a", 1, True, "b", 2, False]
    result = chunk_sequence(sequence, 2)
    assert result == [["a", 1], [True, "b"], [2, False]]


def test_chunk_sequence_invalid_chunk_size():
    with pytest.raises(ValueError):
        chunk_sequence([1, 2, 3], 0)
    with pytest.raises(ValueError):
        chunk_sequence([1, 2, 3], -1)
