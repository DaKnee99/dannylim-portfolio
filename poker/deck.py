"""Standard 52-card deck."""

import random
from typing import List
from poker.card import Card, SUITS, RANKS


class Deck:
    def __init__(self) -> None:
        self._cards: List[Card] = []
        self.reset()

    def reset(self) -> None:
        self._cards = [Card(rank, suit) for suit in SUITS for rank in RANKS]
        random.shuffle(self._cards)

    def deal_one(self) -> Card:
        if not self._cards:
            raise RuntimeError('Deck is empty')
        return self._cards.pop()

    def burn(self) -> None:
        """Burn the top card (standard poker protocol before community cards)."""
        if self._cards:
            self._cards.pop()

    def __len__(self) -> int:
        return len(self._cards)
