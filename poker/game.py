"""
CLI game loop — display, human input, training hints.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional, Tuple

from poker.bot import Bot
from poker.card import Card
from poker.dealer import Dealer, GameState, HandResult, BIG_BLIND
from poker.hand_evaluator import best_hand, hand_name, preflop_strength, postflop_strength
from poker.player import Player


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_R  = '\033[0m'      # reset
_B  = '\033[1m'      # bold
_DIM= '\033[2m'
_RED= '\033[91m'
_GRN= '\033[92m'
_YLW= '\033[93m'
_BLU= '\033[94m'
_MGN= '\033[95m'
_CYN= '\033[96m'


def _c(text: str, color: str) -> str:
    return f'{color}{text}{_R}'


def _clear() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')


# ---------------------------------------------------------------------------
# Card rendering
# ---------------------------------------------------------------------------

def _card_str(card: Card, hidden: bool = False) -> str:
    if hidden:
        return f'{_DIM}[??]{_R}'
    text = card.display()   # coloured rank+suit
    return f'[{text}]'


def _cards_str(cards: List[Card], hidden: bool = False) -> str:
    if not cards:
        return _c('(none dealt)', _DIM)
    return ' '.join(_card_str(c, hidden) for c in cards)


# ---------------------------------------------------------------------------
# Position info
# ---------------------------------------------------------------------------

_POS_DESC = {
    'BTN':  'Button  (best position — acts last post-flop)',
    'SB':   'Small Blind (forced bet, acts first post-flop)',
    'BB':   'Big Blind   (forced bet, closes pre-flop action)',
    'UTG':  'Under the Gun (first to act pre-flop — most disadvantaged)',
    'CO':   'Cutoff  (one left of button — strong position)',
}


# ---------------------------------------------------------------------------
# Table display
# ---------------------------------------------------------------------------

WIDTH = 64


def _divider(char: str = '─') -> str:
    return char * WIDTH


def _header(title: str) -> str:
    pad  = (WIDTH - len(title) - 2) // 2
    return f'{"─" * pad} {_c(title, _B + _YLW)} {"─" * pad}'


def display_table(gs: GameState) -> None:
    """Render the full table to the terminal."""
    _clear()

    human = gs.current_player

    print(_divider('═'))
    print(_c(f'  TEXAS HOLD\'EM   Hand #{gs.hand_number}', _B + _CYN).center(WIDTH + 20))
    print(_divider('═'))

    # Community cards + pot
    comm_label = gs.street.upper().ljust(8)
    comm_display = _cards_str(gs.community_cards)
    print(f'  {_c(comm_label, _YLW + _B)}  {comm_display}')
    print(f'  {_c("Pot:", _B)}  {_c("$" + str(gs.pot), _GRN + _B)}')
    print(_divider())

    # Player rows
    for p in gs.players:
        _print_player_row(p, human, gs)

    print(_divider())

    # Hole cards for human
    if not human.is_folded:
        hc = _cards_str(human.hole_cards)
        print(f'  {_c("Your cards:", _B)} {hc}')

        # Training: hand strength hint
        if gs.community_cards:
            score = best_hand(human.hole_cards + gs.community_cards)
            hn    = hand_name(score)
            print(f'  {_c("Best hand:", _DIM)} {_c(hn, _YLW)}')
        else:
            pf_s = preflop_strength(human.hole_cards)
            bar  = _strength_bar(pf_s)
            print(f'  {_c("Pre-flop strength:", _DIM)} {bar}  {_c(f"{pf_s:.0%}", _YLW)}')

    # Pot odds when there's something to call
    if gs.to_call > 0:
        odds = gs.to_call / (gs.pot + gs.to_call)
        print(f'  {_c("To call:", _B)} {_c("$" + str(gs.to_call), _YLW)}'
              f'   {_c("Pot odds:", _DIM)} {_c(f"{odds:.0%}", _CYN)} '
              f'{_c("(you need >" + f"{odds:.0%}" + " equity to call)", _DIM)}')

    print(_divider())

    # Recent action log (last 6 lines)
    for line in gs.action_log[-6:]:
        print(f'  {_c(line, _DIM)}')

    if gs.action_log:
        print(_divider())


def _print_player_row(p: Player, hero: Player, gs: GameState) -> None:
    is_hero    = p is hero
    is_current = p is gs.current_player

    indicator  = _c('► ', _GRN + _B) if is_current else '  '

    # Name + label
    if isinstance(p, Bot):
        name_str = _c(f'{p.name} {p.style_label}', _MGN if not is_hero else _CYN + _B)
    else:
        name_str = _c(f'{p.name} [YOU]', _CYN + _B)

    # Status
    if p.is_folded:
        status = _c('FOLDED', _DIM)
    elif p.is_all_in:
        status = _c('ALL-IN', _RED + _B)
    else:
        bet_str = f'bet ${p.street_bet}' if p.street_bet > 0 else ''
        status  = _c(bet_str, _YLW) if bet_str else ''

    # Position
    pos_str = _c(p.position.ljust(3), _BLU + _B)

    # Chips
    chips_str = _c(f'${p.chips}', _GRN)

    # Hole cards (show only hero's, hide bots')
    if is_hero:
        cards = ''   # shown separately
    elif p.is_folded:
        cards = _c('[xx][xx]', _DIM)
    else:
        cards = f'{_DIM}[??][??]{_R}'

    print(f'{indicator}{name_str:<30} {pos_str}  {chips_str:<10} {status}  {cards}')


def _strength_bar(strength: float, width: int = 10) -> str:
    filled  = int(strength * width)
    empty   = width - filled
    bar     = '█' * filled + '░' * empty
    if strength < 0.35:
        color = _RED
    elif strength < 0.60:
        color = _YLW
    else:
        color = _GRN
    return f'{color}{bar}{_R}'


# ---------------------------------------------------------------------------
# Human action input
# ---------------------------------------------------------------------------

def get_human_action(gs: GameState) -> Tuple[str, int]:
    """Prompt the human player for an action and return (action, amount)."""
    player     = gs.current_player
    to_call    = gs.to_call
    pot        = gs.pot
    min_raise  = gs.min_raise_to
    big_blind  = BIG_BLIND

    print(f'\n  {_c("YOUR TURN", _B + _YLW)}  —  {_c(player.position, _BLU + _B)}  '
          f'{_c("(" + _POS_DESC.get(player.position, player.position) + ")", _DIM)}')

    # Build available actions
    options: List[str] = []
    actions_map: dict  = {}

    if to_call == 0:
        options.append(_c('[K]', _GRN) + ' Check')
        actions_map['k'] = ('check', 0)
        options.append(_c('[B]', _YLW) + f' Bet  (min ${big_blind})')
        actions_map['b'] = 'bet'
    else:
        options.append(_c('[F]', _RED)  + ' Fold')
        actions_map['f'] = ('fold', 0)
        options.append(_c('[C]', _GRN)  + f' Call ${to_call}')
        actions_map['c'] = ('call', gs.current_bet)
        options.append(_c('[R]', _YLW)  + f' Raise  (min to ${min_raise})')
        actions_map['r'] = 'raise'

    if player.chips > to_call:
        options.append(_c('[A]', _MGN + _B) + f' All-In (${player.chips})')
        actions_map['a'] = ('all_in', player.chips + player.street_bet)

    print('  ' + '   '.join(options))

    while True:
        try:
            raw = input(f'\n  {_c("Action", _B)}: ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            print('\n  Folding (interrupted).')
            return ('fold', 0)

        if raw == '' :
            continue

        key = raw[0]

        if key not in actions_map:
            print(f'  {_c("Invalid choice. Try again.", _RED)}')
            continue

        val = actions_map[key]

        if val == 'bet':
            amount = _ask_amount(
                f'  Bet amount (min ${big_blind}, max ${player.chips + player.street_bet}): ',
                min_val=big_blind,
                max_val=player.chips + player.street_bet,
            )
            if amount is None:
                continue
            return ('bet', player.street_bet + amount)

        if val == 'raise':
            amount = _ask_amount(
                f'  Raise to (min ${min_raise}, max ${player.chips + player.street_bet}): ',
                min_val=min_raise,
                max_val=player.chips + player.street_bet,
            )
            if amount is None:
                continue
            return ('raise', amount)

        return val  # type: ignore[return-value]


def _ask_amount(prompt: str, min_val: int, max_val: int) -> Optional[int]:
    try:
        raw = input(prompt).strip()
        amount = int(raw)
        if amount < min_val or amount > max_val:
            print(f'  {_c(f"Must be between ${min_val} and ${max_val}.", _RED)}')
            return None
        return amount
    except ValueError:
        print(f'  {_c("Please enter a number.", _RED)}')
        return None


# ---------------------------------------------------------------------------
# Hand summary
# ---------------------------------------------------------------------------

def display_hand_result(result: HandResult, players: List[Player]) -> None:
    print()
    print(_divider('═'))
    print(_c('  HAND RESULT', _B + _YLW))
    print(_divider())

    if result.showdown_hands:
        print(f'  {_c("Showdown:", _B)}')
        for p, hn in result.showdown_hands:
            cards = _cards_str(p.hole_cards)
            print(f'    {_c(p.name, _B)}: {cards}  → {_c(hn, _YLW)}')
        print()

    for player, amount, hn in result.winners:
        print(f'  {_c("Winner:", _GRN + _B)} {player.name}  wins {_c("$" + str(amount), _GRN + _B)}'
              f'  with {_c(hn, _YLW)}')

    print(_divider())
    print(f'  {_c("Chip counts:", _B)}')
    for p in players:
        bar = _strength_bar(min(p.chips / 2000, 1.0), width=8)
        print(f'    {p.name:<14}  {_c("$" + str(p.chips), _GRN)}  {bar}')
    print(_divider('═'))


# ---------------------------------------------------------------------------
# Main Game class
# ---------------------------------------------------------------------------

class Game:
    def __init__(self, human_name: str = 'You', starting_chips: int = 1_000) -> None:
        from poker.bot import create_bots

        self.human  = Player(human_name, chips=starting_chips)
        self.bots   = create_bots()
        self.players: List[Player] = [self.human] + self.bots

        self.dealer = Dealer(
            players=self.players,
            action_callback=self._action_callback,
            display_callback=self._display_callback,
            bot_delay=0.7,
        )

    # ------------------------------------------------------------------

    def run(self) -> None:
        self._show_intro()

        while True:
            # Remove broke players and add fresh ones if needed
            self._refresh_players()

            if self.human.chips <= 0:
                print(_c('\n  You are out of chips! Game over.', _RED + _B))
                break

            if len([p for p in self.players if p.chips > 0]) < 2:
                print(_c('\n  Not enough players with chips to continue.', _YLW))
                break

            result = self.dealer.play_hand()

            _clear()
            self._show_final_board()
            display_hand_result(result, self.players)

            if not self._continue_prompt():
                break

        print(_c('\n  Thanks for playing!', _CYN + _B))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _action_callback(self, player: Player, gs: GameState) -> Tuple[str, int]:
        if isinstance(player, Bot):
            return player.decide(
                community_cards=gs.community_cards,
                pot=gs.pot,
                current_bet=gs.current_bet,
                min_raise_to=gs.min_raise_to,
                num_active=gs.num_active,
                is_3bet=gs.is_3bet,
            )
        else:
            return get_human_action(gs)

    def _display_callback(self, gs: GameState) -> None:
        if gs.current_player is self.human:
            display_table(gs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_intro(self) -> None:
        _clear()
        print(_divider('═'))
        print(_c('  TEXAS HOLD\'EM POKER — Training Table', _B + _CYN).center(WIDTH + 20))
        print(_divider())
        print(f'  Blinds: ${BIG_BLIND // 2}/${BIG_BLIND}    Starting stack: ${self.human.chips}')
        print()
        print(f'  {_c("Your opponents:", _B)}')
        for b in self.bots:
            print(f'    {_c(b.name, _MGN + _B):<20} {_c(b.personality.description, _DIM)}')
        print()
        print(f'  {_c("Training hints shown automatically:", _DIM)}')
        print(f'    • Pre-flop hand strength bar')
        print(f'    • Best hand label on the flop/turn/river')
        print(f'    • Pot odds when facing a bet')
        print(f'    • Position description on your turn')
        print(_divider('═'))
        input(f'  {_c("Press Enter to start...", _YLW)}')

    def _show_final_board(self) -> None:
        """Show final community cards after the hand ends."""
        comm = _cards_str(self.dealer.community_cards)
        print(_divider())
        print(f'  {_c("Board:", _B)} {comm}')

    def _continue_prompt(self) -> bool:
        raw = input(f'\n  {_c("Play next hand? [Y/n]: ", _YLW)}').strip().lower()
        return raw in ('', 'y', 'yes')

    def _refresh_players(self) -> None:
        """
        Re-buy broke bots so the table never falls below 5 players.
        The human cannot be re-bought automatically.
        """
        for p in self.bots:
            if p.chips <= 0:
                p.chips = 1_000   # bot re-buy
                print(_c(f'  {p.name} re-buys for $1,000.', _DIM))
