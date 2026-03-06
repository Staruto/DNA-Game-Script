from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class DungeonProfile:
    key: str
    display_name: str
    use_skill_logic: bool = True
    use_challenge_again: bool = True
    use_start_click: bool = True
    skill_key: str = "q"
    challenge_template: str = "challenge_again.png"
    start_template: str = "start_button.png"
    name_template: Optional[str] = None


DUNGEON_PROFILES: Dict[str, DungeonProfile] = {
    "expulsion": DungeonProfile(
        key="expulsion",
        display_name="Expulsion",
        name_template="dungeon_name_expulsion.png",
    ),
    "exploration": DungeonProfile(
        key="exploration",
        display_name="Exploration",
        name_template="dungeon_name_exploration.png",
    ),
    "defence": DungeonProfile(
        key="defence",
        display_name="Defence",
        name_template="dungeon_name_defence.png",
    ),
}
