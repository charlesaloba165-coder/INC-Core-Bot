"""
INC-Core.py
Single-file starter Discord bot for the Incorporated server.

Requires:
    pip install -U discord.py

Before running:
    1. Create a Discord application/bot in the Discord Developer Portal.
    2. Put the bot token in the DISCORD_TOKEN environment variable.
    3. Invite the bot with the scopes: bot + applications.commands
    4. Give it only the permissions it actually needs.
    5. Enable Server Members Intent in the Developer Portal if you want join statistics.

This starter keeps Operations / Raid / Nuke functionality as authorized,
non-destructive simulations only. It does NOT perform real raids, nukes,
mass deletion, mass bans, or other disruptive actions.
"""

import os
import sqlite3
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks


# -----------------------------
# CONFIGURATION
# -----------------------------

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE = "inc_core.db"

intents = discord.Intents.default()
intents.members = False
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)


# -----------------------------
# DATABASE
# -----------------------------

db = sqlite3.connect(DATABASE)
db.row_factory = sqlite3.Row


def init_db():
    db.executescript("""
    CREATE TABLE IF NOT EXISTS members (
        guild_id INTEGER,
        user_id INTEGER,
        joined_at TEXT,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        creator_id INTEGER,
        department TEXT,
        problem TEXT,
        decision TEXT,
        status TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS bugs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        reporter_id INTEGER,
        title TEXT,
        details TEXT,
        status TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        tester_id INTEGER,
        system TEXT,
        result TEXT,
        status TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        name TEXT,
        status TEXT,
        owner_id INTEGER,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        channel_id INTEGER,
        message TEXT,
        send_at TEXT
    );

    CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        creator_id INTEGER,
        name TEXT,
        objective TEXT,
        status TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        channel_id INTEGER,
        status TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS authorized_admins (
        guild_id INTEGER,
        user_id INTEGER,
        authorized_by INTEGER,
        authorized_at TEXT,
        PRIMARY KEY (guild_id, user_id)
    );
    """)
    db.commit()


# -----------------------------
# HELPERS
# -----------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def staff_check(interaction: discord.Interaction) -> bool:
    perms = interaction.user.guild_permissions
    if perms.manage_guild or perms.manage_channels or perms.administrator:
        return True

    row = db.execute(
        "SELECT 1 FROM authorized_admins WHERE guild_id = ? AND user_id = ?",
        (interaction.guild.id, interaction.user.id)
    ).fetchone()
    return row is not None


def staff_only():
    async def predicate(interaction: discord.Interaction):
        return staff_check(interaction)
    return app_commands.check(predicate)


def administrator_only():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


async def send_embed(interaction, title, description, ephemeral=False):
    embed = discord.Embed(
        title=title,
        description=description,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="INC-Core • Incorporated")
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral)


# -----------------------------
# EVENTS
# -----------------------------

@bot.event
async def on_ready():
    init_db()
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="Incorporated management")
    )

    # Sync slash commands globally.
    try:
        synced = await bot.tree.sync()
        print(f"INC-Core online as {bot.user}. Synced {len(synced)} commands.")
    except Exception as exc:
        print(f"Command sync failed: {exc}")

    if not schedule_loop.is_running():
        schedule_loop.start()


@bot.event
async def on_member_join(member: discord.Member):
    db.execute(
        "INSERT OR REPLACE INTO members VALUES (?, ?, ?)",
        (member.guild.id, member.id, now_iso())
    )
    db.commit()


@bot.event
async def on_member_remove(member: discord.Member):
    # We keep the original join record so historical membership data remains.
    pass


# -----------------------------
# COMPANY / ROSTER
# -----------------------------

@bot.tree.command(name="profile", description="Show a member's Incorporated profile.")
@app_commands.describe(member="The member to view.")
async def profile(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    roles = [r.name for r in member.roles if r.name != "@everyone"]

    await send_embed(
        interaction,
        f"🏢 {member.display_name}",
        f"**User:** {member.mention}\n"
        f"**Joined:** {discord.utils.format_dt(member.joined_at, 'D') if member.joined_at else 'Unknown'}\n"
        f"**Roles:** {', '.join(roles) if roles else 'Member'}"
    )


@bot.tree.command(name="roster", description="Show Incorporated's current member roster.")
async def roster(interaction: discord.Interaction):
    members = [m for m in interaction.guild.members if not m.bot]
    lines = []

    for member in members[:30]:
        role = next(
            (r.name for r in reversed(member.roles) if r.name != "@everyone"),
            "Member"
        )
        lines.append(f"• {member.display_name} — **{role}**")

    extra = "" if len(members) <= 30 else f"\n…and {len(members) - 30} more."
    await send_embed(
        interaction,
        "📋 Incorporated Roster",
        "\n".join(lines) + extra if lines else "No members found."
    )


@bot.tree.command(name="promote", description="Give a member a role.")
@app_commands.describe(member="Member to promote.", role="Role to give.")
@staff_only()
async def promote(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if role >= interaction.guild.me.top_role:
        return await send_embed(interaction, "❌ Cannot promote", "That role is above my highest role.", True)

    await member.add_roles(role, reason=f"INC-Core promotion by {interaction.user}")
    await send_embed(interaction, "📈 Promotion", f"{member.mention} received **{role.name}**.")


@bot.tree.command(name="demote", description="Remove a role from a member.")
@app_commands.describe(member="Member to demote.", role="Role to remove.")
@staff_only()
async def demote(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role, reason=f"INC-Core demotion by {interaction.user}")
    await send_embed(interaction, "📉 Demotion", f"Removed **{role.name}** from {member.mention}.")


@bot.tree.command(name="departments", description="List Incorporated departments.")
async def departments(interaction: discord.Interaction):
    await send_embed(
        interaction,
        "🏢 Incorporated Departments",
        "⚙️ Configuration\n"
        "🤖 Bot Division\n"
        "🧪 Testing\n"
        "⚖️ Cases / Judge\n"
        "📊 Statistics\n"
        "📢 Notifications\n"
        "🛡️ Security\n"
        "🎫 Support\n"
        "☢️ Operations — authorized simulations\n"
        "⚔️ Rebellion — roleplay/simulation"
    )


# -----------------------------
# CONFIGURATION
# -----------------------------

@bot.tree.command(name="authorize-admin", description="Allow a member to use INC-Core staff commands.")
@app_commands.describe(member="The member to authorize as an INC-Core administrator.")
@administrator_only()
async def authorize_admin(interaction: discord.Interaction, member: discord.Member):
    db.execute(
        "INSERT OR REPLACE INTO authorized_admins (guild_id, user_id, authorized_by, authorized_at) "
        "VALUES (?, ?, ?, ?)",
        (interaction.guild.id, member.id, interaction.user.id, now_iso())
    )
    db.commit()

    await send_embed(
        interaction,
        "✅ INC-Core Admin Authorized",
        f"{member.mention} can now use INC-Core staff commands in this server."
    )


@bot.tree.command(name="revoke-admin", description="Remove a member's INC-Core staff access.")
@app_commands.describe(member="The member to remove from the INC-Core administrator list.")
@administrator_only()
async def revoke_admin(interaction: discord.Interaction, member: discord.Member):
    cursor = db.execute(
        "DELETE FROM authorized_admins WHERE guild_id = ? AND user_id = ?",
        (interaction.guild.id, member.id)
    )
    db.commit()

    if cursor.rowcount == 0:
        return await send_embed(
            interaction,
            "ℹ️ No Delegated Access",
            f"{member.mention} was not on the INC-Core administrator list.",
            True
        )

    await send_embed(
        interaction,
        "✅ INC-Core Admin Access Revoked",
        f"{member.mention} can no longer use INC-Core staff commands through delegated access."
    )


@bot.tree.command(name="check-perms", description="Check the bot's permissions in this server.")
async def check_perms(interaction: discord.Interaction):
    me = interaction.guild.me
    perms = me.guild_permissions

    important = {
        "View Channels": perms.view_channel,
        "Send Messages": perms.send_messages,
        "Embed Links": perms.embed_links,
        "Manage Messages": perms.manage_messages,
        "Manage Channels": perms.manage_channels,
        "Manage Roles": perms.manage_roles,
        "Manage Guild": perms.manage_guild,
        "Administrator": perms.administrator,
    }

    text = "\n".join(
        f"{'✅' if value else '❌'} {name}" for name, value in important.items()
    )
    await send_embed(interaction, "⚙️ INC-Core Permission Check", text)


@bot.tree.command(name="config", description="Show basic server configuration information.")
@staff_only()
async def config(interaction: discord.Interaction):
    guild = interaction.guild
    await send_embed(
        interaction,
        "⚙️ Server Configuration",
        f"**Server:** {guild.name}\n"
        f"**Members:** {guild.member_count}\n"
        f"**Channels:** {len(guild.channels)}\n"
        f"**Roles:** {len(guild.roles)}\n"
        f"**Verification:** {str(guild.verification_level).title()}"
    )


@bot.tree.command(name="setup", description="Show a recommended Incorporated setup checklist.")
@staff_only()
async def setup(interaction: discord.Interaction):
    await send_embed(
        interaction,
        "🛠️ INC-Core Setup Checklist",
        "☐ Create Incorporated categories\n"
        "☐ Create staff/member roles\n"
        "☐ Configure channel permissions\n"
        "☐ Configure moderation/AutoMod\n"
        "☐ Configure support tickets\n"
        "☐ Create logs channel\n"
        "☐ Test every system\n"
        "☐ Review permissions before release"
    )


# -----------------------------
# TESTING / BUGS
# -----------------------------

@bot.tree.command(name="test", description="Create a system test record.")
@app_commands.describe(system="System being tested.", result="What happened.", status="Passed or Failed.")
async def test(
    interaction: discord.Interaction,
    system: str,
    result: str,
    status: str
):
    db.execute(
        "INSERT INTO tests (guild_id, tester_id, system, result, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (interaction.guild.id, interaction.user.id, system, result, status, now_iso())
    )
    db.commit()

    await send_embed(
        interaction,
        "🧪 Test Recorded",
        f"**System:** {system}\n**Result:** {result}\n**Status:** {status}"
    )


@bot.tree.command(name="bug", description="Report a configuration or bot bug.")
@app_commands.describe(title="Short bug title.", details="Explain the problem.")
async def bug(interaction: discord.Interaction, title: str, details: str):
    db.execute(
        "INSERT INTO bugs (guild_id, reporter_id, title, details, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (interaction.guild.id, interaction.user.id, title, details, "Open", now_iso())
    )
    db.commit()

    await send_embed(
        interaction,
        "🐛 Bug Reported",
        f"**Title:** {title}\n**Details:** {details}\n**Status:** Open"
    )


# -----------------------------
# JUDGE / CASES
# -----------------------------

@bot.tree.command(name="case-create", description="Create an Incorporated case.")
@app_commands.describe(department="Department handling the case.", problem="Problem to judge.")
async def case_create(interaction: discord.Interaction, department: str, problem: str):
    cursor = db.execute(
        "INSERT INTO cases (guild_id, creator_id, department, problem, decision, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (interaction.guild.id, interaction.user.id, department, problem, "Awaiting decision", "Open", now_iso())
    )
    db.commit()

    await send_embed(
        interaction,
        f"⚖️ CASE #{cursor.lastrowid}",
        f"**Problem:** {problem}\n"
        f"**Judge/Department:** {department}\n"
        f"**Decision:** Awaiting decision\n"
        f"**Status:** Open"
    )


@bot.tree.command(name="case-close", description="Close a case with a decision.")
@app_commands.describe(case_id="Case number.", decision="Final decision.")
@staff_only()
async def case_close(interaction: discord.Interaction, case_id: int, decision: str):
    row = db.execute(
        "SELECT * FROM cases WHERE id = ? AND guild_id = ?",
        (case_id, interaction.guild.id)
    ).fetchone()

    if not row:
        return await send_embed(interaction, "❌ Case not found", "That case does not exist.", True)

    db.execute(
        "UPDATE cases SET decision = ?, status = 'Closed' WHERE id = ?",
        (decision, case_id)
    )
    db.commit()

    await send_embed(
        interaction,
        f"⚖️ CASE #{case_id} CLOSED",
        f"**Problem:** {row['problem']}\n"
        f"**Decision:** {decision}\n"
        f"**Status:** Closed"
    )


# -----------------------------
# PROJECTS
# -----------------------------

@bot.tree.command(name="project-create", description="Create a company project.")
@app_commands.describe(name="Project name.", status="Project status.")
@staff_only()
async def project_create(interaction: discord.Interaction, name: str, status: str = "Planning"):
    cursor = db.execute(
        "INSERT INTO projects (guild_id, name, status, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (interaction.guild.id, name, status, interaction.user.id, now_iso())
    )
    db.commit()

    await send_embed(
        interaction,
        "📋 Project Created",
        f"**ID:** {cursor.lastrowid}\n**Name:** {name}\n**Status:** {status}"
    )


# -----------------------------
# STATS
# -----------------------------

@bot.tree.command(name="stats", description="Show server and join statistics.")
async def stats(interaction: discord.Interaction):
    guild = interaction.guild
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(days=1)
    week_start = now - timedelta(days=7)

    rows = db.execute(
        "SELECT joined_at FROM members WHERE guild_id = ?",
        (guild.id,)
    ).fetchall()

    daily = 0
    weekly = 0

    for row in rows:
        try:
            joined = datetime.fromisoformat(row["joined_at"])
            if joined.tzinfo is None:
                joined = joined.replace(tzinfo=timezone.utc)
            if joined >= day_start:
                daily += 1
            if joined >= week_start:
                weekly += 1
        except ValueError:
            continue

    await send_embed(
        interaction,
        "📊 INCORPORATED STATISTICS",
        f"👥 **Current members:** {guild.member_count}\n"
        f"👤 **Joins (24h):** {daily}\n"
        f"📅 **Joins (7d):** {weekly}\n"
        f"📁 **Channels:** {len(guild.channels)}\n"
        f"🎭 **Roles:** {len(guild.roles)}"
    )


@bot.tree.command(name="leaderboard", description="Show contribution placeholders.")
async def leaderboard(interaction: discord.Interaction):
    await send_embed(
        interaction,
        "🏆 Incorporated Leaderboard",
        "Contribution scoring is ready to be expanded.\n"
        "Suggested points: completed projects, resolved cases, approved suggestions, and successful tests."
    )


# -----------------------------
# NOTIFICATIONS
# -----------------------------

@bot.tree.command(name="announce", description="Send an announcement to the current channel.")
@app_commands.describe(message="Announcement text.")
@staff_only()
async def announce(interaction: discord.Interaction, message: str):
    await send_embed(interaction, "📢 INCORPORATED ANNOUNCEMENT", message)


@bot.tree.command(name="schedule", description="Schedule a message for a future time.")
@app_commands.describe(minutes="Minutes from now.", message="Message to send.")
@staff_only()
async def schedule(interaction: discord.Interaction, minutes: int, message: str):
    if minutes < 1:
        return await send_embed(interaction, "❌ Invalid time", "Minutes must be at least 1.", True)

    send_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    db.execute(
        "INSERT INTO schedules (guild_id, channel_id, message, send_at) VALUES (?, ?, ?, ?)",
        (interaction.guild.id, interaction.channel.id, message, send_at.isoformat())
    )
    db.commit()

    await send_embed(
        interaction,
        "📢 Scheduled",
        f"Message scheduled for {discord.utils.format_dt(send_at, 'F')}."
    )


@tasks.loop(seconds=30)
async def schedule_loop():
    now = datetime.now(timezone.utc)

    rows = db.execute(
        "SELECT * FROM schedules WHERE send_at <= ?",
        (now.isoformat(),)
    ).fetchall()

    for row in rows:
        channel = bot.get_channel(row["channel_id"])
        if channel:
            try:
                await channel.send(row["message"])
            except discord.HTTPException:
                pass

        db.execute("DELETE FROM schedules WHERE id = ?", (row["id"],))

    db.commit()


# -----------------------------
# SECURITY
# -----------------------------

@bot.tree.command(name="security", description="Show basic security recommendations.")
@staff_only()
async def security(interaction: discord.Interaction):
    await send_embed(
        interaction,
        "🛡️ INC-Core Security",
        "✅ Keep Administrator limited\n"
        "✅ Use least-privilege bot permissions\n"
        "✅ Keep staff channels private\n"
        "✅ Use Discord AutoMod\n"
        "✅ Review audit logs\n"
        "✅ Never share bot tokens\n"
        "✅ Test permission changes before release"
    )


@bot.tree.command(name="audit", description="Show recent audit-log actions.")
@staff_only()
async def audit(interaction: discord.Interaction):
    entries = []

    try:
        async for entry in interaction.guild.audit_logs(limit=10):
            entries.append(
                f"• **{entry.action.name}** — {entry.user} "
                f"({discord.utils.format_dt(entry.created_at, 'R')})"
            )
    except discord.Forbidden:
        return await send_embed(
            interaction,
            "🛡️ Audit Logs",
            "I don't have permission to view the audit log.",
            True
        )

    await send_embed(
        interaction,
        "🛡️ Recent Audit Activity",
        "\n".join(entries) if entries else "No recent entries."
    )


# -----------------------------
# SUPPORT / TICKETS
# -----------------------------

@bot.tree.command(name="ticket", description="Create a private support ticket.")
async def ticket(interaction: discord.Interaction):
    guild = interaction.guild
    category = discord.utils.get(guild.categories, name="Support")

    if category is None:
        category = await guild.create_category("Support")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            read_message_history=True
        ),
    }

    channel = await guild.create_text_channel(
        f"ticket-{interaction.user.name}".lower()[:90],
        category=category,
        overwrites=overwrites,
        reason="INC-Core support ticket"
    )

    db.execute(
        "INSERT INTO tickets (guild_id, user_id, channel_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (guild.id, interaction.user.id, channel.id, "Open", now_iso())
    )
    db.commit()

    await channel.send(
        f"🎫 **INCORPORATED SUPPORT**\n"
        f"Welcome {interaction.user.mention}.\n"
        f"Please explain your issue. A staff member can claim this ticket."
    )

    await send_embed(interaction, "🎫 Ticket Created", channel.mention)


@bot.tree.command(name="claim", description="Claim the current support ticket.")
@staff_only()
async def claim(interaction: discord.Interaction):
    await send_embed(
        interaction,
        "🎫 Ticket Claimed",
        f"{interaction.user.mention} is now handling this ticket."
    )


@bot.tree.command(name="close", description="Close the current support ticket.")
@staff_only()
async def close(interaction: discord.Interaction):
    db.execute(
        "UPDATE tickets SET status = 'Closed' WHERE channel_id = ?",
        (interaction.channel.id,)
    )
    db.commit()

    await send_embed(interaction, "🔒 Ticket Closed", "This ticket will be archived shortly.")

    try:
        await interaction.channel.edit(archived=True)
    except (discord.HTTPException, TypeError):
        pass


# -----------------------------
# OPERATIONS / REBELLION
# SAFE SIMULATION ONLY
# -----------------------------

@bot.tree.command(name="operation", description="Create an authorized fictional/simulation operation.")
@app_commands.describe(name="Operation name.", objective="Simulation objective.")
async def operation(interaction: discord.Interaction, name: str, objective: str):
    cursor = db.execute(
        "INSERT INTO operations (guild_id, creator_id, name, objective, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (interaction.guild.id, interaction.user.id, name, objective, "Simulation", now_iso())
    )
    db.commit()

    await send_embed(
        interaction,
        f"☢️ OPERATION #{cursor.lastrowid}",
        f"**Name:** {name}\n"
        f"**Objective:** {objective}\n"
        f"**Status:** Authorized Simulation\n\n"
        "This system is for roleplay/training on servers where you have permission."
    )


@bot.tree.command(name="mission", description="Create a fictional mission objective.")
@app_commands.describe(name="Mission name.", objective="Mission objective.")
async def mission(interaction: discord.Interaction, name: str, objective: str):
    await send_embed(
        interaction,
        f"⚔️ Mission: {name}",
        f"**Objective:** {objective}\n"
        "**Mode:** Fictional / authorized simulation"
    )


@bot.tree.command(name="faction", description="Display a fictional faction.")
@app_commands.describe(name="Faction name.", description="Faction description.")
async def faction(interaction: discord.Interaction, name: str, description: str):
    await send_embed(
        interaction,
        f"🏴 Faction: {name}",
        description + "\n\n**Mode:** Roleplay / simulation"
    )


@bot.tree.command(name="simulation", description="Start a safe raid/nuke-themed defense simulation.")
@app_commands.describe(scenario="Name of the fictional scenario.")
async def simulation(interaction: discord.Interaction, scenario: str):
    await send_embed(
        interaction,
        "🧪 Simulation Started",
        f"**Scenario:** {scenario}\n\n"
        "This is a non-destructive training simulation. "
        "No real raids, nukes, mass deletions, mass bans, or disruption are performed."
    )


@bot.tree.command(name="operation-record", description="Record the result of a simulation.")
@app_commands.describe(result="Describe the simulation result.")
async def operation_record(interaction: discord.Interaction, result: str):
    await send_embed(
        interaction,
        "📋 Operation Record",
        f"**Recorded by:** {interaction.user.mention}\n"
        f"**Result:** {result}"
    )


# -----------------------------
# ERROR HANDLING
# -----------------------------

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        if interaction.response.is_done():
            await interaction.followup.send(
                "❌ You need appropriate staff permissions for that command.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ You need appropriate staff permissions for that command.",
                ephemeral=True
            )
        return

    print(f"Command error: {repr(error)}")

    if interaction.response.is_done():
        await interaction.followup.send(
            "❌ Something went wrong while running that command.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ Something went wrong while running that command.",
            ephemeral=True
        )


# -----------------------------
# START
# -----------------------------

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Set the environment variable before running INC-Core.py."
        )

    init_db()
    bot.run(TOKEN)