import os, json, re, discord
from pathlib import Path
from discord.ext import commands
from discord.ui import View, Button, Select
from dotenv import load_dotenv

load_dotenv()

# ========= Helpers env =========
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

# ========= Discord setup =========
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_messages, feedback_threads, last_feedback_for = {}, {}, {}
dashboard_message = None

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

DISABLED_SUCCES = {"Sakaii": ["sakaii_blitzkrieg"],"Glours": ["glours_collant"],"Tanu": ["tanu_blitz"],
                   "Dojo du vent": ["dojo_premier","dojo_duo"],"Katamashii": ["katamashii_hardi","katamashii_duo"]}

# ========= Ticket META utilities =========
META_PREFIX = "META_PASSAGE:"
META_RE = re.compile(r"^META_PASSAGE:\s*(\{.*\})\s*$")

def build_meta(client_id: int, passeur_id: int, area: str, donjon: str, succes_labels: str) -> str:
    data = {
        "client_id": client_id,
        "passeur_id": passeur_id,
        "area": area,
        "donjon": donjon,
        "succes": succes_labels,
    }
    return f"{META_PREFIX} {json.dumps(data, ensure_ascii=False)}"

def parse_meta_from_text(text: str) -> dict | None:
    for line in (text or "").splitlines():
        m = META_RE.match(line.strip())
        if m:
            try:
                return json.loads(m.group(1))
            except:
                return None
    return None

async def find_ticket_meta(channel: discord.TextChannel) -> dict | None:
    # On cherche dans les ~30 derniers messages du ticket
    async for m in channel.history(limit=30, oldest_first=True):
        meta = parse_meta_from_text(m.content)
        if meta:
            return meta
    return None

# ========= Core helpers =========
def load_passeurs_map():
    try:
        if not PASSEURS_JSON_PATH.exists():
            return {}
        with open(PASSEURS_JSON_PATH, "r", encoding="utf-8") as f:
            return {str(k): int(v) for k,v in json.load(f).items()}
    except:
        return {}

def get_passeur_for_donjon(d): return load_passeurs_map().get(d, OWNER_ID)

def next_ticket_name(cat,prefix):
    n=[int(m.group(1)) for c in cat.text_channels for m in [re.match(rf"^{re.escape(prefix)}-(\d{{3}})$",c.name)] if m] if cat else []
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

# ========= Views =========
class DonjonSelect(Select):
    def __init__(self,l,a): super().__init__(placeholder="Choisissez un donjon...",options=[discord.SelectOption(label=x,value=x) for x in l]);self.a=a
    async def callback(self,i):
        c=self.values[0];v=MultiStepView(self.a,c)
        await i.response.send_message(embed=discord.Embed(title=f"{self.a} — {c}",description="Commencez par choisir si vous voulez faire les succès.",color=0x2F3136),view=v,ephemeral=True)
        user_messages.setdefault(i.user.id,[]).append(await i.original_response())

class MultiStepView(View):
    def __init__(self,a,d): super().__init__(timeout=900);self.a=a;self.d=d;self.s=[];self.dispo=None;self.stage="ask"
    @discord.ui.button(label="Succès : Oui",style=discord.ButtonStyle.secondary,custom_id="y")
    async def y(self,i,b): await self.succes(i,True)
    @discord.ui.button(label="Succès : Non",style=discord.ButtonStyle.secondary,custom_id="n")
    async def n(self,i,b): await self.succes(i,False)
    async def succes(self,i,yes):
        self.clear_items()
        if yes:
            [self.add_item(Button(label=l,style=(discord.ButtonStyle.danger if c in DISABLED_SUCCES.get(self.d,[]) else discord.ButtonStyle.secondary),custom_id=f"s_{c}",disabled=c in DISABLED_SUCCES.get(self.d,[]))) for l,c in DONJON_SUCCES.get(self.d,[])]
            self.stage="sel"
        else:self.stage="disp"
        self.add_item(Button(label="Suivant ➜",style=discord.ButtonStyle.danger,custom_id="next"))
        await i.response.edit_message(view=self)
    async def interaction_check(self,i):
        cid=i.data.get("custom_id")
        if self.stage=="sel" and cid.startswith("s_"):
            c=cid[2:];self.s.remove(c) if c in self.s else self.s.append(c)
            for x in self.children:
                if hasattr(x,"custom_id") and x.custom_id==cid:
                    x.style=discord.ButtonStyle.success if c in self.s else discord.ButtonStyle.secondary
            await i.response.edit_message(view=self);return False
        if cid=="next":
            self.clear_items();[self.add_item(Button(label=l,style=discord.ButtonStyle.secondary,custom_id=id)) for l,id in [("✅ Dès que possible","now"),("📅 À planifier","later")]]
            self.add_item(Button(label="Valider la demande",style=discord.ButtonStyle.danger,custom_id="confirm",disabled=True));self.stage="disp"
            await i.response.edit_message(view=self);return False
        if self.stage=="disp" and cid in["now","later"]:
            self.dispo="Passage dès que possible" if cid=="now" else "Passage à planifier"
            for x in self.children:
                if hasattr(x,"custom_id") and x.custom_id in["now","later"]:
                    x.style=discord.ButtonStyle.success if x.custom_id==cid else discord.ButtonStyle.secondary
                if hasattr(x,"custom_id") and x.custom_id=="confirm": x.disabled=False
            await i.response.edit_message(view=self);return False
        if self.stage=="disp" and cid=="confirm":await self.create(i);return False
        return True
    async def create(self,i):
        await i.response.defer(ephemeral=True)
        g,a=i.guild,i.user;cat=g.get_channel(NEW_CATEGORY_ID)
        pid=get_passeur_for_donjon(self.d);p=g.get_member(pid)
        ow={g.default_role:discord.PermissionOverwrite(view_channel=False),g.me:discord.PermissionOverwrite(view_channel=True,send_messages=True),a:discord.PermissionOverwrite(view_channel=True,send_messages=True)}
        for x in [p,g.get_member(OWNER_ID)]:
            if x: ow[x]=discord.PermissionOverwrite(view_channel=True,send_messages=True)
        ch=await g.create_text_channel(next_ticket_name(cat,TICKET_PREFIX),category=cat,overwrites=ow)
        try:
            await ch.edit(topic=self.dispo or "Non précisé")
        except: pass
        s=labels_from_success_codes(self.d,self.s)

        # 1) message recap
        await ch.send(f"{a.mention} • <@{pid}>",embed=make_summary_embed(a,self.a,self.d,s,self.dispo or "Non précisé"))

        # 2) meta (sert à reconstruire les boutons après reboot)
        await ch.send(build_meta(a.id, pid, self.a, self.d, s))

        d=g.get_channel(DEMANDS_CHANNEL_ID)
        if d: await d.send(f"Nouveau ticket créé : {ch.mention} — {a.mention} (Donjon **{self.d}**)")

        # 3) bouton persistant (custom_id fixe + add_view au démarrage)
        await ch.send(f"<@{pid}> — Cliquez pour valider le passage :",view=FeedbackPersistentView())

        sc=g.get_channel(SCREEN_CHANNEL_ID)
        if sc and p: await sc.set_permissions(p,view_channel=True,send_messages=True)
        for lst in list(user_messages.values()):
            for m in lst:
                if m.author==bot.user:
                    try: await m.delete()
                    except: pass
        user_messages.clear()

class FeedbackPersistentView(View):
    """
    View persistante: survit aux reboots.
    Elle ne stocke rien en mémoire: elle relit les infos META du ticket.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Valider passage / Envoyer feedback",
        style=discord.ButtonStyle.danger,
        custom_id="passage_validate_v1",
    )
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return

        # On relit la META dans le ticket
        meta = await find_ticket_meta(interaction.channel)
        if not meta:
            return await interaction.response.send_message(
                "❌ Impossible de valider : je ne retrouve pas les infos du ticket (META).",
                ephemeral=True
            )

        client_id = int(meta["client_id"])
        passeur_id = int(meta["passeur_id"])
        donjon = meta.get("donjon", "Inconnu")
        succes = meta.get("succes", "Aucun")

        fb = interaction.guild.get_channel(FEEDBACK_CHANNEL_ID)
        if not fb:
            return await interaction.response.send_message("❌ Channel feedback introuvable.", ephemeral=True)

        disp = interaction.channel.topic if interaction.channel.topic else "Non précisé"
        author_id = passeur_id if interaction.user.id == OWNER_ID else interaction.user.id

        client_member = interaction.guild.get_member(client_id)
        client_mention = client_member.mention if client_member else f"<@{client_id}>"

        e = discord.Embed(title="Passage effectué !", color=0x2ECC71)
        e.add_field(name="Par", value=f"<@{author_id}>", inline=False)
        e.add_field(name="Pour", value=client_mention, inline=False)
        e.add_field(name="Donjon", value=donjon, inline=False)
        e.add_field(name="Succès demandés", value=succes or "Aucun", inline=False)
        e.add_field(name="Disponibilité", value=disp, inline=False)
        e.add_field(name="💬 Commentaires", value="*(Aucun commentaire pour le moment)*", inline=False)

        msg = await fb.send(embed=e)
        feedback_threads[msg.id] = {"client_id": client_id, "passeur_id": passeur_id, "comments": ""}
        last_feedback_for[passeur_id] = msg
        last_feedback_for[OWNER_ID] = msg

        # On supprime le message bouton (comme avant)
        try:
            await interaction.message.delete()
        except:
            pass

        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass

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
        v=View();v.add_item(DonjonSelect(dons,zone));await interaction.response.send_message(f"Choisissez le donjon {zone} :",view=v,ephemeral=True)
        user_messages.setdefault(interaction.user.id,[]).append(await interaction.original_response())

class BotDashboardView(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🚀 Lancer le bot",style=discord.ButtonStyle.primary,custom_id="dash_launch")
    async def l(self,i,b):await i.response.send_message("🎟️ Choisissez la zone :",view=AreaView(),ephemeral=True);user_messages.setdefault(i.user.id,[]).append(await i.original_response())
    @discord.ui.button(label="❌ Mettre hors ligne",style=discord.ButtonStyle.danger,custom_id="dash_stop")
    async def s(self,i,b):
        if i.user.id!=OWNER_ID:return await i.response.send_message("❌ Seul le propriétaire peut utiliser ce bouton.",ephemeral=True)
        await update_dashboard_status(False);await i.response.send_message("✅ Bot mis hors ligne.",ephemeral=True)

async def post_bot_dashboard():
    global dashboard_message;await bot.wait_until_ready();g=bot.get_guild(GUILD_ID);c=g.get_channel(WAKEUP_CHANNEL_ID)
    if not c:return
    async for m in c.history(limit=50):
        if m.author==bot.user and m.embeds and "Bot de création" in m.embeds[0].title:dashboard_message=m;break
    if not dashboard_message:
        e=discord.Embed(title="🤖 Bot de création de demandes de passage",description="Bienvenue sur le bot de création de demandes de passage !",color=0x2F3136)
        e.add_field(name="État du bot",value="✅ En ligne");v=BotDashboardView();m=await c.send(embed=e,view=v)
        try:await m.pin()
        except:pass;dashboard_message=m
    else:await update_dashboard_status(True)

async def update_dashboard_status(on=True):
    global dashboard_message
    if not dashboard_message:return
    e=dashboard_message.embeds[0];n=discord.Embed(title=e.title,description=e.description,color=e.color)
    n.add_field(name="État du bot",value="✅ En ligne" if on else "❌ Hors ligne");await dashboard_message.edit(embed=n,view=BotDashboardView())

@bot.tree.command(name="reservations",description="Ouvre la procédure de réservation",guild=discord.Object(id=GUILD_ID))
async def r(i):await i.response.send_message("🎟️ Choisissez la zone :",view=AreaView(),ephemeral=True);user_messages.setdefault(i.user.id,[]).append(await i.original_response())

# ========= Commande réparation: !rebtn =========
@bot.command(name="rebtn")
async def rebtn(ctx: commands.Context):
    """
    À utiliser DANS un ticket.
    Le bot renvoie un nouveau bouton "Valider passage" (persistant) basé sur META.
    """
    if not isinstance(ctx.channel, discord.TextChannel):
        return

    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Seul le propriétaire peut utiliser cette commande.", delete_after=10)

    meta = await find_ticket_meta(ctx.channel)
    if not meta:
        return await ctx.reply("❌ Je ne trouve pas la META du ticket (impossible de recréer le bouton).", delete_after=15)

    await ctx.send("🔁 Nouveau bouton de validation :", view=FeedbackPersistentView())

@bot.event
async def on_message(m):
    if m.channel.id==SCREEN_CHANNEL_ID and not m.author.bot:
        fb=last_feedback_for.get(m.author.id)
        if fb and m.attachments:
            a=m.attachments[0]
            if "image" in (a.content_type or ""):
                e=fb.embeds[0] if fb.embeds else discord.Embed(title="Passage effectué !",color=0x2ECC71);e.set_image(url=a.url);await fb.edit(embed=e)
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
                    e.set_field_at(idx,name="💬 Commentaires",value=data["comments"] or "*(Aucun commentaire pour le moment)*",inline=False);found=True;break
            if not found: e.add_field(name="💬 Commentaires",value=data["comments"] or "*(Aucun commentaire pour le moment)*",inline=False)
            feedback_threads[fbm.id]=data
            try: await fbm.edit(embed=e)
            except: pass
        if m.attachments:
            a=m.attachments[0]
            if "image" in (a.content_type or ""):
                e.set_image(url=a.url)
                try: await fbm.edit(embed=e)
                except: pass
        try: await m.delete()
        except: pass
    await bot.process_commands(m)

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("✅ Slash commands synchronisées sur la guilde", GUILD_ID)
    except Exception as e:
        print("❌ Sync erreur:", e)

    # IMPORTANT: enregistre la view persistante au démarrage (survit aux reboots)
    bot.add_view(FeedbackPersistentView())

    await post_bot_dashboard()

def main():
    t=os.getenv("DISCORD_TOKEN")
    if not t:raise RuntimeError("DISCORD_TOKEN manquant (mets-le dans .env ou variable d'environnement)")
    bot.run(t)

if __name__=="__main__":
    main()