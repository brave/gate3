from typing import TypeVar, Sequence

T = TypeVar("T")


def chunk_sequence(sequence: Sequence[T], chunk_size: int) -> list[list[T]]:
    """
    Split a sequence into chunks of specified size.

    Args:
        sequence: The sequence to split into chunks
        chunk_size: The size of each chunk

    Returns:
        A list of chunks, where each chunk is a list of items from the original sequence

    Raises:
        ValueError: If chunk_size is less than or equal to 0
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    chunks = [list(chunk) for chunk in zip(*[iter(sequence)] * chunk_size)]
    if len(sequence) % chunk_size != 0:
        chunks.append(list(sequence)[-(len(sequence) % chunk_size) :])
    return chunks
