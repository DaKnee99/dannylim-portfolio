"""
Bot players with distinct personalities.

Four personalities are defined:
  TAG      (Tight-Aggressive)  – Atlas
  LAG      (Loose-Aggressive)  – Blaze
  ROCK     (Tight-Passive/Nit) – Grinder
  MANIAC   (Gambler/Erratic)   – Maverick
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from poker.player import Player
from poker.hand_evaluator import (
    best_hand, preflop_strength, postflop_strength,
)

if TYPE_CHECKING:
    from poker.card import Card


# ---------------------------------------------------------------------------
# Personality definition
# ---------------------------------------------------------------------------

@dataclass
class Personality:
    style: str           # e.g. "TAG"
    description: str
    vpip: float          # % of hands voluntarily entered (0-1)
    pfr: float           # % of hands where bot raises pre-flop (0-1)
    aggression: float    # post-flop aggression multiplier  (1 = balanced)
    bluff_freq: float    # probability of a pure bluff on any given street
    call_threshold: float  # minimum hand strength needed to call a bet
    fold_to_3bet: float  # probability of folding to a 3-bet with a weak hand
    noise: float         # randomness / tilt factor


PERSONALITIES: Dict[str, Personality] = {
    'TAG': Personality(
        style='TAG',
        description='Tight-Aggressive — plays premium hands, bets big',
        vpip=0.22,
        pfr=0.17,
        aggression=2.2,
        bluff_freq=0.10,
        call_threshold=0.32,
        fold_to_3bet=0.55,
        noise=0.05,
    ),
    'LAG': Personality(
        style='LAG',
        description='Loose-Aggressive — wide range, relentless pressure',
        vpip=0.44,
        pfr=0.33,
        aggression=3.0,
        bluff_freq=0.27,
        call_threshold=0.18,
        fold_to_3bet=0.25,
        noise=0.12,
    ),
    'ROCK': Personality(
        style='ROCK',
        description='Rock/Nit — ultra-tight, passive unless holding a monster',
        vpip=0.14,
        pfr=0.06,
        aggression=0.55,
        bluff_freq=0.04,
        call_threshold=0.50,
        fold_to_3bet=0.75,
        noise=0.03,
    ),
    'MANIAC': Personality(
        style='MANIAC',
        description='Maniac/Gambler — wild, erratic, raises with almost anything',
        vpip=0.72,
        pfr=0.60,
        aggression=5.0,
        bluff_freq=0.45,
        call_threshold=0.08,
        fold_to_3bet=0.10,
        noise=0.25,
    ),
}

# Human-readable tag labels for the display
STYLE_LABELS = {
    'TAG':    '[TAG]',
    'LAG':    '[LAG]',
    'ROCK':   '[NIT]',
    'MANIAC': '[MNIAC]',
}


# ---------------------------------------------------------------------------
# Bot class
# ---------------------------------------------------------------------------

class Bot(Player):
    def __init__(self, name: str, style: str, chips: int = 1_000) -> None:
        super().__init__(name, chips)
        self.personality: Personality = PERSONALITIES[style]
        self.style = style
        self.style_label = STYLE_LABELS[style]

        # Track aggression this street (detect 3-bets against us)
        self._facing_raise = False

    # ------------------------------------------------------------------
    # Public decision interface
    # ------------------------------------------------------------------

    def decide(
        self,
        community_cards: List['Card'],
        pot: int,
        current_bet: int,   # highest bet this street (absolute)
        min_raise_to: int,  # minimum amount to raise to
        num_active: int,    # active players still in hand
        is_3bet: bool = False,
    ) -> Tuple[str, int]:
        """
        Returns (action, amount) where action is one of:
          'fold', 'check', 'call', 'bet', 'raise', 'all_in'
        and amount is the total chips to commit this street (0 for fold/check).
        """
        p = self.personality
        to_call = current_bet - self.street_bet

        # ---- Hand strength ------------------------------------------------
        if community_cards:
            score = best_hand(self.hole_cards + community_cards)
            strength = postflop_strength(score)
        else:
            strength = preflop_strength(self.hole_cards)

        # ---- Position bonus (late position = slight edge) -----------------
        pos_bonus = {0: 0.04, 4: 0.02, 1: -0.02, 2: -0.03, 3: -0.01}
        strength += pos_bonus.get(self.position_idx, 0)

        # ---- Add personality noise ----------------------------------------
        strength += random.gauss(0, p.noise)
        strength = max(0.0, min(1.0, strength))

        # ---- Facing a 3-bet (aggressive re-raise) -------------------------
        if is_3bet and strength < 0.55:
            if random.random() < p.fold_to_3bet:
                return ('fold', 0)

        # ---- No bet to call -----------------------------------------------
        if to_call == 0:
            return self._decide_no_bet(strength, pot, min_raise_to)

        # ---- Bet/raise is facing us ---------------------------------------
        return self._decide_facing_bet(
            strength, pot, to_call, current_bet, min_raise_to
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decide_no_bet(
        self, strength: float, pot: int, min_raise_to: int
    ) -> Tuple[str, int]:
        p = self.personality
        # Bet threshold: aggression scales with hand strength
        bet_threshold = 1.0 / (p.aggression + 1.0)

        if strength > bet_threshold or random.random() < p.bluff_freq * 0.5:
            amount = self._size_bet(strength, pot)
            if amount >= self.chips:
                return ('all_in', self.chips + self.street_bet)
            # Ensure we meet min_raise_to when there's a previous bet context
            amount = max(amount, min_raise_to) if min_raise_to > self.street_bet else amount
            return ('bet', self.street_bet + amount)
        return ('check', 0)

    def _decide_facing_bet(
        self,
        strength: float,
        pot: int,
        to_call: int,
        current_bet: int,
        min_raise_to: int,
    ) -> Tuple[str, int]:
        p = self.personality

        # Pot-odds threshold: if pot odds justify calling, lower the bar
        pot_odds = to_call / (pot + to_call) if (pot + to_call) > 0 else 0
        effective_threshold = max(p.call_threshold, pot_odds * 0.8)

        raise_threshold = effective_threshold + 0.20 / p.aggression

        if strength > raise_threshold:
            # Raise
            raise_amount = self._size_raise(strength, pot, current_bet)
            raise_to = current_bet + raise_amount
            raise_to = max(raise_to, min_raise_to)
            if raise_to - self.street_bet >= self.chips:
                return ('all_in', self.chips + self.street_bet)
            return ('raise', raise_to)

        if strength > effective_threshold:
            # Call
            if to_call >= self.chips:
                return ('all_in', self.chips + self.street_bet)
            return ('call', current_bet)

        # Bluff raise opportunity
        if random.random() < p.bluff_freq:
            raise_to = max(min_raise_to, current_bet + self._size_raise(0.3, pot, current_bet))
            if raise_to - self.street_bet >= self.chips:
                return ('all_in', self.chips + self.street_bet)
            return ('raise', raise_to)

        return ('fold', 0)

    def _size_bet(self, strength: float, pot: int) -> int:
        """Calculate bet size as fraction of pot (chips to add, not total street bet)."""
        p = self.personality
        # 0.4–1.2× pot depending on strength and aggression
        frac = 0.4 + strength * 0.8 * (p.aggression / 3.0)
        frac = min(frac, 1.2)
        size = max(int(pot * frac), 20)   # never less than 20
        return min(size, self.chips)

    def _size_raise(self, strength: float, pot: int, current_bet: int) -> int:
        """Calculate the raise-size ON TOP of the current bet."""
        p = self.personality
        frac = 0.5 + strength * 1.0 * (p.aggression / 3.0)
        frac = min(frac, 2.0)
        size = max(int((pot + current_bet) * frac), current_bet)
        return min(size, self.chips)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_bots() -> List[Bot]:
    """Return the 4 bots used in the game."""
    return [
        Bot('Atlas',    'TAG',    chips=1_000),
        Bot('Blaze',    'LAG',    chips=1_000),
        Bot('Grinder',  'ROCK',   chips=1_000),
        Bot('Maverick', 'MANIAC', chips=1_000),
    ]
