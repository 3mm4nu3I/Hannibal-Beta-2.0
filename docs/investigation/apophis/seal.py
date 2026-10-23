"""Seal a statement now, reveal it later, and prove it was not changed.

    python seal.py my_hypothesis.txt          # prints the SHA-256 to put in PREREGISTRATION.md
    python seal.py my_hypothesis.txt --check <sha256>

Keep my_hypothesis.txt private (do NOT commit it). Commit only the printed hash. Git records when the
hash was committed. Later, publish the file: anyone can run --check and see that the text existed,
unchanged, on that date. Add a line of random characters at the end of the file before sealing, so a
short statement cannot be guessed by trying candidate sentences against the hash.

Hashes the exact bytes of the file: a changed space or line ending gives a different hash.
"""
import argparse
import hashlib
import sys


def seal(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="SHA-256 commit-reveal seal for a private statement")
    ap.add_argument("file")
    ap.add_argument("--check", metavar="SHA256", help="verify the file against a previously published hash")
    args = ap.parse_args(argv)
    digest = seal(args.file)
    if args.check:
        ok = digest == args.check.strip().lower()
        print("MATCH: this is the sealed text" if ok else f"NO MATCH: file hashes to {digest}")
        return 0 if ok else 1
    print(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
