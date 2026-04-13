"""Base player class shared by the human and bot subclasses."""

from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from poker.card import Card

POSITIONS = ['BTN', 'SB', 'BB', 'UTG', 'CO']  # index 0 = button seat


class Player:
    def __init__(self, name: str, chips: int = 1_000) -> None:
        self.name = name
        self.chips = chips

        # Per-hand state (reset each hand)
        self.hole_cards: List['Card'] = []
        self.is_folded = False
        self.is_all_in = False
        self.position: str = ''        # 'BTN', 'SB', 'BB', 'UTG', 'CO'
        self.position_idx: int = 0     # 0=BTN, 1=SB, 2=BB, 3=UTG, 4=CO

        # Bet tracking (reset each street)
        self.street_bet = 0    # chips committed this street
        self.total_bet  = 0    # chips committed this entire hand

    # ------------------------------------------------------------------
    # Reset helpers
    # ------------------------------------------------------------------

    def reset_for_hand(self) -> None:
        self.hole_cards = []
        self.is_folded  = False
        self.is_all_in  = False
        self.street_bet = 0
        self.total_bet  = 0

    def reset_for_street(self) -> None:
        self.street_bet = 0

    # ------------------------------------------------------------------
    # Chip mechanics
    # ------------------------------------------------------------------

    def put_in(self, amount: int) -> int:
        """
        Move *amount* chips to the pot.  Caps at remaining stack.
        Sets is_all_in if chips reach 0.  Returns actual amount moved.
        """
        amount = min(amount, self.chips)
        self.chips      -= amount
        self.street_bet += amount
        self.total_bet  += amount
        if self.chips == 0:
            self.is_all_in = True
        return amount

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """Player can still act (not folded, not all-in)."""
        return not self.is_folded and not self.is_all_in

    @property
    def is_in_hand(self) -> bool:
        """Player hasn't folded yet (may be all-in)."""
        return not self.is_folded

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'Player({self.name}, ${self.chips})'
