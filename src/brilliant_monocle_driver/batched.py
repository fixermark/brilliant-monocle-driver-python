# Copyright 2023 Mark T. Tomczak
# License at https://github.com/fixermark/brilliant-monocle-driver-python/blob/main/LICENSE

def batched(iterable, length):
    """
    Simple implementation of itertools.batched from Python 12.
    Generator that yields chunks of length (length) from the iterable.
    """

    cursor = 0
    while cursor < len(iterable):
        yield iterable[cursor:cursor + length]
        cursor += length
