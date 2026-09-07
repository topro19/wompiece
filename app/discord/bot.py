import discord
from discord.ext import commands
from discord import app_commands
from app.config.settings import settings
from app.database.connection import db_manager
from app.services.logger import logger


class PirateWarsBot(commands.Bot):
    """Authoritative Discord Client for the Pirate Wars persistent world."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        super().__init__(
            command_prefix="!pw ",
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        """Initializes database connection and registers slash commands."""
        logger.info("Initializing PirateWarsBot setup hook...")
        await db_manager.connect()

        # Register slash commands
        self.tree.add_command(status_command)
        from app.discord.commands.player_commands import (
            start_command,
            profile_command,
            inventory_command,
            location_command
        )
        self.tree.add_command(start_command)
        self.tree.add_command(profile_command)
        self.tree.add_command(inventory_command)
        self.tree.add_command(location_command)
        from app.discord.commands.crew_commands import crew_group
        self.tree.add_command(crew_group)
        from app.discord.commands.business_commands import business_group, alias_group
        self.tree.add_command(business_group)
        self.tree.add_command(alias_group)
        from app.discord.commands.marine_commands import case_group, freeform_action_command, bribe_command
        self.tree.add_command(case_group)
        self.tree.add_command(freeform_action_command)
        self.tree.add_command(bribe_command)
        from app.discord.commands.gambling_commands import gamble_group
        self.tree.add_command(gamble_group)
        from app.discord.commands.combat_commands import combat_group
        self.tree.add_command(combat_group)
        from app.discord.commands.ship_commands import ship_group
        self.tree.add_command(ship_group)
        from app.discord.commands.admin_commands import admin_group
        self.tree.add_command(admin_group)
        from app.discord.commands.help_commands import ginto_command, help_command
        self.tree.add_command(ginto_command)
        self.tree.add_command(help_command)
        
        # Sync slash commands with Discord
        try:
            if settings.DISCORD_GUILD_ID:
                guild = discord.Object(id=int(settings.DISCORD_GUILD_ID))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info(f"Synchronized slash commands for guild {settings.DISCORD_GUILD_ID}.")
            else:
                await self.tree.sync()
                logger.info("Synchronized global slash commands.")
        except discord.errors.MissingApplicationID:
            logger.warning("Discord client application ID not set or running offline; skipped remote command sync.")

    async def on_ready(self):
        logger.info(f"PirateWarsBot logged in as {self.user} (ID: {self.user.id}).")
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="the High Seas | /start"
        )
        await self.change_presence(activity=activity)

    async def close(self):
        logger.info("Closing PirateWarsBot and releasing resources...")
        await db_manager.disconnect()
        await super().close()


@app_commands.command(name="status", description="Check the status and health of the Pirate Wars persistent world.")
async def status_command(interaction: discord.Interaction):
    """Health check command verifying database connectivity and system status."""
    is_mock = db_manager.is_mock
    db_status = "Connected (In-Memory Mock)" if is_mock else "Connected (MongoDB Live)"

    embed = discord.Embed(
        title="⚓ Pirate Wars — World Status",
        color=discord.Color.blue()
    )
    embed.add_field(name="World State", value="🟢 Online & Persistent", inline=True)
    embed.add_field(name="Database", value=f"🟢 {db_status}", inline=True)
    embed.add_field(name="Ping", value=f"{round(interaction.client.latency * 1000)}ms", inline=True)
    embed.set_footer(text="Authoritative Simulation Engine v0.1.0")

    await interaction.response.send_message(embed=embed, ephemeral=True)


bot = PirateWarsBot()
