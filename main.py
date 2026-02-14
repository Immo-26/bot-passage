import os, json, re, discord
from pathlib import Path
from discord.ext import commands
from discord.ui import View, Button, Select
from dotenv import load_dotenv

load_dotenv()

# =========================
# Config / ENV
# =========================
def env_int(name: str, fallback: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return fallback
    try:
        return int(v)
    except ValueError:
        raise RuntimeError(f"{name} doit être un nombre (int). Actuel: {v}")

GUILD_ID = env_int("GUILD_ID", 1393982298654900345)
DEMANDS_CHANNEL_ID = env_int("DEMANDS_CHANNEL_ID", 1393984437078720603)
OWNER_ID = env_int("OWNER_ID", 342021125800198144)
TICKET_PREFIX = os.getenv("TICKET_PREFIX", "ticket-passage-donjon")
NEW_CATEGORY_ID = env_int("NEW_CATEGORY_ID", 1426346995466895480)
FEEDBACK_CHANNEL_ID = env_int("FEEDBACK_CHANNEL_ID", 1394291299066056745)
SCREEN_CHANNEL_ID = env_int("SCREEN_CHANNEL_ID", 1427079620246638732)
WAKEUP_CHANNEL_ID = env_int("WAKEUP_CHANNEL_ID", 1426347294525096119)

BASE_DIR = Path(__file__).resolve().parent
PASSEURS_JSON_PATH = Path(os.getenv("PASSEURS_JSON_PATH", str(BASE_DIR / "passeurs.json")))

# =========================
# Bot setup
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_messages = {}
dashboard_message = None

# =========================
# Data
# =========================
DONJON_SUCCES = {
    "Obsidiantre": [("Premier","obsi_premier"),("Statue","obsi_statue"),("Duo","obsi_duo")],
    "Tengu": [("Premier","tengu_premier"),("Statue","tengu_statue"),("Duo","tengu_duo")],
    "Korriandre": [("Mystique","korriandre_mystique"),("Zombie","korriandre_zombie"),("Duo","korriandre_duo")],
    "Kolosso": [("Dernier","kolosso_dernier"),("Premier","kolosso_premier"),("Duo","kolosso_duo")],
    "Sakaii": [("Versatile","sakaii_versatile"),("Blitzkrieg","sakaii_blitzkrieg"),("Duo","sakaii_duo")],
    "Glours": [("Premier","glours_premier"),("Collant","glours_collant"),("Duo","glours_duo")],
    "Nagate": [("Dernier","nagate_dernier"),("Hardi","nagate_hardi"),("Duo","nagate_duo")],
    "Tanu": [("Nomade","tanu_nomade"),("Blitzkrieg","tanu_blitz"),("Duo","tanu_duo")],
    "Founo": [("Dernier","founo_dernier"),("Anachorète","founo_anachorete"),("Duo","founo_duo")],
    "Dojo du vent": [("Premier","dojo_premier"),("Pusillanime","dojo_pusillamine"),("Duo","dojo_duo")],
    "Damadrya": [("Anachorète","damadrya_anachorete"),("Premier","damadrya_premier"),("Duo","damadrya_duo")],
    "Katamashii": [("Main propres","katamashii_main"),("Hardi","katamashii_hardi"),("Duo","katamashii_duo")],
    "Kralamour": [("Nomade","kralamour_nomade"),("Blitzkrieg","kralamour_blitzkrieg"),("Duo","kralamour_duo")],
    "Kimbo": [("Statue","kimbo_statue"),("Premier","kimbo_premier"),("Duo","kimbo_duo")]
}

DISABLED_SUCCES = {
    "Sakaii": ["sakaii_blitzkrieg"],
    "Glours": ["glours_collant"],
    "Tanu": ["tanu_blitz"],
    "Dojo du vent": ["dojo_premier","dojo_duo"],
    "Katamashii": ["katamashii_hardi","katamashii_duo"]
}

MENTION_ID_RE = re.compile(r"<@!?(\d+)>")

# =========================
# Helpers
# =========================
def load_passeurs_map():
    try:
        if not PASSEURS_JSON_PATH.exists():
            return {}
        with open(PASSEURS_JSON_PATH, "r", encoding="utf-8") as f:
            return {str(k): int(v) for k,v in json.load(f).items()}
    except:
        return {}

def get_passeur_for_donjon(d):
    return load_passeurs_map().get(d, OWNER_ID)

def next_ticket_name(cat, prefix):
    n = []
    if cat:
        for c in cat.text_channels:
            m = re.match(rf"^{re.escape(prefix)}-(\d{{3}})$", c.name)
            if m:
                n.append(int(m.group(1)))
    return f"{prefix}-{(max(n)+1) if n else 1:03d}"

def make_summary_embed(u, a, d, s, disp):
    e = discord.Embed(title="Récapitulatif de la réservation", color=0x2F3136)
    e.add_field(name="Client", value=u.mention, inline=False)
    e.add_field(name="Zone", value=a, inline=False)
    e.add_field(name="Donjon", value=d, inline=False)
    e.add_field(name="Succès demandés", value=s, inline=False)
    e.add_field(name="Disponibilité", value=disp, inline=False)
    e.set_footer(text="Vérifie les informations puis clique sur « Valider la demande »."); 
    return e

def labels_from_success_codes(d, sel):
    labels = []
    for cid in sel:
        for lbl, cid2 in DONJON_SUCCES.get(d, []):
            if cid2 == cid:
                labels.append(lbl)
    return ", ".join(labels) if labels else "Aucun"

def extract_first_id_from_mention(text: str) -> int | None:
    if not text:
        return None
    m = MENTION_ID_RE.search(text)
    return int(m.group(1)) if m else None

def extract_all_ids_from_text(text: str) -> list[int]:
    return [int(x) for x in MENTION_ID_RE.findall(text or "")]

def read_field(embed: discord.Embed, field_name: str) -> str | None:
    for f in embed.fields:
        if f.name == field_name:
            return f.value
    return None

def update_or_add_comment_field(embed: discord.Embed, new_value: str) -> discord.Embed:
    for idx, f in enumerate(embed.fields):
        if f.name == "💬 Commentaires":
            embed.set_field_at(idx, name="💬 Commentaires", value=new_value, inline=False)
            return embed
    embed.add_field(name="💬 Commentaires", value=new_value, inline=False)
    return embed

async def find_recap_message(channel: discord.TextChannel) -> discord.Message | None:
    async for m in channel.history(limit=50, oldest_first=True):
        if m.author == bot.user and m.embeds:
            emb = m.embeds[0]
            if emb.title and "Récapitulatif de la réservation" in emb.title:
                return m
    return None

async def find_latest_feedback_message_for_author(guild: discord.Guild, author_id: int) -> discord.Message | None:
    fb = guild.get_channel(FEEDBACK_CHANNEL_ID)
    if not isinstance(fb, discord.TextChannel):
        return None
    async for m in fb.history(limit=80):
        if m.author != bot.user or not m.embeds:
            continue
        e = m.embeds[0]
        if not e.title or "Passage effectué" not in e.title:
            continue
        par_val = read_field(e, "Par") or ""
        par_id = extract_first_id_from_mention(par_val)
        if par_id == author_id:
            return m
    return None

# =========================
# UI: Select / Views
# =========================
class DonjonSelect(Select):
    def __init__(self, l, a):
        super().__init__(
            placeholder="Choisissez un donjon...",
            options=[discord.SelectOption(label=x, value=x) for x in l]
        )
        self.a = a

    async def callback(self, i: discord.Interaction):
        c = self.values[0]
        v = MultiStepView(self.a, c)
        await i.response.send_message(
            embed=discord.Embed(
                title=f"{self.a} — {c}",
                description="Commencez par choisir si vous voulez faire les succès.",
                color=0x2F3136
            ),
            view=v,
            ephemeral=True
        )
        user_messages.setdefault(i.user.id, []).append(await i.original_response())

class MultiStepView(View):
    def __init__(self, a, d):
        super().__init__(timeout=900)
        self.a = a
        self.d = d
        self.s = []
        self.dispo = None
        self.stage = "ask"

    @discord.ui.button(label="Succès : Oui", style=discord.ButtonStyle.secondary, custom_id="y")
    async def y(self, i: discord.Interaction, b: discord.ui.Button):
        await self.succes(i, True)

    @discord.ui.button(label="Succès : Non", style=discord.ButtonStyle.secondary, custom_id="n")
    async def n(self, i: discord.Interaction, b: discord.ui.Button):
        await self.succes(i, False)

    async def succes(self, i: discord.Interaction, yes: bool):
        self.clear_items()
        if yes:
            for l, c in DONJON_SUCCES.get(self.d, []):
                disabled = c in DISABLED_SUCCES.get(self.d, [])
                self.add_item(Button(
                    label=l,
                    style=(discord.ButtonStyle.danger if disabled else discord.ButtonStyle.secondary),
                    custom_id=f"s_{c}",
                    disabled=disabled
                ))
            self.stage = "sel"
        else:
            self.stage = "disp"

        self.add_item(Button(label="Suivant ➜", style=discord.ButtonStyle.danger, custom_id="next"))
        await i.response.edit_message(view=self)

    async def interaction_check(self, i: discord.Interaction):
        cid = i.data.get("custom_id")

        if self.stage == "sel" and cid.startswith("s_"):
            c = cid[2:]
            if c in self.s:
                self.s.remove(c)
            else:
                self.s.append(c)
            for x in self.children:
                if hasattr(x, "custom_id") and x.custom_id == cid:
                    x.style = discord.ButtonStyle.success if c in self.s else discord.ButtonStyle.secondary
            await i.response.edit_message(view=self)
            return False

        if cid == "next":
            self.clear_items()
            for l, idv in [("✅ Dès que possible", "now"), ("📅 À planifier", "later")]:
                self.add_item(Button(label=l, style=discord.ButtonStyle.secondary, custom_id=idv))
            self.add_item(Button(label="Valider la demande", style=discord.ButtonStyle.danger, custom_id="confirm", disabled=True))
            self.stage = "disp"
            await i.response.edit_message(view=self)
            return False

        if self.stage == "disp" and cid in ["now", "later"]:
            self.dispo = "Passage dès que possible" if cid == "now" else "Passage à planifier"
            for x in self.children:
                if hasattr(x, "custom_id") and x.custom_id in ["now", "later"]:
                    x.style = discord.ButtonStyle.success if x.custom_id == cid else discord.ButtonStyle.secondary
                if hasattr(x, "custom_id") and x.custom_id == "confirm":
                    x.disabled = False
            await i.response.edit_message(view=self)
            return False

        if self.stage == "disp" and cid == "confirm":
            await self.create(i)
            return False

        return True

    async def create(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        g, a = i.guild, i.user
        cat = g.get_channel(NEW_CATEGORY_ID)

        pid = get_passeur_for_donjon(self.d)
        p = g.get_member(pid)

        ow = {
            g.default_role: discord.PermissionOverwrite(view_channel=False),
            g.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            a: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for x in [p, g.get_member(OWNER_ID)]:
            if x:
                ow[x] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ch = await g.create_text_channel(next_ticket_name(cat, TICKET_PREFIX), category=cat, overwrites=ow)

        try:
            await ch.edit(topic=self.dispo or "Non précisé")
        except:
            pass

        s = labels_from_success_codes(self.d, self.s)

        # Message récapitulatif (source de vérité)
        await ch.send(
            f"{a.mention} • <@{pid}>",
            embed=make_summary_embed(a, self.a, self.d, s, self.dispo or "Non précisé")
        )

        dch = g.get_channel(DEMANDS_CHANNEL_ID)
        if dch:
            await dch.send(f"Nouveau ticket créé : {ch.mention} — {a.mention} (Donjon **{self.d}**)")

        # Bouton validation persistant
        await ch.send(f"<@{pid}> — Cliquez pour valider le passage :", view=FeedbackPersistentView())

        sc = g.get_channel(SCREEN_CHANNEL_ID)
        if sc and p:
            try:
                await sc.set_permissions(p, view_channel=True, send_messages=True)
            except:
                pass

        # Nettoyage messages éphémères
        for lst in list(user_messages.values()):
            for m in lst:
                if m.author == bot.user:
                    try:
                        await m.delete()
                    except:
                        pass
        user_messages.clear()

class FeedbackPersistentView(View):
    """
    View persistante => survit aux reboots.
    Elle relit les infos dans le message récap du ticket (aucune META visible).
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Valider passage / Envoyer feedback",
        style=discord.ButtonStyle.danger,
        custom_id="passage_validate_v1"
    )
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return

        fb = interaction.guild.get_channel(FEEDBACK_CHANNEL_ID)
        if not isinstance(fb, discord.TextChannel):
            return await interaction.response.send_message("❌ Channel feedback introuvable.", ephemeral=True)

        recap_msg = await find_recap_message(interaction.channel)
        if not recap_msg or not recap_msg.embeds:
            return await interaction.response.send_message("❌ Je ne retrouve pas le récapitulatif du ticket.", ephemeral=True)

        recap = recap_msg.embeds[0]
        client_val = read_field(recap, "Client") or ""
        donjon_val = read_field(recap, "Donjon") or "Inconnu"
        succes_val = read_field(recap, "Succès demandés") or "Aucun"

        # Client id
        client_id = extract_first_id_from_mention(client_val)
        if not client_id:
            ids = extract_all_ids_from_text(recap_msg.content)
            client_id = ids[0] if ids else None

        # Passeur id (dans "client • <@pid>")
        ids_in_text = extract_all_ids_from_text(recap_msg.content)
        passeur_id = None
        if client_id:
            for x in ids_in_text:
                if x != client_id:
                    passeur_id = x
                    break
        if not passeur_id:
            passeur_id = OWNER_ID

        # ✅ Autorisation : seul le passeur assigné ou OWNER_ID peut valider
        if interaction.user.id not in (passeur_id, OWNER_ID):
            return await interaction.response.send_message(
                "❌ Tu ne peux pas valider ce passage. Seul le passeur assigné (ou un admin) peut le faire.",
                ephemeral=True
            )

        disp = interaction.channel.topic if interaction.channel.topic else "Non précisé"

        # ✅ "Par" = la personne autorisée qui clique
        author_id = interaction.user.id
        client_mention = f"<@{client_id}>" if client_id else (client_val or "Client inconnu")

        e = discord.Embed(title="Passage effectué !", color=0x2ECC71)
        e.add_field(name="Par", value=f"<@{author_id}>", inline=False)
        e.add_field(name="Pour", value=client_mention, inline=False)
        e.add_field(name="Donjon", value=donjon_val, inline=False)
        e.add_field(name="Succès demandés", value=succes_val or "Aucun", inline=False)
        e.add_field(name="Disponibilité", value=disp, inline=False)
        e.add_field(name="💬 Commentaires", value="*(Aucun commentaire pour le moment)*", inline=False)

        await fb.send(embed=e)

        # supprime le message bouton pour éviter double validation
        try:
            await interaction.message.delete()
        except:
            pass

        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass

class AreaView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Frigost 2", style=discord.ButtonStyle.primary, custom_id="area_f2")
    async def f2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_area(interaction, "Frigost 2")

    @discord.ui.button(label="Pandala", style=discord.ButtonStyle.primary, custom_id="area_pandala")
    async def pandala(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_area(interaction, "Pandala")

    @discord.ui.button(label="Otomaii", style=discord.ButtonStyle.primary, custom_id="area_otoma")
    async def otomaii(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_area(interaction, "Otomaii")

    async def handle_area(self, interaction: discord.Interaction, zone: str):
        dons = (
            ["Obsidiantre","Tengu","Korriandre","Kolosso","Glours","Sakaii"] if zone=="Frigost 2"
            else (["Nagate","Tanu","Founo","Dojo du vent","Damadrya","Katamashii"] if zone=="Pandala" else ["Kralamour","Kimbo"])
        )
        v = View()
        v.add_item(DonjonSelect(dons, zone))
        await interaction.response.send_message(f"Choisissez le donjon {zone} :", view=v, ephemeral=True)
        user_messages.setdefault(interaction.user.id, []).append(await interaction.original_response())

class BotDashboardView(View):
    # On garde UNIQUEMENT "Lancer le bot". Pas de "Mettre hors ligne".
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚀 Lancer le bot", style=discord.ButtonStyle.primary, custom_id="dash_launch")
    async def l(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎟️ Choisissez la zone :", view=AreaView(), ephemeral=True)
        user_messages.setdefault(interaction.user.id, []).append(await interaction.original_response())

async def post_bot_dashboard():
    global dashboard_message
    await bot.wait_until_ready()
    g = bot.get_guild(GUILD_ID)
    if not g:
        return
    c = g.get_channel(WAKEUP_CHANNEL_ID)
    if not c:
        return

    async for m in c.history(limit=50):
        if m.author == bot.user and m.embeds and "Bot de création" in (m.embeds[0].title or ""):
            dashboard_message = m
            break

    if not dashboard_message:
        e = discord.Embed(
            title="🤖 Bot de création de demandes de passage",
            description="Bienvenue sur le bot de création de demandes de passage !",
            color=0x2F3136
        )
        e.add_field(name="État du bot", value="✅ En ligne")
        v = BotDashboardView()
        msg = await c.send(embed=e, view=v)
        try:
            await msg.pin()
        except:
            pass
        dashboard_message = msg
    else:
        old = dashboard_message.embeds[0]
        e = discord.Embed(title=old.title, description=old.description, color=old.color)
        e.add_field(name="État du bot", value="✅ En ligne")
        await dashboard_message.edit(embed=e, view=BotDashboardView())

@bot.tree.command(name="reservations", description="Ouvre la procédure de réservation", guild=discord.Object(id=GUILD_ID))
async def reservations(i: discord.Interaction):
    await i.response.send_message("🎟️ Choisissez la zone :", view=AreaView(), ephemeral=True)
    user_messages.setdefault(i.user.id, []).append(await i.original_response())

# =========================
# Commande secours : !rebtn
# =========================
@bot.command(name="rebtn")
async def rebtn(ctx: commands.Context):
    """
    À utiliser dans un ticket si le message bouton a été supprimé.
    Renvoie un nouveau bouton persistant de validation.
    """
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Seul le propriétaire peut utiliser cette commande.", delete_after=10)
    if not isinstance(ctx.channel, discord.TextChannel):
        return
    recap = await find_recap_message(ctx.channel)
    if not recap:
        return await ctx.reply("❌ Je ne retrouve pas le récapitulatif dans ce ticket.", delete_after=15)

    await ctx.send("🔁 Nouveau bouton de validation :", view=FeedbackPersistentView())

# =========================
# Events: Screens + Comments robustes
# =========================
@bot.event
async def on_message(m: discord.Message):
    # 1) Screens: on colle l'image sur le dernier feedback où "Par" = auteur
    if m.channel.id == SCREEN_CHANNEL_ID and not m.author.bot:
        if m.attachments and m.guild:
            a = m.attachments[0]
            if "image" in (a.content_type or ""):
                fbm = await find_latest_feedback_message_for_author(m.guild, m.author.id)
                if fbm and fbm.embeds:
                    e = fbm.embeds[0]
                    e.set_image(url=a.url)
                    try:
                        await fbm.edit(embed=e)
                    except:
                        pass

    # 2) Commentaires: si reply dans feedback channel, on modifie l'embed ciblé
    if (
        m.channel.id == FEEDBACK_CHANNEL_ID
        and not m.author.bot
        and m.reference
        and m.reference.message_id
    ):
        try:
            fbm = await m.channel.fetch_message(m.reference.message_id)
        except:
            fbm = None

        if fbm and fbm.author == bot.user and fbm.embeds:
            e = fbm.embeds[0]
            if e.title and "Passage effectué" in e.title:
                txt = (m.content or "").strip()

                par_id = extract_first_id_from_mention(read_field(e, "Par") or "")
                client_id = extract_first_id_from_mention(read_field(e, "Pour") or "")

                if m.author.id == OWNER_ID:
                    label = "🔴 Immo"
                elif par_id and m.author.id == par_id:
                    label = "👑 Passeur"
                elif client_id and m.author.id == client_id:
                    label = "👤 Client"
                else:
                    label = "👤 Client"

                if txt:
                    current = read_field(e, "💬 Commentaires") or ""
                    lines = [x for x in current.split("\n") if x.strip() and "*(Aucun" not in x]
                    lines.append(f"{label}: {txt}")
                    new_comments = "\n".join(lines[-8:]) if lines else "*(Aucun commentaire pour le moment)*"
                    update_or_add_comment_field(e, new_comments)

                if m.attachments:
                    a = m.attachments[0]
                    if "image" in (a.content_type or ""):
                        e.set_image(url=a.url)

                try:
                    await fbm.edit(embed=e)
                except:
                    pass

                try:
                    await m.delete()
                except:
                    pass

    await bot.process_commands(m)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("✅ Slash commands synchronisées sur la guilde", GUILD_ID)
    except Exception as e:
        print("❌ Sync erreur:", e)

    # Enregistre la view persistante au démarrage (crucial pour survivre aux reboots)
    bot.add_view(FeedbackPersistentView())

    await post_bot_dashboard()

def main():
    t = os.getenv("DISCORD_TOKEN")
    if not t:
        raise RuntimeError("DISCORD_TOKEN manquant (mets-le dans .env ou variable d'environnement)")
    bot.run(t)

if __name__ == "__main__":
    main()