"""
Evaluates poker hands.

best_hand(cards)  → (rank, tiebreakers)   — best 5-of-N hand score
hand_name(score)  → str
preflop_strength(hole_cards) → float 0-1  — quick pre-flop estimate
postflop_strength(score)     → float 0-1  — normalised post-flop score
"""

from itertools import combinations
from collections import Counter
from typing import List, Tuple
from poker.card import Card

# Hand rank constants
HIGH_CARD      = 0
ONE_PAIR       = 1
TWO_PAIR       = 2
THREE_OF_A_KIND = 3
STRAIGHT       = 4
FLUSH          = 5
FULL_HOUSE     = 6
FOUR_OF_A_KIND = 7
STRAIGHT_FLUSH = 8

HAND_NAMES = {
    HIGH_CARD:       'High Card',
    ONE_PAIR:        'One Pair',
    TWO_PAIR:        'Two Pair',
    THREE_OF_A_KIND: 'Three of a Kind',
    STRAIGHT:        'Straight',
    FLUSH:           'Flush',
    FULL_HOUSE:      'Full House',
    FOUR_OF_A_KIND:  'Four of a Kind',
    STRAIGHT_FLUSH:  'Straight Flush',
}

Score = Tuple[int, List[int]]


def _score_five(cards: tuple) -> Score:
    """Score exactly 5 cards. Returns comparable (rank, tiebreakers) tuple."""
    values = sorted((c.value for c in cards), reverse=True)
    suits = [c.suit for c in cards]

    is_flush = len(set(suits)) == 1

    # Straight detection
    is_straight = False
    straight_high = 0
    unique_vals = set(values)
    if len(unique_vals) == 5 and values[0] - values[4] == 4:
        is_straight = True
        straight_high = values[0]
    # Wheel: A-2-3-4-5
    if unique_vals == {14, 2, 3, 4, 5}:
        is_straight = True
        straight_high = 5
        values = [5, 4, 3, 2, 1]

    counts = Counter(values)
    # Sort groups: primary by count desc, secondary by value desc
    groups = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    gcounts = [g[1] for g in groups]
    gvals   = [g[0] for g in groups]

    if is_flush and is_straight:
        return (STRAIGHT_FLUSH,  [straight_high])
    if gcounts[0] == 4:
        return (FOUR_OF_A_KIND,  gvals)
    if gcounts[0] == 3 and gcounts[1] == 2:
        return (FULL_HOUSE,      gvals)
    if is_flush:
        return (FLUSH,           values)
    if is_straight:
        return (STRAIGHT,        [straight_high])
    if gcounts[0] == 3:
        return (THREE_OF_A_KIND, gvals)
    if gcounts[0] == 2 and gcounts[1] == 2:
        return (TWO_PAIR,        gvals)
    if gcounts[0] == 2:
        return (ONE_PAIR,        gvals)
    return     (HIGH_CARD,       values)


def best_hand(cards: List[Card]) -> Score:
    """Return the best 5-card hand score from a list of 2–7 cards."""
    if len(cards) < 5:
        # Pad with lowest possible score — shouldn't happen in normal play
        padded = list(cards) + [cards[0]] * (5 - len(cards))
        return _score_five(tuple(padded))

    best: Score = (-1, [])
    for combo in combinations(cards, 5):
        s = _score_five(combo)
        if s > best:
            best = s
    return best


def hand_name(score: Score) -> str:
    return HAND_NAMES[score[0]]


# ---------------------------------------------------------------------------
# Strength helpers (0.0 – 1.0) used by bots
# ---------------------------------------------------------------------------

def preflop_strength(hole_cards: List[Card]) -> float:
    """Estimate pre-flop hand strength in [0, 1]."""
    vals = sorted((c.value for c in hole_cards), reverse=True)
    v1, v2 = vals[0], vals[1]
    is_pair   = v1 == v2
    is_suited = hole_cards[0].suit == hole_cards[1].suit
    gap       = v1 - v2

    if is_pair:
        # 22 → ~0.40,  AA → 1.0
        base = 0.40 + (v1 - 2) / 12.0 * 0.60
    else:
        # AK → ~0.96,  72o → ~0.21
        base = (v1 - 2 + v2 - 2) / 24.0

    if is_suited:
        base += 0.05
    if not is_pair and gap <= 2:
        base += 0.04
    if not is_pair and gap <= 1:
        base += 0.02

    return min(max(base, 0.0), 1.0)


# Band ranges per hand rank: (low, high)
_RANK_BANDS = [
    (0.04, 0.18),  # High Card
    (0.18, 0.38),  # One Pair
    (0.38, 0.54),  # Two Pair
    (0.54, 0.64),  # Three of a Kind
    (0.64, 0.72),  # Straight
    (0.72, 0.81),  # Flush
    (0.81, 0.90),  # Full House
    (0.90, 0.95),  # Four of a Kind
    (0.95, 1.00),  # Straight Flush
]


def postflop_strength(score: Score) -> float:
    """Normalise a hand score to [0, 1]."""
    rank = score[0]
    tiebreakers = score[1]
    low, high = _RANK_BANDS[rank]
    # Scale within band using the top tiebreaker value (max = Ace = 14)
    tb_norm = (tiebreakers[0] / 14.0) if tiebreakers else 0.5
    return low + (high - low) * tb_norm
