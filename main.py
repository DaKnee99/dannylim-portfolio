#!/usr/bin/env python3
"""
Texas Hold'em Poker — Training Table
Run:  python main.py
"""

from poker.game import Game


def main() -> None:
    name = input('Enter your name (or press Enter for "Hero"): ').strip() or 'Hero'
    game = Game(human_name=name, starting_chips=1_000)
    game.run()


if __name__ == '__main__':
    main()
