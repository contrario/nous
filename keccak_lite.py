from __future__ import annotations

_MASK64: int = (1 << 64) - 1
_RATE_BYTES: int = 136
_OUTPUT_BYTES: int = 32

_RC: tuple[int, ...] = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

_R: tuple[tuple[int, ...], ...] = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rotl64(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


def _keccak_f1600(a: list[list[int]]) -> None:
    for rnd in range(24):
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl64(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rotl64(a[x][y], _R[x][y])
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) & _MASK64
        a[0][0] ^= _RC[rnd]


def keccak256(data: bytes) -> bytes:
    msg = bytearray(data)
    msg.append(0x01)
    while len(msg) % _RATE_BYTES != 0:
        msg.append(0x00)
    msg[-1] ^= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), _RATE_BYTES):
        block = msg[off:off + _RATE_BYTES]
        for i in range(_RATE_BYTES // 8):
            lane = int.from_bytes(block[i * 8:i * 8 + 8], "little")
            a[i % 5][i // 5] ^= lane
        _keccak_f1600(a)
    out = bytearray()
    while len(out) < _OUTPUT_BYTES:
        for i in range(_RATE_BYTES // 8):
            if len(out) >= _OUTPUT_BYTES:
                break
            out += a[i % 5][i // 5].to_bytes(8, "little")
        if len(out) < _OUTPUT_BYTES:
            _keccak_f1600(a)
    return bytes(out[:_OUTPUT_BYTES])
