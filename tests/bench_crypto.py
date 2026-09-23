"""Telethon-compatible AES-IGE implementations for benchmarking the pure-Python
fallback path (what telethon.crypto.aes uses when no C crypto is installed).
Covers cryptg and TgCrypto-pyrofork too, in one file, so all stacks are
comparable on identical data.

Usage:
    python3 bench_crypto.py <stack>   # pyaes | cryptg | tgcrypto | goygram

Each stack must run in its own venv with only that package installed
(goygram needs no extra venv: its crypto is a Rust extension, not a telethon dep).
"""
import statistics
import sys
import time

key = b"\x11" * 32
iv = b"\x22" * 32

stack = sys.argv[1] if len(sys.argv) > 1 else "pyaes"


class IGE:
    """telethon-style IGE over pyaes.AES blocks (the slow fallback)."""

    def __init__(self, key: bytes, iv: bytes):
        import pyaes

        self.aes = pyaes.AES(key)
        self.iv1 = iv[:16]
        self.iv2 = iv[16:]

    def encrypt(self, pt: bytes) -> bytes:
        pad = len(pt) % 16
        if pad:
            pt += b"\x00" * (16 - pad)
        iv1, iv2 = self.iv1, self.iv2
        out = bytearray()
        for i in range(0, len(pt), 16):
            blk = pt[i : i + 16]
            x = bytes(a ^ b for a, b in zip(blk, iv2))
            e = self.aes.encrypt(list(x))
            c = bytes(a ^ b for a, b in zip(e, iv1))
            out += c
            iv1, iv2 = blk, c
        return bytes(out)

    def decrypt(self, ct: bytes) -> bytes:
        iv1, iv2 = self.iv1, self.iv2
        out = bytearray()
        for i in range(0, len(ct), 16):
            blk = ct[i : i + 16]
            x = bytes(a ^ b for a, b in zip(blk, iv1))
            d = self.aes.decrypt(list(x))
            p = bytes(a ^ b for a, b in zip(d, iv2))
            out += p
            iv1, iv2 = p, blk
        return bytes(out)


if stack == "pyaes":
    enc_c = IGE(key, iv)
    dec_c = IGE(key, iv)
    enc, dec = enc_c.encrypt, dec_c.decrypt
elif stack == "cryptg":
    import cryptg

    enc = lambda d: cryptg.encrypt_ige(d, key, iv)  # noqa: E731
    dec = lambda d: cryptg.decrypt_ige(d, key, iv)  # noqa: E731
elif stack == "tgcrypto":
    import tgcrypto

    enc = lambda d: tgcrypto.ige256_encrypt(d, key, iv)  # noqa: E731
    dec = lambda d: tgcrypto.ige256_decrypt(d, key, iv)  # noqa: E731
elif stack == "goygram":
    from goygram.ext import aes_ige_dec, aes_ige_enc

    enc = lambda d: aes_ige_enc(d, key, iv)  # noqa: E731
    dec = lambda d: aes_ige_dec(d, key, iv)  # noqa: E731
else:
    sys.exit(f"unknown stack: {stack}")


def bench(fn, arg: bytes, n: int = 25) -> float:
    """Median of n runs, milliseconds."""
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        fn(arg)
        ts.append(time.perf_counter() - t)
    return statistics.median(ts) * 1000


def mbps(ms: float, nbytes: int) -> float:
    return nbytes / 1024 / 1024 / (ms / 1000)


print(f"=== {stack} ===")
for size, label in [(4096, "4KB"), (1 << 20, "1MB"), (16 << 20, "16MB")]:
    if stack == "pyaes" and size > (1 << 20):
        continue  # pure python: minutes per run, skip
    d = b"\x44" * size
    enc(d)
    ms_e = bench(enc, d)
    ms_d = bench(dec, d)
    print(
        f"{label:>5} enc: {ms_e:9.3f} ms ({mbps(ms_e, size):8.1f} MB/s)"
        f"  dec: {ms_d:9.3f} ms ({mbps(ms_d, size):8.1f} MB/s)"
    )

d = b"\x44" * 4096
ct = enc(d)
assert dec(ct) == d, "roundtrip failed"
print("roundtrip OK, ct[:8]:", ct[:8].hex())
