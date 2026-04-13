"""
Dealer — manages all game-state mechanics:
  • blinds, deal, streets
  • betting rounds
  • pot management & side pots
  • showdown
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Tuple

from poker.card import Card
from poker.deck import Deck
from poker.hand_evaluator import best_hand, hand_name
from poker.player import Player, POSITIONS
from poker.bot import Bot


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class HandResult:
    """Outcome of one hand."""
    def __init__(self) -> None:
        self.winners: List[Tuple[Player, int, str]] = []
        # Each entry: (player, chips_won, hand_description)
        self.showdown_hands: List[Tuple[Player, str]] = []
        self.one_player_left: bool = False


# ---------------------------------------------------------------------------
# Dealer
# ---------------------------------------------------------------------------

SMALL_BLIND = 10
BIG_BLIND   = 20


class Dealer:
    def __init__(
        self,
        players: List[Player],
        action_callback: Callable[[Player, 'GameState'], Tuple[str, int]],
        display_callback: Optional[Callable[['GameState'], None]] = None,
        bot_delay: float = 0.6,
    ) -> None:
        """
        Parameters
        ----------
        players         : ordered list of players (index 0 will be BTN on hand 1)
        action_callback : called with (player, game_state) → (action, amount)
                          when it's that player's turn.
        display_callback: called before each action to refresh the screen.
        bot_delay       : pause (seconds) after each bot action so player can see it.
        """
        self.players = players
        self.action_callback = action_callback
        self.display_callback = display_callback
        self.bot_delay = bot_delay

        self.deck = Deck()
        self.community_cards: List[Card] = []
        self.pot = 0
        self.contributions: Dict[Player, int] = {}   # total per hand
        self.street = ''          # 'preflop' | 'flop' | 'turn' | 'river'
        self.current_bet = 0      # highest bet this street (absolute)
        self.last_raise_size = BIG_BLIND
        self.button_idx = -1      # advances before each hand
        self.hand_number = 0
        self.action_log: List[str] = []   # e.g. "Atlas raises to $60"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play_hand(self) -> HandResult:
        """Run one complete hand from setup through showdown."""
        self._setup_hand()
        result = HandResult()

        # --- Pre-flop ---
        self.street = 'preflop'
        if not self._run_betting_round():
            return self._award_last_player(result)

        # --- Flop ---
        self.street = 'flop'
        self._deal_community(3)
        self._reset_street_bets()
        if not self._run_betting_round():
            return self._award_last_player(result)

        # --- Turn ---
        self.street = 'turn'
        self._deal_community(1)
        self._reset_street_bets()
        if not self._run_betting_round():
            return self._award_last_player(result)

        # --- River ---
        self.street = 'river'
        self._deal_community(1)
        self._reset_street_bets()
        if not self._run_betting_round():
            return self._award_last_player(result)

        # --- Showdown ---
        return self._showdown(result)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_hand(self) -> None:
        self.hand_number += 1
        self.deck.reset()
        self.community_cards = []
        self.pot = 0
        self.contributions = {p: 0 for p in self.players}
        self.action_log = []

        for p in self.players:
            p.reset_for_hand()

        # Advance button
        self.button_idx = (self.button_idx + 1) % len(self.players)

        n = len(self.players)
        self.sb_idx  = (self.button_idx + 1) % n
        self.bb_idx  = (self.button_idx + 2) % n

        # Assign positions (BTN=0, SB=1, BB=2, UTG=3, CO=4 for 5-handed)
        for i, p in enumerate(self.players):
            rel = (i - self.button_idx) % n
            p.position     = POSITIONS[rel] if rel < len(POSITIONS) else f'MP{rel}'
            p.position_idx = rel

        # Post blinds
        self._post_blind(self.players[self.sb_idx], SMALL_BLIND)
        self._post_blind(self.players[self.bb_idx], BIG_BLIND)

        self.current_bet     = BIG_BLIND
        self.last_raise_size = BIG_BLIND

        # Deal 2 hole cards each (starting left of button)
        deal_order = self._from_seat(self.sb_idx)
        for _ in range(2):
            for p in deal_order:
                p.hole_cards.append(self.deck.deal_one())

    # ------------------------------------------------------------------
    # Betting round
    # ------------------------------------------------------------------

    def _run_betting_round(self) -> bool:
        """
        Execute one street's betting.
        Returns True  → hand continues.
        Returns False → only one player remains (everyone else folded).
        """
        order = self._acting_order()

        # Track who has acted since the last aggressive action.
        # A player must act if:
        #   • they haven't acted yet this round, OR
        #   • someone raised after they last acted
        acted: set = set()
        last_raiser: Optional[Player] = None

        # Pre-flop: BB already posted, counts as "acted" unless someone raised
        if self.street == 'preflop':
            pass  # BB will get their option when the action reaches them

        idx = 0
        iterations = 0
        max_iter = len(self.players) ** 2 + 10  # safety cap

        while iterations < max_iter:
            iterations += 1
            can_act = [p for p in order if p.is_active]
            if not can_act:
                break

            # Round ends when all active players have acted AND matched current bet
            all_done = all(
                p in acted and p.street_bet == self.current_bet
                for p in can_act
            )
            if all_done and len(acted) > 0:
                break

            # Find next player who needs to act (in order)
            player = self._next_to_act(order, acted)
            if player is None:
                break

            # Build game state snapshot
            gs = self._make_game_state(player)

            # Refresh display
            if self.display_callback:
                self.display_callback(gs)

            # Get action
            action, amount = self.action_callback(player, gs)
            self._process_action(player, action, amount)

            if action not in ('fold',):
                acted.add(player)

            if action in ('raise', 'bet', 'all_in') and player.street_bet > self.current_bet:
                last_raiser = player
                # Reset acted set — everyone else must act again
                acted = {player}

            # Short pause after bot actions
            if isinstance(player, Bot) and self.bot_delay > 0:
                time.sleep(self.bot_delay)

            # Check if hand is over
            remaining = [p for p in self.players if p.is_in_hand]
            if len(remaining) == 1:
                return False

        return True

    def _next_to_act(self, order: List[Player], acted: set) -> Optional[Player]:
        """Find the next player in order who still needs to act."""
        for p in order:
            if not p.is_active:
                continue
            if p not in acted:
                return p
            if p.street_bet < self.current_bet:
                return p
        return None

    # ------------------------------------------------------------------
    # Action processing
    # ------------------------------------------------------------------

    def _process_action(self, player: Player, action: str, amount: int) -> None:
        """Apply an action and log it."""
        if action == 'fold':
            player.is_folded = True
            self._log(player, 'folds')

        elif action == 'check':
            self._log(player, 'checks')

        elif action == 'call':
            to_call = self.current_bet - player.street_bet
            actual  = player.put_in(to_call)
            self._add_to_pot(player, actual)
            if player.is_all_in:
                self._log(player, f'calls ${actual} (all-in)')
            else:
                self._log(player, f'calls ${actual}')

        elif action == 'bet':
            # amount = total street bet target
            chips_to_add = amount - player.street_bet
            actual = player.put_in(chips_to_add)
            self._add_to_pot(player, actual)
            self.last_raise_size = actual
            self.current_bet     = player.street_bet
            self._log(player, f'bets ${actual}')

        elif action == 'raise':
            # amount = total street bet target
            chips_to_add = amount - player.street_bet
            actual = player.put_in(chips_to_add)
            self._add_to_pot(player, actual)
            raise_size = player.street_bet - (self.current_bet)
            if raise_size > 0:
                self.last_raise_size = raise_size
            self.current_bet = player.street_bet
            self._log(player, f'raises to ${player.street_bet}')

        elif action == 'all_in':
            # amount = total street bet target (all chips)
            chips_to_add = min(amount - player.street_bet, player.chips)
            actual = player.put_in(chips_to_add)
            self._add_to_pot(player, actual)
            if player.street_bet > self.current_bet:
                raise_size = player.street_bet - self.current_bet
                if raise_size > 0:
                    self.last_raise_size = raise_size
                self.current_bet = player.street_bet
            self._log(player, f'goes all-in for ${player.total_bet}')

    # ------------------------------------------------------------------
    # Showdown & pot award
    # ------------------------------------------------------------------

    def _showdown(self, result: HandResult) -> HandResult:
        in_hand = [p for p in self.players if p.is_in_hand]

        # Evaluate each player's hand
        scored = []
        for p in in_hand:
            score  = best_hand(p.hole_cards + self.community_cards)
            hname  = hand_name(score)
            scored.append((p, score, hname))
            result.showdown_hands.append((p, hname))

        # Calculate and award side pots
        pots = self._calculate_side_pots(in_hand)
        for pot_amount, eligible in pots:
            if not eligible:
                continue
            eligible_scored = [(p, s, h) for p, s, h in scored if p in eligible]
            best_score = max(eligible_scored, key=lambda x: x[1])[1]
            winners    = [p for p, s, h in eligible_scored if s == best_score]
            share      = pot_amount // len(winners)
            remainder  = pot_amount % len(winners)

            for w in winners:
                w.chips += share
            # Give remainder to first winner
            if remainder:
                winners[0].chips += remainder

            hname = hand_name(best_score)
            for w in winners:
                result.winners.append((w, share, hname))

        return result

    def _award_last_player(self, result: HandResult) -> HandResult:
        """Award pot to the sole remaining player (everyone else folded)."""
        remaining = [p for p in self.players if p.is_in_hand]
        if remaining:
            winner = remaining[0]
            winner.chips += self.pot
            result.winners.append((winner, self.pot, '(uncontested)'))
            result.one_player_left = True
        return result

    def _calculate_side_pots(
        self, active: List[Player]
    ) -> List[Tuple[int, List[Player]]]:
        """
        Correctly split pot when all-in players are present.
        Returns list of (pot_amount, eligible_players).
        """
        # All players who put in chips (including folders — they just can't win)
        all_contributors = {p: self.contributions[p] for p in self.contributions if self.contributions[p] > 0}

        # Sort by contribution level to peel side pots
        levels = sorted(set(all_contributors.values()))
        pots: List[Tuple[int, List[Player]]] = []
        prev = 0

        for level in levels:
            tier_contributors = [p for p, c in all_contributors.items() if c >= level]
            tier_pot = (level - prev) * len(tier_contributors)
            eligible  = [p for p in tier_contributors if p in active]
            if tier_pot > 0:
                pots.append((tier_pot, eligible))
            prev = level

        # Any leftover (rounding / odd chip)
        accounted = sum(p for p, _ in pots)
        leftover  = self.pot - accounted
        if leftover > 0 and active:
            pots.append((leftover, active))

        return pots

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _post_blind(self, player: Player, amount: int) -> None:
        actual = player.put_in(amount)
        self._add_to_pot(player, actual)

    def _add_to_pot(self, player: Player, amount: int) -> None:
        self.pot += amount
        self.contributions[player] = self.contributions.get(player, 0) + amount

    def _deal_community(self, count: int) -> None:
        self.deck.burn()
        for _ in range(count):
            self.community_cards.append(self.deck.deal_one())

    def _reset_street_bets(self) -> None:
        self.current_bet     = 0
        self.last_raise_size = BIG_BLIND
        for p in self.players:
            p.reset_for_street()

    def _from_seat(self, start_idx: int) -> List[Player]:
        n = len(self.players)
        return [self.players[(start_idx + i) % n] for i in range(n)]

    def _acting_order(self) -> List[Player]:
        """Players ordered to act for the current street."""
        n = len(self.players)
        if self.street == 'preflop':
            # UTG acts first  (seat after BB)
            start = (self.bb_idx + 1) % n
        else:
            # SB acts first post-flop
            start = self.sb_idx
        return self._from_seat(start)

    def _make_game_state(self, current_player: Player) -> 'GameState':
        to_call = max(0, self.current_bet - current_player.street_bet)
        min_raise_to = self.current_bet + max(self.last_raise_size, BIG_BLIND)

        is_3bet = (
            self.current_bet >= BIG_BLIND * 3
            and self.street == 'preflop'
        )

        return GameState(
            street=self.street,
            community_cards=list(self.community_cards),
            pot=self.pot,
            current_bet=self.current_bet,
            to_call=to_call,
            min_raise_to=min_raise_to,
            current_player=current_player,
            players=list(self.players),
            hand_number=self.hand_number,
            action_log=list(self.action_log),
            is_3bet=is_3bet,
            last_raise_size=self.last_raise_size,
        )

    def _log(self, player: Player, msg: str) -> None:
        self.action_log.append(f'{player.name} {msg}')


# ---------------------------------------------------------------------------
# GameState — passed to display and action callbacks
# ---------------------------------------------------------------------------

class GameState:
    """Immutable snapshot of the game at the moment a player must act."""

    def __init__(
        self,
        street: str,
        community_cards: List[Card],
        pot: int,
        current_bet: int,
        to_call: int,
        min_raise_to: int,
        current_player: Player,
        players: List[Player],
        hand_number: int,
        action_log: List[str],
        is_3bet: bool,
        last_raise_size: int,
    ) -> None:
        self.street          = street
        self.community_cards = community_cards
        self.pot             = pot
        self.current_bet     = current_bet
        self.to_call         = to_call
        self.min_raise_to    = min_raise_to
        self.current_player  = current_player
        self.players         = players
        self.hand_number     = hand_number
        self.action_log      = action_log
        self.is_3bet         = is_3bet
        self.last_raise_size = last_raise_size

    @property
    def num_active(self) -> int:
        return sum(1 for p in self.players if p.is_in_hand)
