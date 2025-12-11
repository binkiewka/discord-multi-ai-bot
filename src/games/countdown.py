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
from typing import Optional, List, Dict, Any, Tuple

from .expression_parser import ExpressionParser


class GameStatus(Enum):
    """Status of a game instance."""
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


@dataclass
class GameLobby:
    """Represents a game lobby waiting for players to ready up."""
    host_id: str
    channel_id: str
    server_id: str
    message_id: Optional[str] = None
    rounds: int = 3
    seconds_per_round: int = 60
    ready_players: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> 'GameLobby':
        """Deserialize from JSON string."""
        parsed = json.loads(data)
        return cls(**parsed)


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
    # Multi-round support
    current_round: int = 1
    total_rounds: int = 1
    round_duration: int = 60
    game_scores: Dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> 'GameState':
        """Deserialize from JSON string."""
        parsed = json.loads(data)
        return cls(**parsed)

    def time_remaining(self) -> float:
        """Get seconds remaining in the round."""
        return max(0, self.end_time - time.time())

    def is_expired(self) -> bool:
        """Check if the round timer has expired."""
        return time.time() >= self.end_time

    def is_final_round(self) -> bool:
        """Check if this is the last round."""
        return self.current_round >= self.total_rounds


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

    def _leaderboard_key(self, server_id: str) -> str:
        """Generate Redis key for server leaderboard."""
        return f"countdown:leaderboard:{server_id}"

    def _lobby_key(self, server_id: str, channel_id: str) -> str:
        """Generate Redis key for lobby state."""
        return f"countdown:lobby:{server_id}:{channel_id}"

    # ==================== LOBBY METHODS ====================

    def create_lobby(self, server_id: str, channel_id: str, host_id: str) -> GameLobby:
        """Create a new game lobby."""
        # Check if lobby or game already exists
        existing_lobby = self.get_lobby(server_id, channel_id)
        if existing_lobby:
            raise ValueError("A lobby is already open in this channel!")

        existing_game = self.get_active_game(server_id, channel_id)
        if existing_game:
            raise ValueError("A game is already active in this channel!")

        lobby = GameLobby(
            host_id=host_id,
            channel_id=channel_id,
            server_id=server_id,
            ready_players=[host_id]  # Host is automatically ready
        )

        self._save_lobby(server_id, channel_id, lobby)
        return lobby

    def _save_lobby(self, server_id: str, channel_id: str, lobby: GameLobby) -> None:
        """Save lobby state to Redis."""
        key = self._lobby_key(server_id, channel_id)
        self.redis.redis.set(key, lobby.to_json())
        self.redis.redis.expire(key, 300)  # 5 minute TTL for lobby

    def get_lobby(self, server_id: str, channel_id: str) -> Optional[GameLobby]:
        """Get existing lobby for a channel."""
        key = self._lobby_key(server_id, channel_id)
        data = self.redis.redis.get(key)
        if data:
            return GameLobby.from_json(data)
        return None

    def update_lobby(self, server_id: str, channel_id: str, lobby: GameLobby) -> None:
        """Update lobby state."""
        self._save_lobby(server_id, channel_id, lobby)

    def delete_lobby(self, server_id: str, channel_id: str) -> None:
        """Delete lobby from Redis."""
        key = self._lobby_key(server_id, channel_id)
        self.redis.redis.delete(key)

    def toggle_ready(self, server_id: str, channel_id: str, user_id: str) -> GameLobby:
        """Toggle a player's ready status."""
        lobby = self.get_lobby(server_id, channel_id)
        if not lobby:
            raise ValueError("No lobby found!")

        if user_id in lobby.ready_players:
            lobby.ready_players.remove(user_id)
        else:
            lobby.ready_players.append(user_id)

        self._save_lobby(server_id, channel_id, lobby)
        return lobby

    def _save_game(self, server_id: str, channel_id: str, state: GameState) -> None:
        """Save game state to Redis."""
        key = self._game_key(server_id, channel_id)
        self.redis.redis.set(key, state.to_json())
        # TTL based on total game duration (all rounds + buffer)
        ttl = (state.round_duration * state.total_rounds) + 120
        self.redis.redis.expire(key, ttl)

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

    def create_game(self, server_id: str, channel_id: str, started_by: str,
                    total_rounds: int = 1, round_duration: int = 60) -> GameState:
        """
        Create a new game in a channel.

        Args:
            server_id: Discord server/guild ID
            channel_id: Discord channel ID
            started_by: User ID who started the game
            total_rounds: Number of rounds to play
            round_duration: Duration of each round in seconds

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
            end_time=now + round_duration,
            status=GameStatus.ACTIVE.value,
            channel_id=channel_id,
            started_by=started_by,
            current_round=1,
            total_rounds=total_rounds,
            round_duration=round_duration,
            game_scores={}
        )

        # Store in Redis
        self._save_game(server_id, channel_id, state)
        return state

    def create_game_from_lobby(self, lobby: GameLobby) -> GameState:
        """Create a game from an existing lobby."""
        # Delete the lobby first
        self.delete_lobby(lobby.server_id, lobby.channel_id)

        # Create the game with lobby settings
        return self.create_game(
            server_id=lobby.server_id,
            channel_id=lobby.channel_id,
            started_by=lobby.host_id,
            total_rounds=lobby.rounds,
            round_duration=lobby.seconds_per_round
        )

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
        End the game completely and return results.

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

    def end_round(self, server_id: str, channel_id: str) -> Tuple[GameState, List[Submission]]:
        """
        End the current round and return results.
        Does NOT delete the game - just collects submissions and clears them for next round.

        Returns:
            Tuple of (GameState, list of Submissions for this round)
        """
        game = self.get_active_game(server_id, channel_id)
        if not game:
            raise ValueError("No active game to end round")

        submissions = self._get_all_submissions(server_id, channel_id)

        # Clear submissions for next round
        self._delete_submissions(server_id, channel_id)

        return game, submissions

    def advance_round(self, server_id: str, channel_id: str,
                      round_points: Dict[str, int]) -> Optional[GameState]:
        """
        Advance to the next round with new numbers and target.
        Updates cumulative game scores.

        Args:
            server_id: Discord server/guild ID
            channel_id: Discord channel ID
            round_points: Points earned this round {user_id: points}

        Returns:
            Updated GameState if more rounds remain, None if game is complete
        """
        game = self.get_active_game(server_id, channel_id)
        if not game:
            raise ValueError("No active game")

        # Update cumulative scores
        for user_id, points in round_points.items():
            game.game_scores[user_id] = game.game_scores.get(user_id, 0) + points

        # Check if this was the final round
        if game.is_final_round():
            # End the game completely
            game.status = GameStatus.ENDED.value
            self._delete_game(server_id, channel_id)
            return None

        # Advance to next round
        game.current_round += 1
        numbers, large, small = self.generate_numbers()
        target = self.generate_target()
        now = time.time()

        game.target = target
        game.numbers = numbers
        game.large_numbers = large
        game.small_numbers = small
        game.start_time = now
        game.end_time = now + game.round_duration

        # Save updated game
        self._save_game(server_id, channel_id, game)
        return game

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

    def update_scores(self, server_id: str, submissions: List[Submission]) -> Dict[str, int]:
        """
        Update player scores based on game results.
        
        Points:
        - Exact match (dist 0): 10 points
        - Within 10: 5 points
        - Within 25: 2 points
        
        Args:
            server_id: Discord server ID
            submissions: List of submissions
            
        Returns:
            Dictionary of {user_id: points_earned}
        """
        key = self._leaderboard_key(server_id)
        points_earned = {}
        
        for sub in submissions:
            if not sub.valid:
                continue
                
            points = 0
            if sub.distance == 0:
                points = 10
            elif sub.distance <= 10:
                points = 5
            elif sub.distance <= 25:
                points = 2
            
            if points > 0:
                # Update Redis sorted set
                self.redis.redis.zincrby(key, points, sub.user_id)
                points_earned[sub.user_id] = points
                
        return points_earned

    def get_leaderboard(self, server_id: str, limit: int = 10) -> List[Tuple[str, int]]:
        """
        Get top players for the server.
        
        Args:
            server_id: Discord server ID
            limit: Number of players to return
            
        Returns:
            List of (user_id, score) tuples
        """
        key = self._leaderboard_key(server_id)
        # zrevrange returns list of (member, score) with withscores=True
        # Redis-py returns bytes for member, float for score usually
        data = self.redis.redis.zrevrange(key, 0, limit - 1, withscores=True)
        
        # Clean up data (decode bytes, int score)
        leaderboard = []
        for member, score in data:
            if isinstance(member, bytes):
                member = member.decode('utf-8')
            leaderboard.append((member, int(score)))
            
        return leaderboard
