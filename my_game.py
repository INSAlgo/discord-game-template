#!/usr/bin/env python3

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Callable, Any
from io import StringIO
from pathlib import Path
import argparse, asyncio, os, re, sys

# You can add game constants here, like a board size for example

# Default Timeouts :
TIMEOUT_LENGTH = 0.1
DISCORD_TIMEOUT = 60

# Usefull emojis :
EMOJI_NUMBERS = ('0️⃣', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣')
EMOJI_COLORS = ('🟠', '🔴', '🟡', '🟢', '🔵', '🟣', '🟤',  '⚪️', '⚫️')

# what is the type of a valid move or a valid input (when it has a specific format) to use in typing
ValidMove = Any
ValidInput = str

# input and output functions types
InputFunction = Callable[..., str]      # function asking a discord player to make a move, returns the discord answer
OutputFunction = Callable[[str], None]  # function called when an AI wants to "talk" to discord, the argument being the message


class Player(ABC):

    ofunc = None

    def __init__(self, no: int, name: str = None, **kwargs):
        """The abstract Player constructor

        Args:
            no (int): player number/id
            name (str, optional): The player name. Defaults to None.
        """
        # You can add any number of kwargs you want that will be passed in the discord command for your game
        
        self.no = no

        # These can be altered to give personnality to your game display (with emojis for example)
        self.icon = self.no
        self.name = name
        self.rendered_name = None

    @abstractmethod
    async def start_game(self):
        self.alive = True

    @abstractmethod
    async def lose_game(self):
        await Player.print(f"{self} is eliminated")

    @abstractmethod
    async def ask_move(self, **kwargs) -> tuple[ValidMove, None] | tuple[None | str]:
        pass

    @abstractmethod
    async def tell_move(self, move: ValidInput):
        pass

    async def tell_other_players(self, players: list[Player], move: ValidInput):
        for other_player in players:
            if self != other_player and other_player.alive:
                await other_player.tell_move(move)

    @staticmethod
    async def sanithize(userInput: str, **kwargs) -> tuple[ValidMove, None] | tuple[None | str]:
        """Parses raw user input text into an error message or a valid move

        Args:
            userInput (`str`): the raw user input text

        Returns:
            `tuple[ValidMove, None] | tuple[None | str]`
        """
        # You can add any number of kwargs you want
        # that will be necessary to parse the input
        # (like the game board for example),
        # just remember to pass them when calling this method.
        
        if userInput == "stop" :
            # When a human player (or an AI, who knows) wants to abandon.
            return None, "user interrupt"
        
        # Here, you can process your userInput,
        # try to get all wrong input cases out as errors
        # to make sure your game doesn't break.

        processed_input: ValidMove = userInput

        return processed_input, None

    @staticmethod
    async def print(output: StringIO | str, send_discord=True, end="\n"):
        if isinstance(output, StringIO):
            text = output.getvalue()
            output.close()
        else:
            text = output + end
        print(text, end="")
        if Player.ofunc and send_discord:
            await Player.ofunc(text)

    def __str__(self):
        return self.rendered_name


class Human(Player):

    def __init__(self, no: int, name: str = None, ifunc: InputFunction = None, **kwargs):
        """The human player constructor
        Let ifunc be None to get terminal input (for a local game)

        Args:
            no (`int`): player number/id
            name (`str`, optional): The player name. Defaults to None.
            ifunc (`InputFunction`, optional): The input function. Defaults to None.
        """
        super().__init__(no, name, **kwargs)
        self.ifunc = ifunc

        # Here you can personnalize human players name specifically
        self.rendered_name = f"{self.name} {self.icon}" if name else f"Player {self.icon}"

    async def start_game(self):
        await super().start_game()

    async def lose_game(self):
        await super().lose_game()
    
    # Don't forget to replace <**kwargs> with the arguments necessary for parsing the input
    async def ask_move(self, **kwargs):
        await super().ask_move(**kwargs)
        # You can customize your message asking for a move here :
        await Player.print(f"Awaiting {self}'s move : ", end="")
        try:
            user_input = await self.input()
        except asyncio.TimeoutError:
            await Player.print(f"User did not respond in time (over {DISCORD_TIMEOUT}s)")
            return None, "timeout"
        # This is where the kwargs are usefull :
        return await Human.sanithize(user_input, **kwargs)

    async def tell_move(self, move: ValidInput):
        return super().tell_move(move)

    async def input(self):
        if self.ifunc:
            user_input = await asyncio.wait_for(self.ifunc(self.name), timeout=DISCORD_TIMEOUT)
            await Player.print(user_input, send_discord=False)
            return user_input
        else:
            return input()

class AI(Player):

    @staticmethod
    def prepare_command(progPath: str | Path):
        """Prepares the command to start the AI

        Args:
            progPath (`str` | `Path`): the path to the program

        Raises:
            Exception: File not found error

        Returns:
            `str`: the command to start the AI
        """
        path = Path(progPath)
        if not path.is_file():
            raise FileNotFoundError(f"File {progPath} not found\n")

        match path.suffix:
            case ".py":
                return f"python3 {progPath}"
            case ".js":
                return f"node {progPath}"
            case ".class":
                return f"java -cp {os.path.dirname(progPath)} {os.path.splitext(os.path.basename(progPath))[0]}"
            case _:
                return f"./{progPath}"

    def __init__(self, no: int, prog_path: str, discord: bool, **kwargs):
        """The AI player constructor

        Args:
            no (int): player number/id
            prog_path (str): AI's program path
            discord (bool): if it is instantiated through discord to associate the user tag
        """
        super().__init__(no, Path(prog_path).stem, **kwargs)
        self.prog_path = prog_path
        self.command = AI.prepare_command(self.prog_path)

        # Once again, you can personnalize how the AI player will be called during the game here
        if discord:
            # if it's through discord, self.name should be the discord user's ID
            self.rendered_name = f"<@{self.name}>'s AI {self.icon}"
        else:
            self.rendered_name = f"AI {self.icon} ({self.name})"
    
    async def drain(self):
        if self.prog.stdin.transport._conn_lost:
            self.prog.stdin.close()
            self.prog.stdin = asyncio.subprocess.PIPE
        await self.prog.stdin.drain()

    async def start_game(self, **kwargs):
        # You can specify here what parameters are required to start a game for an AI player.
        # For example : board size, number of players...
        await super().start_game()
        self.prog = await asyncio.create_subprocess_shell(
            AI.prepare_command(self.prog_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        if self.prog.stdin:
            # Here, write the NORMALIZED message you'll send to the AIs for them to start the game.
            # This is what this method's kwargs are for, the AI will need 
            self.prog.stdin.write(f"Your message here\n".encode())
            await self.drain()

    async def lose_game(self):
        await super().lose_game()

    # Don't forget to replace <**kwargs> with the arguments necessary for parsing the input
    async def ask_move(self, debug: bool = True, **kwargs) -> tuple[tuple[int, int] | None, str | None]:
        await super().ask_move(**kwargs)
        try:
            while True:
                if not self.prog.stdout:
                    return None, "communication failed"
                progInput = await asyncio.wait_for(self.prog.stdout.readuntil(), TIMEOUT_LENGTH)

                if not isinstance(progInput, bytes):
                    continue
                progInput = progInput.decode().strip()

                if progInput.startswith("Traceback"):
                    output = StringIO()
                    if debug:
                        print(file=output)
                        print(progInput, file=output)
                        progInput = self.prog.stdout.read()
                        if isinstance(progInput, bytes):
                            print(progInput.decode(), file=output)
                        await Player.print(output)
                    return None, "error"
                
                if progInput.startswith(">"):
                    # Any bot can write lines starting with ">" to debug in local.
                    # It is recommended to remove any debug before playing
                    # against other players to avoid reverse engineering!
                    if debug:
                        await Player.print(f"{self} {progInput}")
                else:
                    break

            # You can customize the message all bots will send to announce their moves here :
            await Player.print(f"{self}'s move : {progInput}")

        except (asyncio.TimeoutError, asyncio.exceptions.IncompleteReadError):
            await Player.print(f"AI did not respond in time (over {TIMEOUT_LENGTH}s)")
            return None, "timeout"
        
        # This is where the kwargs are usefull :
        return await AI.sanithize(progInput, **kwargs)

    async def tell_move(self, move: ValidInput):
        if self.prog.stdin:
            # The AIs should keep track of who's playing themselves.
            self.prog.stdin.write(f"{move}n".encode())
            await self.drain()

    async def stop_game(self):
        try:
            self.prog.terminate()
            await self.prog.wait()
        except ProcessLookupError:
            pass


# Here is a place to define functions useful for your game, typically:
#  - checking for a win or a draw,
#  - drawing the grid in terminal or in discord
#  - processing a move
#  - ...


async def game(players: list[Human | AI], debug: bool, **kwargs) -> tuple[list[Human | AI], Human | AI | None, dict]:
    """The function handling all the game logic.
    Once again, you can add as many kwargs as you need.
    Note that you can return anything you need that will be treated in `main()` after the specified args.

    Args:
        players (`list[Human | AI]`): The list of players
        debug (`bool`): _description_

    Returns:
        `tuple[list[Human | AI], Human | AI | None, dict, ...]`: A whole bunch of game data to help display and judge the result
    """

    nb_players = len(players)
    alive_players = nb_players
    errors = {} # This is for logging and debugginf purposes
    starters = (player.start_game(**kwargs) for player in players)
    await asyncio.gather(*starters)
    turn = 0
    winner = None

    # Initialize general game objects here, like the board

    # game loop
    while alive_players >= 2:
        i = turn % nb_players
        player = players[i]

        if not player.alive:
            # It is essential to notify of a player "death" so that AIs can skip their turn.
            # Replace `None` by a NORMALIZED simple value signifying an incorrect move. 
            await player.tell_other_players(players, None)

        else :
            await Player.print() # Render the grid for the player here

            # player input
            user_input, error = None, None
            while not user_input:
                # Don't forget to give the kwargs necessary for an AI (or a player) to understand what's asked
                user_input, error = await player.ask_move(debug, **kwargs)
                if isinstance(player, AI) or error in ("user interrupt", "timeout"):
                    break

            # saving eventual error
            if not user_input:
                await player.lose_game()
                errors[player] = error
                player.alive = False
                alive_players -= 1
                # It is essential to notify of a player "death" so that AIs can skip their turn.
                # Replace `None` by a NORMALIZED simple value signifying an incorrect move. 
                await player.tell_other_players(players, None)

            else:
                # Apply the user_input to the game here, it already went through sanithization so it is a ValidMove
                # You'll also need to convert to a ValidInput to notify all the AIs of the played move
                await player.tell_other_players(players, "valid input here")
            
                # Check for wins or draw here.
                # Any end must break the `while alive_players >= 2`.
                # Do this step early to avoid an infinite loop!
        
        turn += 1

    if alive_players == 1:
        # nobreak
        winner = [player for player in players if player.alive][0]
    
    enders = (player.stop_game() for player in players if isinstance(player, AI))
    await asyncio.gather(*enders)

    # You can add extra returned stuff here, like the final board and other stuff
    return players, winner, errors


async def main(raw_args: str = None, ifunc: InputFunction = None, ofunc: OutputFunction = None, discord=False):
    # these arguments should not be messed with because that's how the discord bot works

    parser = argparse.ArgumentParser()
    parser.add_argument("prog", nargs="*", \
            help="AI program to play the game ('user' to play yourself)")
    parser.add_argument("-p", "--players", type=int, default=2, metavar="NB_PLAYERS", \
            help="number of players (if more players than programs are provided, the other ones will be filled as real players)")
    parser.add_argument("-s", "--silent", action="store_true", \
            help="only show the result of the game")
    parser.add_argument("-n", "--nodebug", action="store_true", \
            help="do not print the debug output of the programs")
    # Add here any extra argument you need to define the game (board size for example)

    args = parser.parse_args(raw_args)

    Player.ofunc = ofunc
    players = []
    ai_only = True
    pattern = re.compile(r"^\<\@[0-9]{18}\>$")
    for i, name in enumerate(args.prog):
        if name == "user":
            players.append(Human(i))                # Add extra arguments extracted from `args`
            ai_only = False
        elif pattern.match(name):
            players.append(Human(i, name, ifunc))   # Add extra arguments extracted from `args`
            ai_only = False
        else:
            players.append(AI(i, name, discord))    # Add extra arguments extracted from `args`
    while len(players) < args.players:
        players.append(Human(len(players)))         # Add extra arguments extracted from `args`
        ai_only = False

    origin_stdout = sys.stdout
    if args.silent:
        if not ai_only:
            output = StringIO("Game cannot be silent since humans are playing")
            tmp = output.getvalue()
            await Player.print(output)
            raise Exception(tmp)
        if discord:
            Player.ofunc = None
        else:
            sys.stdout = open(os.devnull, "w")

    players, winner, errors = await game(players, not args.nodebug) # Add extra arguments extracted from `args`

    if args.silent:
        sys.stdout = origin_stdout
        Player.ofunc = ofunc
    else:
        # print whatever you want when not silent, often the final board
        ...
    ... # another place to display things

    return players, winner, errors  # this should not be messed with because that's how the discord bot works

if __name__ == "__main__":
    asyncio.run(main())

