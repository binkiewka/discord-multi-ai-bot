"""
Countdown Numbers Game - Core game logic and state management.

A fork of the classic IRC/TV numbers game where players must reach a target
number using arithmetic operations on a set of given numbers.
"""

import random
import time
import json
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Optional, List, Dict, Any

from .expression_parser import ExpressionParser


class GameStatus(Enum):
    """Status of a game instance."""
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


@dataclass
class GameState:
    """Represents the state of an active Countdown game."""
    target: int
    numbers: List[int]
    large_numbers: List[int]
    small_numbers: List[int]
    start_time: float
    end_time: float
    status: str
    channel_id: str
    started_by: str
    message_id: Optional[str] = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> 'GameState':
        """Deserialize from JSON string."""
        parsed = json.loads(data)
        return cls(**parsed)

    def time_remaining(self) -> float:
        """Get seconds remaining in the game."""
        return max(0, self.end_time - time.time())

    def is_expired(self) -> bool:
        """Check if the game timer has expired."""
        return time.time() >= self.end_time


@dataclass
class Submission:
    """Represents a player's answer submission."""
    user_id: str
    expression: str
    result: Optional[int]
    distance: int
    valid: bool
    error: Optional[str]
    submitted_at: float

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> 'Submission':
        """Deserialize from JSON string."""
        parsed = json.loads(data)
        return cls(**parsed)


class CountdownGame:
    """
    Main game manager for the Countdown Numbers Game.

    Handles game creation, answer submission, and result determination.
    Uses Redis for persistent state storage.
    """

    # Game configuration
    LARGE_NUMBERS = [25, 50, 75, 100]
    SMALL_NUMBERS = list(range(1, 11))  # 1-10
    GAME_DURATION = 30  # seconds
    NUM_LARGE = 2
    NUM_SMALL = 3
    TARGET_MIN = 100
    TARGET_MAX = 999

    def __init__(self, redis_client):
        """
        Initialize the game manager.

        Args:
            redis_client: RedisClient instance for state persistence
        """
        self.redis = redis_client
        self.parser = ExpressionParser()

    def generate_numbers(self) -> tuple:
        """
        Generate the numbers for a game round.

        Returns:
            Tuple of (all_numbers, large_numbers, small_numbers)
        """
        large = random.sample(self.LARGE_NUMBERS, self.NUM_LARGE)
        small = random.choices(self.SMALL_NUMBERS, k=self.NUM_SMALL)  # Can repeat
        return large + small, large, small

    def generate_target(self) -> int:
        """Generate a random target number."""
        return random.randint(self.TARGET_MIN, self.TARGET_MAX)

    def _game_key(self, server_id: str, channel_id: str) -> str:
        """Generate Redis key for game state."""
        return f"countdown:game:{server_id}:{channel_id}"

    def _submissions_key(self, server_id: str, channel_id: str) -> str:
        """Generate Redis key for submissions."""
        return f"countdown:submissions:{server_id}:{channel_id}"

    def _save_game(self, server_id: str, channel_id: str, state: GameState) -> None:
        """Save game state to Redis."""
        key = self._game_key(server_id, channel_id)
        self.redis.redis.set(key, state.to_json())
        self.redis.redis.expire(key, 120)  # 2 minute TTL

    def get_active_game(self, server_id: str, channel_id: str) -> Optional[GameState]:
        """
        Get the active game for a channel, if any.

        Returns:
            GameState if active game exists, None otherwise
        """
        key = self._game_key(server_id, channel_id)
        data = self.redis.redis.get(key)
        if data:
            game = GameState.from_json(data)
            if game.status == GameStatus.ACTIVE.value:
                return game
        return None

    def create_game(self, server_id: str, channel_id: str, started_by: str) -> GameState:
        """
        Create a new game in a channel.

        Args:
            server_id: Discord server/guild ID
            channel_id: Discord channel ID
            started_by: User ID who started the game

        Returns:
            The newly created GameState

        Raises:
            ValueError: If a game is already active in the channel
        """
        # Check if game already active
        existing = self.get_active_game(server_id, channel_id)
        if existing:
            raise ValueError("A game is already active in this channel! Wait for it to finish or use the current one.")

        numbers, large, small = self.generate_numbers()
        target = self.generate_target()
        now = time.time()

        state = GameState(
            target=target,
            numbers=numbers,
            large_numbers=large,
            small_numbers=small,
            start_time=now,
            end_time=now + self.GAME_DURATION,
            status=GameStatus.ACTIVE.value,
            channel_id=channel_id,
            started_by=started_by
        )

        # Store in Redis
        self._save_game(server_id, channel_id, state)
        return state

    def _save_submission(self, server_id: str, channel_id: str,
                         user_id: str, submission: Submission) -> None:
        """Save a player's submission to Redis."""
        key = self._submissions_key(server_id, channel_id)
        self.redis.redis.hset(key, user_id, submission.to_json())
        self.redis.redis.expire(key, 120)

    def _get_submission(self, server_id: str, channel_id: str,
                        user_id: str) -> Optional[Submission]:
        """Get a player's existing submission, if any."""
        key = self._submissions_key(server_id, channel_id)
        data = self.redis.redis.hget(key, user_id)
        return Submission.from_json(data) if data else None

    def _get_all_submissions(self, server_id: str, channel_id: str) -> List[Submission]:
        """Get all submissions for the current game."""
        key = self._submissions_key(server_id, channel_id)
        all_data = self.redis.redis.hgetall(key)
        return [Submission.from_json(v) for v in all_data.values()]

    def _delete_game(self, server_id: str, channel_id: str) -> None:
        """Delete game state from Redis."""
        self.redis.redis.delete(self._game_key(server_id, channel_id))

    def _delete_submissions(self, server_id: str, channel_id: str) -> None:
        """Delete all submissions from Redis."""
        self.redis.redis.delete(self._submissions_key(server_id, channel_id))

    def submit_answer(self, server_id: str, channel_id: str,
                      user_id: str, expression: str) -> Submission:
        """
        Process a player's answer submission.

        Args:
            server_id: Discord server/guild ID
            channel_id: Discord channel ID
            user_id: User ID submitting the answer
            expression: Mathematical expression to evaluate

        Returns:
            The Submission object with validation results

        Raises:
            ValueError: If no game active, time expired, or already submitted
        """
        game = self.get_active_game(server_id, channel_id)
        if not game:
            raise ValueError("No active game in this channel! Start one with `!countdown`")

        if game.is_expired():
            raise ValueError("Time's up! The game has ended.")

        # Check if user already submitted
        existing = self._get_submission(server_id, channel_id, user_id)
        if existing:
            raise ValueError("You already submitted an answer! Wait for results.")

        # Parse and validate expression
        result = self.parser.parse_and_validate(expression, game.numbers)

        if result['valid']:
            # Calculate distance from target
            distance = abs(game.target - int(result['result']))
            submission = Submission(
                user_id=user_id,
                expression=expression,
                result=int(result['result']),
                distance=distance,
                valid=True,
                error=None,
                submitted_at=time.time()
            )
        else:
            submission = Submission(
                user_id=user_id,
                expression=expression,
                result=None,
                distance=999999,  # Invalid = worst possible distance
                valid=False,
                error=result['error'],
                submitted_at=time.time()
            )

        # Store submission
        self._save_submission(server_id, channel_id, user_id, submission)
        return submission

    def end_game(self, server_id: str, channel_id: str) -> tuple:
        """
        End the game and return results.

        Args:
            server_id: Discord server/guild ID
            channel_id: Discord channel ID

        Returns:
            Tuple of (GameState, list of Submissions)

        Raises:
            ValueError: If no game to end
        """
        game = self.get_active_game(server_id, channel_id)
        if not game:
            raise ValueError("No active game to end")

        submissions = self._get_all_submissions(server_id, channel_id)

        # Update game status
        game.status = GameStatus.ENDED.value

        # Clean up Redis
        self._delete_game(server_id, channel_id)
        self._delete_submissions(server_id, channel_id)

        return game, submissions

    def determine_winners(self, submissions: List[Submission]) -> List[Submission]:
        """
        Determine winner(s) from submissions.

        Winners are those with the smallest distance to target.
        Ties are broken by submission time (earlier wins).

        Args:
            submissions: List of all submissions

        Returns:
            Sorted list of valid submissions (best first)
        """
        valid_subs = [s for s in submissions if s.valid]
        if not valid_subs:
            return []

        # Sort by distance (ascending), then by submission time (earlier wins)
        sorted_subs = sorted(valid_subs, key=lambda s: (s.distance, s.submitted_at))
        return sorted_subs

    def cancel_game(self, server_id: str, channel_id: str) -> bool:
        """
        Cancel an active game.

        Args:
            server_id: Discord server/guild ID
            channel_id: Discord channel ID

        Returns:
            True if game was cancelled, False if no game existed
        """
        game = self.get_active_game(server_id, channel_id)
        if not game:
            return False

        self._delete_game(server_id, channel_id)
        self._delete_submissions(server_id, channel_id)
        return True
