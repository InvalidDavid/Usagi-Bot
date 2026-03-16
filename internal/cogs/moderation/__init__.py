from .appeals import AppealCommands
from .base import ModerationBase
from .cases import CaseCommands
from .forum import ForumCommands
from .sanctions import SanctionCommands
from .setup_commands import SetupCommands


class ModCog(
    ForumCommands,
    AppealCommands,
    SetupCommands,
    CaseCommands,
    SanctionCommands,
    ModerationBase,
):
    pass


def setup(bot):
    bot.add_cog(ModCog(bot))
