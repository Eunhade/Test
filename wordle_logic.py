# Load valid words from text file
import os
import random


words_file = os.path.join(os.path.dirname(__file__), "data", "valid_words.txt")
with open(words_file, "r") as f:
    VALID_WORDS = set(word.strip().upper() for word in f if word.strip())

# Convert to list for random.choice() - sets are not subscriptable
VALID_WORDS_LIST = list(VALID_WORDS)


def random_word():
    wordchoice = random.choice(VALID_WORDS_LIST)
    print(f"\n\nRandom word is {wordchoice}\n\n")
    return wordchoice


def is_valid_word(word: str) -> bool:
    return word.upper() in VALID_WORDS


def evaluate_guess(secret: str, guess: str) -> dict:
    guess = guess.upper()
    secret = secret.upper()
    
    if len(guess) != len(secret):
        return {"colors": [], "solved": False, "error": "Invalid word length"}

    colors = [None] * len(guess)
    secret_letters = list(secret)

    # First pass: mark all exact matches (green)
    for i, ch in enumerate(guess):
        if ch == secret[i]:
            colors[i] = "green"
            secret_letters[i] = None  # Mark as used

    # Second pass: mark present but wrong position (yellow) or absent (gray)
    for i, ch in enumerate(guess):
        if colors[i] is not None:
            continue  # Already marked green
        
        if ch in secret_letters:
            colors[i] = "yellow"
            idx = secret_letters.index(ch)
            secret_letters[idx] = None  # Mark as used
        else:
            colors[i] = "gray"

    solved = (guess == secret)
    return {"colors": colors, "solved": solved}


def get_word_length() -> int:
    """Return the standard word length for the game."""
    return 5