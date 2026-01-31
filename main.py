# main.py
import os, json, re, logging, sys, discord
from discord.ext import commands
from discord.ui import View, Button, Select
from dotenv import load_dotenv

# ── Config & logs ──────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Fix : éviter les crashs de logs discord.gateway (problème de %s / format)
logging.getLogger("discord.gateway").setLevel(logging.ERROR)

class _EscapePercentFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # On double les % dans les messages discord.gateway pour éviter les erreurs de format
        if record.name.startswith("discord.gateway") and isinstance(record.msg, str):
            record.msg = record.msg.replace("%", "%%")
        return True

logging.getLogger().addFilter(_EscapePercentFilter())

log = logging.getLogger("bot")

# IDs (remplace si besoin)
GUILD_ID = 1393982298654900345
DEMANDS_CHANNEL_ID = 1393984437078720603
OWNER_ID = 342021125800198144
TICKET_PREFIX = "ticket-passage-donjon"
NEW_CATEGORY_ID = 1426346995466895480
FEEDBACK_CHANNEL_ID = 1394291299066056745
SCREEN_CHANNEL_ID = 1427079620246638732
WAKEUP_CHANNEL_ID = 1426347294525096119
ALERT_CHANNEL_ID = int(os.getenv("ALERT_CHANNEL_ID", "0"))  # 0 = désactivé par défaut
PASSEURS_JSON_PATH = "passeurs.json"

# ── Discord bot ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_messages, feedback_threads, last_feedback_for = {}, {}, {}
dashboard_message = None

# ── Données succès ─────────────────────────────────────────────────────────────
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
    "Dojo du vent": [("Premier","dojo_premier"),("Pusillanime","dojo_pusillanime"),("Duo","dojo_duo")],
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

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_passeurs_map():
    try:
        with open(PASSEURS_JSON_PATH, "r", encoding="utf-8") as f:
            return {str(k): int(v) for k,v in json.load(f).items()}
    except Exception:
        return {}

def get_passeur_for_donjon(d):
    return load_passeurs_map().get(d, OWNER_ID)

def next_ticket_name(cat,prefix):
    n=[int(m.group(1)) for c in (cat.text_channels if cat else []) for m in [re.match(rf"^{re.escape(prefix)}-(\d{{3}})$",c.name)] if m]
    return f"{prefix}-{(max(n)+1) if n else 1:03d}"

def make_summary_embed(u,a,d,s,disp):
    e=discord.Embed(title="Récapitulatif de la réservation",color=0x2F3136)
    e.add_field(name="Client",value=u.mention,inline=False)
    e.add_field(name="Zone",value=a,inline=False)
    e.add_field(name="Donjon",value=d,inline=False)
    e.add_field(name="Succès demandés",value=s,inline=False)
    e.add_field(name="Disponibilité",value=disp,inline=False)
    e.set_footer(text="Vérifie les informations puis clique sur « Valider la demande ».");return e

def labels_from_success_codes(d,sel):
    l=[];[l.append(lbl) for cid in sel for lbl,cid2 in DONJON_SUCCES.get(d,[]) if cid2==cid];return ", ".join(l) if l else "Aucun"

async def ensure_passeur_permissions_on_screens(guild: discord.Guild):
    screen_chan = guild.get_channel(SCREEN_CHANNEL_ID)
    if not screen_chan: return
    mapping = load_passeurs_map()
    for _, pid in mapping.items():
        m = guild.get_member(int(pid))
        if not m: continue
        try:
            await screen_chan.set_permissions(
                m,
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                attach_files=True,
                add_reactions=True,
                mention_everyone=True
            )
        except Exception:
            pass

# ── UI ────────────────────────────────────────────────────────────────────────
class DonjonSelect(Select):
    def __init__(self,l,a):
        super().__init__(placeholder="Choisissez un donjon...",
                         options=[discord.SelectOption(label=x,value=x) for x in l])
        self.a=a

    async def callback(self,i):
        c=self.values[0]
        v=MultiStepView(self.a,c)
        await i.response.send_message(
            embed=discord.Embed(
                title=f"{self.a} — {c}",
                description="Commencez par choisir si vous voulez faire les succès.",
                color=0x2F3136
            ),
            view=v,ephemeral=True)
        user_messages.setdefault(i.user.id,[]).append(await i.original_response())

class MultiStepView(View):
    def __init__(self,a,d):
        super().__init__(timeout=900)
        self.a=a;self.d=d;self.s=[];self.dispo=None;self.stage="ask"

    @discord.ui.button(label="Succès : Oui",style=discord.ButtonStyle.secondary,custom_id="y")
    async def y(self,i,b): await self.succes(i,True)

    @discord.ui.button(label="Succès : Non",style=discord.ButtonStyle.secondary,custom_id="n")
    async def n(self,i,b): await self.succes(i,False)

    async def succes(self,i,yes):
        self.clear_items()
        if yes:
            for l,c in DONJON_SUCCES.get(self.d,[]):
                self.add_item(Button(
                    label=l,
                    style=(discord.ButtonStyle.danger if c in DISABLED_SUCCES.get(self.d,[]) else discord.ButtonStyle.secondary),
                    custom_id=f"s_{c}",
                    disabled=c in DISABLED_SUCCES.get(self.d,[])
                ))
            self.stage="sel"
        else:
            self.stage="disp"

        self.add_item(Button(label="Suivant ➜",style=discord.ButtonStyle.danger,custom_id="next"))
        await i.response.edit_message(view=self)

    async def interaction_check(self,i):
        cid=i.data.get("custom_id")
        if self.stage=="sel" and cid.startswith("s_"):
            c=cid[2:]
            if c in self.s: self.s.remove(c)
            else: self.s.append(c)
            for x in self.children:
                if hasattr(x,"custom_id") and x.custom_id==cid:
                    x.style=discord.ButtonStyle.success if c in self.s else discord.ButtonStyle.secondary
            await i.response.edit_message(view=self)
            return False

        if cid=="next":
            self.clear_items()
            for l,id in [("✅ Dès que possible","now"),("📅 À planifier","later")]:
                self.add_item(Button(label=l,style=discord.ButtonStyle.secondary,custom_id=id))
            self.add_item(Button(label="Valider la demande",style=discord.ButtonStyle.danger,custom_id="confirm",disabled=True))
            self.stage="disp"
            await i.response.edit_message(view=self)
            return False

        if self.stage=="disp" and cid in ["now","later"]:
            self.dispo="Passage dès que possible" if cid=="now" else "Passage à planifier"
            for x in self.children:
                if hasattr(x,"custom_id") and x.custom_id in["now","later"]:
                    x.style=discord.ButtonStyle.success if x.custom_id==cid else discord.ButtonStyle.secondary
                if hasattr(x,"custom_id") and x.custom_id=="confirm":
                    x.disabled=False
            await i.response.edit_message(view=self)
            return False

        if self.stage=="disp" and cid=="confirm":
            await self.create(i)
            return False
        return True

    async def create(self,i):
        await i.response.defer(ephemeral=True)
        g,a=i.guild,i.user
        cat=g.get_channel(NEW_CATEGORY_ID)
        pid=get_passeur_for_donjon(self.d)
        p=g.get_member(pid)

        ow={
            g.default_role:discord.PermissionOverwrite(view_channel=False),
            g.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True,attach_files=True,add_reactions=True,mention_everyone=True),
            a:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True,attach_files=True,add_reactions=True,mention_everyone=True)
        }

        if p:
            ow[p]=discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                add_reactions=True,
                mention_everyone=True
            )

        owner=g.get_member(OWNER_ID)
        if owner and owner!=p:
            ow[owner]=discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                add_reactions=True,
                mention_everyone=True
            )

        ch=await g.create_text_channel(next_ticket_name(cat,TICKET_PREFIX),category=cat,overwrites=ow)
        try: await ch.edit(topic=self.dispo or "Non précisé")
        except Exception: pass

        s=labels_from_success_codes(self.d,self.s)
        await ch.send(f"{a.mention} • <@{pid}>",embed=make_summary_embed(a,self.a,self.d,s,self.dispo or "Non précisé"))

        dchan=g.get_channel(DEMANDS_CHANNEL_ID)
        if dchan:
            try: await dchan.send(f"Nouveau ticket créé : {ch.mention} — {a.mention} (Donjon **{self.d}**)")
            except Exception: pass

        await ch.send(f"<@<@{pid}> — Cliquez pour valider le passage :",view=FeedbackView(a,pid,self.d,s))

        sc=g.get_channel(SCREEN_CHANNEL_ID)
        if sc and p:
            try:
                await sc.set_permissions(
                    p,
                    view_channel=True,
                    read_message_history=True,
                    send_messages=True,
                    attach_files=True,
                    add_reactions=True,
                    mention_everyone=True
                )
            except Exception: pass

        for lst in list(user_messages.values()):
            for m in lst:
                if m.author==bot.user:
                    try: await m.delete()
                    except Exception: pass
        user_messages.clear()

# ── FeedbackView (validation protégée) ────────────────────────────────────────
class FeedbackView(View):
    def __init__(self,c,pid,d,s):
        super().__init__(timeout=None)
        self.c=c
        self.pid=pid
        self.d=d
        self.s=s
        # seuls ces IDs peuvent cliquer le bouton :
        self._allowed_ids = {OWNER_ID, int(pid)}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Bloque l'interaction pour toute personne non autorisée."""
        if interaction.user.id not in self._allowed_ids:
            try:
                await interaction.response.send_message(
                    "❌ Seul le propriétaire ou le passeur peut valider le passage.",
                    ephemeral=True
                )
            except Exception:
                pass
            return False
        return True

    @discord.ui.button(label="Valider passage / Envoyer feedback",style=discord.ButtonStyle.danger)
    async def v(self,i,b):
        # À ce stade, interaction_check a déjà filtré.
        actor_id = i.user.id
        fb=i.guild.get_channel(FEEDBACK_CHANNEL_ID)
        if not fb: 
            return
        disp=i.channel.topic if i.channel and i.channel.topic else "Non précisé"
        e=discord.Embed(title="Passage effectué !",color=0x2ECC71)
        e.add_field(name="Par",value=f"<@{actor_id}>",inline=False)
        e.add_field(name="Pour",value=self.c.mention,inline=False)
        e.add_field(name="Donjon",value=self.d,inline=False)
        e.add_field(name="Succès demandés",value=self.s or "Aucun",inline=False)
        e.add_field(name="Disponibilité",value=disp,inline=False)
        e.add_field(name="💬 Commentaires",value="*(Aucun commentaire pour le moment)*",inline=False)
        msg=await fb.send(embed=e)
        feedback_threads[msg.id]={"client_id":self.c.id,"passeur_id":self.pid,"comments":""}
        last_feedback_for[self.pid]=msg
        last_feedback_for[OWNER_ID]=msg
        try: await i.message.delete()
        except Exception: pass
        try: await i.response.defer(ephemeral=True)
        except Exception: pass

class AreaView(View):
    def __init__(self): super().__init__(timeout=None)

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
        dons=["Obsidiantre","Tengu","Korriandre","Kolosso","Glours","Sakaii"] if zone=="Frigost 2" else (["Nagate","Tanu","Founo","Dojo du vent","Damadrya","Katamashii"] if zone=="Pandala" else ["Kralamour","Kimbo"])
        v=View();v.add_item(DonjonSelect(dons,zone))
        await interaction.response.send_message(f"Choisissez le donjon {zone} :",view=v,ephemeral=True)
        user_messages.setdefault(interaction.user.id,[]).append(await interaction.original_response())

class BotDashboardView(View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="🚀 Lancer le bot",style=discord.ButtonStyle.primary,custom_id="dash_launch")
    async def l(self,i,b):
        await i.response.send_message("🎟️ Choisissez la zone :",view=AreaView(),ephemeral=True)
        user_messages.setdefault(i.user.id,[]).append(await i.original_response())

async def post_bot_dashboard():
    g=bot.get_guild(GUILD_ID)
    if not g:
        log.warning("Guild %s introuvable pour le dashboard", GUILD_ID)
        return
    c=g.get_channel(WAKEUP_CHANNEL_ID)
    if not c:
        log.warning("Salon WAKEUP_CHANNEL_ID=%s introuvable pour le dashboard", WAKEUP_CHANNEL_ID)
        return

    existing_msg = None
    try:
        async for m in c.history(limit=50):
            if m.author==bot.user and m.embeds and "Bot de création" in m.embeds[0].title:
                existing_msg = m
                break
    except Exception as e:
        log.warning("Impossible de lire l'historique du salon wakeup: %s", e)
        existing_msg = None

    e=discord.Embed(
        title="🤖 Bot de création de demandes de passage",
        description="Bienvenue sur le bot de création de demandes de passage !",
        color=0x2F3136
    )

    if existing_msg:
        try:
            await existing_msg.edit(embed=e, view=BotDashboardView())
        except Exception as ex:
            log.warning("Erreur lors de l'édition du dashboard: %s", ex)
    else:
        try:
            m=await c.send(embed=e, view=BotDashboardView())
            try: await m.pin()
            except Exception: pass
        except Exception as ex:
            log.warning("Erreur lors de l'envoi du dashboard: %s", ex)

# ── Slash: démarrer réservation ────────────────────────────────────────────────
@bot.tree.command(name="reservations",description="Ouvre la procédure de réservation",guild=discord.Object(id=GUILD_ID))
async def r(i: discord.Interaction):
    await i.response.send_message("🎟️ Choisissez la zone :",view=AreaView(),ephemeral=True)
    user_messages.setdefault(i.user.id,[]).append(await i.original_response())

# ── Events ────────────────────────────────────────────────────────────────────
@bot.event
async def on_message(m):
    if m.channel.id==SCREEN_CHANNEL_ID and not m.author.bot:
        fb=last_feedback_for.get(m.author.id)
        if fb and m.attachments:
            a=m.attachments[0]
            if "image" in (a.content_type or ""):
                e=fb.embeds[0] if fb.embeds else discord.Embed(title="Passage effectué !",color=0x2ECC71)
                e.set_image(url=a.url)
                await fb.edit(embed=e)

    if m.channel.id==FEEDBACK_CHANNEL_ID and not m.author.bot and m.reference and m.reference.message_id in feedback_threads:
        fbm=await m.channel.fetch_message(m.reference.message_id)
        e=fbm.embeds[0] if fbm.embeds else discord.Embed(title="Passage effectué !",color=0x2ECC71)
        data=feedback_threads.get(fbm.id,{"comments":"","passeur_id":None})
        label="🔴 Immo" if m.author.id==OWNER_ID else ("👑 Passeur" if m.author.id==data.get("passeur_id") else "👤 Client")
        txt=m.content.strip()
        if txt:
            existing=[x for x in (data.get("comments","").split("\n")) if x.strip()]
            existing.append(f"{label}: {txt}")
            data["comments"]="\n".join(existing[-8:])
            found=False
            for idx,f in enumerate(e.fields):
                if f.name=="💬 Commentaires":
                    e.set_field_at(idx,name="💬 Commentaires",value=data["comments"] or "*(Aucun commentaire pour le moment)*",inline=False)
                    found=True;break
            if not found:
                e.add_field(name="💬 Commentaires",value=data["comments"] or "*(Aucun commentaire pour le moment)*",inline=False)
            feedback_threads[fbm.id]=data
            try: await fbm.edit(embed=e)
            except Exception: pass
        if m.attachments:
            a=m.attachments[0]
            if "image" in (a.content_type or ""):
                e.set_image(url=a.url)
                try: await fbm.edit(embed=e)
                except Exception: pass
        try: await m.delete()
        except Exception: pass
    await bot.process_commands(m)

@bot.event
async def on_error(event, *args, **kwargs):
    log.exception("Unhandled error in %s", event)
    if ALERT_CHANNEL_ID:
        ch = bot.get_channel(ALERT_CHANNEL_ID)
        if ch:
            try:
                await ch.send(f"⚠️ Erreur non gérée dans `{event}` — vérifie les logs serveur.")
            except Exception:
                pass

# Charger l’admin cog + sync commandes + init dashboard
_extensions_loaded = False
@bot.event
async def on_ready():
    global _extensions_loaded
    log.info("on_ready déclenché, préparation du bot...")

    try:
        await ensure_passeur_permissions_on_screens(bot.get_guild(GUILD_ID))
    except Exception as e:
        log.warning("Erreur ensure_passeur_permissions_on_screens: %s", e)

    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        log.info("Slash commands synchronisées sur la guilde %s", GUILD_ID)
    except Exception as e:
        log.warning("Sync commands échoué: %s", e)

    try:
        await post_bot_dashboard()
    except Exception as e:
        log.warning("Erreur post_bot_dashboard: %s", e)

    log.info("✅ Connecté en %s (%s)", bot.user, getattr(bot.user, "id", "?"))

# ── Entrée ────────────────────────────────────────────────────────────────────
def main():
    t=os.getenv("DISCORD_TOKEN")
    if not t:
        raise RuntimeError("DISCORD_TOKEN manquant (mets-le dans .env ou variable d'environnement)")
    bot.run(t)

if __name__=="__main__":
    main()
