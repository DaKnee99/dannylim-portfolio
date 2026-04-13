"""Card primitives."""

SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
RANK_VALUES = {rank: i + 2 for i, rank in enumerate(RANKS)}

_RED = '\033[91m'
_RESET = '\033[0m'


class Card:
    __slots__ = ('rank', 'suit', 'value')

    def __init__(self, rank: str, suit: str) -> None:
        self.rank = rank
        self.suit = suit
        self.value = RANK_VALUES[rank]

    # Colored string for display (red for hearts/diamonds)
    def display(self) -> str:
        if self.suit in ('♥', '♦'):
            return f'{_RED}{self.rank}{self.suit}{_RESET}'
        return f'{self.rank}{self.suit}'

    def __str__(self) -> str:
        return f'{self.rank}{self.suit}'

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Card) and self.rank == other.rank and self.suit == other.suit

    def __hash__(self) -> int:
        return hash((self.rank, self.suit))
