"""Count the most common words in a text file."""

import argparse
import sys
from collections import Counter


def count_words(text):
    return Counter(word.lower().strip(".,!?;:\"'()-") for word in text.split())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--top", type=int, default=10, help="How many words to show.")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as f:
        counts = count_words(f.read())
    for word, count in counts.most_common(args.top):
        print(f"{count}\t{word}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
