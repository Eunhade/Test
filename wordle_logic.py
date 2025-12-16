# Load valid words from text file
import os
import random

_here = os.path.dirname(__file__)

# Prefer ./data/valid_words.txt (production layout), but fall back to ./valid_words.txt
words_file = os.path.join(_here, 'data', 'valid_words.txt')
if not os.path.exists(words_file):
    words_file = os.path.join(_here, 'valid_words.txt')

with open(words_file, 'r') as f:
    VALID_WORDS = set(word.strip().upper() for word in f if word.strip())

# Convert to list for random.choice() - sets are not subscriptable
VALID_WORDS_LIST = list(VALID_WORDS)


def random_word():
    return random.choice(VALID_WORDS_LIST)


def is_valid_word(word: str) -> bool:
    return word.upper() in VALID_WORDS


def evaluate_guess(secret: str, guess: str) -> dict:
    guess = guess.upper()
    secret = secret.upper()

    if len(guess) != len(secret):
        return {'colors': [], 'solved': False, 'error': 'Invalid word length'}

    colors = [None] * len(guess)
    secret_letters = list(secret)

    # First pass: mark correct positions
    for i, ch in enumerate(guess):
        if ch == secret[i]:
            colors[i] = 'green'
            secret_letters[i] = None

    # Second pass: mark present letters (wrong position) or absent
    for i, ch in enumerate(guess):
        if colors[i] is not None:
            continue
        if ch in secret_letters:
            colors[i] = 'yellow'
            idx = secret_letters.index(ch)
            secret_letters[idx] = None
        else:
            colors[i] = 'gray'

    solved = (guess == secret)
    return {'colors': colors, 'solved': solved}


def get_word_length() -> int:
    return 5
