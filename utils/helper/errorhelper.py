from utils.imports import *
from utils.secrets import ERROREMOJI, SUPPORT_SERVER

# never change those values
MAX_ERROR_FIELD_LENGTH = 1000

INITIAL_INTERACTION_RESPONSE_DEADLINE_SECONDS = 3.0
FOLLOWUP_INTERACTION_TTL_SECONDS = 15 * 60.0


ERROR_MAP: dict[type[Exception], tuple[str, str]] = {
    commands.MissingPermissions: ("Missing Permissions", "You lack the required permissions to use this command."),
    commands.BotMissingPermissions: ("Bot Missing Permissions", "I lack the required permissions to execute this command."),
    commands.MissingRole: ("Missing Role", "You need a specific role to use this command."),
    commands.MissingAnyRole: ("Missing Role", "You need at least one of the required roles to use this command."),
    commands.BotMissingAnyRole: ("Bot Missing Role", "I need at least one of the required roles to execute this command."),
    commands.NotOwner: ("Missing Permissions", "Only the bot owner can use this command."),
    commands.DisabledCommand: ("Command Disabled", "This command is currently disabled."),
    commands.CommandOnCooldown: ("Cooldown", "This command is on cooldown."),
    commands.MaxConcurrencyReached: ("Command Busy", "This command is already running too many times. Try again shortly."),
    commands.TooManyArguments: ("Too Many Arguments", "You provided too many arguments."),
    commands.MissingRequiredArgument: ("Missing Argument", "You are missing a required argument."),
    commands.BadArgument: ("Invalid Argument", "One of the provided arguments is invalid."),
    commands.BadUnionArgument: ("Invalid Argument", "I could not convert one of the provided arguments."),
    commands.BadLiteralArgument: ("Invalid Argument", "One of the values provided is not allowed."),
    commands.BadBoolArgument: ("Invalid Argument", "That is not a valid true or false value."),
    commands.ArgumentParsingError: ("Invalid Argument", "I could not parse the command arguments."),
    commands.UnexpectedQuoteError: ("Invalid Argument", "There is an unexpected quote in your command."),
    commands.InvalidEndOfQuotedStringError: ("Invalid Argument", "Quoted text is malformed."),
    commands.ExpectedClosingQuoteError: ("Invalid Argument", "A quoted string is missing a closing quote."),
    commands.ConversionError: ("Conversion Error", "I failed to convert one of the arguments."),
    commands.CheckAnyFailure: ("Access Denied", "You do not meet the requirements to use this command."),
    commands.CheckFailure: ("Access Denied", "You are not allowed to use this command."),
    commands.PrivateMessageOnly: ("DM Only", "This command can only be used in direct messages."),
    commands.NoPrivateMessage: ("No DM", "This command cannot be used in direct messages."),
    commands.NSFWChannelRequired: ("NSFW Channel Required", "You can only use this command in an NSFW channel."),
    commands.MessageNotFound: ("Not Found", "The message could not be found."),
    commands.MemberNotFound: ("Not Found", "The member could not be found."),
    commands.UserNotFound: ("Not Found", "The user could not be found."),
    commands.ChannelNotFound: ("Not Found", "The channel could not be found."),
    commands.ChannelNotReadable: ("Access Denied", "I cannot read messages in this channel."),
    commands.RoleNotFound: ("Not Found", "The role could not be found."),
    commands.EmojiNotFound: ("Not Found", "I could not find the emoji."),
    commands.PartialEmojiConversionFailure: ("Invalid Emoji", "This is not a valid emoji."),
    commands.GuildNotFound: ("Not Found", "The server could not be found."),
    commands.ThreadNotFound: ("Not Found", "The thread could not be found."),
    commands.BadInviteArgument: ("Invalid Invite", "That invite is invalid or could not be parsed."),
}

DISCORD_API_ERRORS: dict[type[Exception], tuple[str, str]] = {
    discord.Forbidden: ("Access Denied", "I do not have permission to do that."),
    discord.NotFound: ("Not Found", "The requested resource was not found."),
    discord.InteractionResponded: ("Interaction Already Replied", "This interaction has already been responded to."),
    discord.HTTPException: ("API Error", "Discord returned an API error."),
    discord.ClientException: ("Client Error", "A Discord client error occurred."),
    discord.InvalidData: ("Invalid Data", "Discord returned invalid data."),
    discord.LoginFailure: ("Login Failed", "The bot could not log in."),
    discord.GatewayNotFound: ("Gateway Error", "Discord gateway could not be found."),
    discord.ConnectionClosed: ("Connection Closed", "The connection to Discord was closed unexpectedly."),
}


def cooldown_timestamp(seconds: float, show_absolute: bool = True) -> str:
    target_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    relative = discord.utils.format_dt(target_time, style="R")
    absolute = discord.utils.format_dt(target_time, style="F")
    return f"{relative} ({absolute})" if show_absolute else relative


def shorten_codeblock_text(text, limit: int = MAX_ERROR_FIELD_LENGTH) -> str:
    text = str(text).strip() or "Unknown error"
    text = text.replace("```", "`\u200b``")

    if len(text) <= limit:
        return text

    return text[: limit - 3] + "..."


def unwrap_error(error: Exception) -> Exception:
    if isinstance(error, commands.CommandInvokeError) and getattr(error, "original", None):
        return error.original

    if isinstance(error, discord.ApplicationCommandInvokeError) and getattr(error, "original", None):
        return error.original

    return error


def is_critical_error(error: Exception) -> bool:
    if isinstance(error, commands.CommandOnCooldown):
        return False

    if isinstance(error, tuple(ERROR_MAP.keys())):
        return False

    if isinstance(error, tuple(DISCORD_API_ERRORS.keys())):
        return False

    if isinstance(error, commands.CommandError):
        return False

    return True


def build_basic_error_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        color=discord.Color.red(),
        title=title,
        description=f"{ERROREMOJI} | {description}",
    )


def build_unexpected_error_embed(user_display: str, error: Exception) -> discord.Embed:
    embed = discord.Embed(
        color=discord.Color.red(),
        title="Command Error",
        description=(
            f"{ERROREMOJI} | An unexpected error occurred.\n"
            f"Please report this issue on [GitHub]({SUPPORT_SERVER})."
        ),
    )
    embed.set_author(name=user_display)
    embed.add_field(
        name="Error",
        value=f"```py\n{shorten_codeblock_text(error, 900)}```",
        inline=False,
    )
    return embed


def build_plain_component_error(error: Exception, *, source: str = "Unknown interaction") -> str:
    error_text = str(error).strip() or type(error).__name__
    error_text = error_text.replace("```", "`\u200b``")

    source = str(source).strip() or "Unknown interaction"
    source = source.replace("```", "`\u200b``")

    if len(source) > 400:
        source = source[:397] + "..."

    if len(error_text) > 1300:
        error_text = error_text[:1297] + "..."

    return (
        f"Something broke in **{source}**:\n"
        f"```py\n{error_text}```"
    )


def get_ctx_user(ctx) -> Optional[Union[discord.Member, discord.User]]:
    return getattr(ctx, "author", getattr(ctx, "user", None))


def interaction_age_seconds(interaction: Optional[discord.Interaction]) -> float:
    if interaction is None:
        return float("inf")

    created_at = getattr(interaction, "created_at", None)
    if created_at is None:
        return 0.0

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds())


def can_send_initial_interaction_response(interaction: Optional[discord.Interaction]) -> bool:
    return interaction_age_seconds(interaction) < INITIAL_INTERACTION_RESPONSE_DEADLINE_SECONDS


def can_send_interaction_followup(interaction: Optional[discord.Interaction]) -> bool:
    return interaction_age_seconds(interaction) < FOLLOWUP_INTERACTION_TTL_SECONDS


def resolve_known_error(error: Exception) -> Optional[tuple[str, str]]:
    if isinstance(error, commands.CommandOnCooldown):
        timestamp = cooldown_timestamp(error.retry_after)
        return "Cooldown", f"This command is on cooldown. Try again {timestamp}."

    for error_type, payload in ERROR_MAP.items():
        if isinstance(error, error_type):
            return payload

    for error_type, payload in DISCORD_API_ERRORS.items():
        if isinstance(error, error_type):
            return payload

    return None
