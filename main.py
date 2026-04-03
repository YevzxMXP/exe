import discord
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import aiofiles
from threading import Thread
from flask import Flask
import re
from dotenv import load_dotenv

# Keep alive para manter o bot online
app = Flask('')

@app.route('/')
def home():
    return "Security Bot Online"

def run():
    try:
        app.run(host='0.0.0.0', port=5000) # Replit usa porta 5000 por padrão para webviews
    except Exception as e:
        print(f"Erro ao iniciar Flask: {e}")

def keep_alive():
    t = Thread(target=run)
    t.start()

# ID do owner do bot (CONFIGURE AQUI SEU ID)
OWNER_ID = 983196900910039090  # Substitua pelo seu ID real

# Configurações padrão para novos servidores
DEFAULT_CONFIG = {
    'auto_ban_bots': True,
    'auto_ban_new_accounts': False,
    'new_account_days': 7,
    'role_delete_punishment': 'ban',
    'channel_delete_punishment': 'ban',
    'logs_channel_id': 1451797805310939177,
    'audit_log_delay': 2,
    'max_logs_history': 100,
    'auto_kick_everyone_ping': True,
    'auto_kick_mass_ping': False,
    'max_mentions': 10,
    'auto_delete_invite_links': False,
    'whitelist_users': [],
    'protection_enabled': True,
    'anti_spam_enabled': False,
    'spam_message_count': 5,
    'spam_time_window': 10,
    'auto_mute_duration': 10,
    'mass_ping_mute_duration': 10,
    'protect_admin_roles': True,
    'backup_channels': True,
    'backup_roles': True,
    'auto_recreate_channels': True,
    'auto_recreate_roles': True,
    'monitor_bot_activity': True,
    'max_bans_per_timeframe': 3,
    'ban_timeframe_minutes': 5,
    'auto_ban_mass_banner': False,
    'auto_kick_mass_banner': True,
    'bot_protection_enabled': True
}

COLORS = {
    'danger': 0xff0000,
    'warning': 0xff9900,
    'success': 0x00ff00,
    'info': 0x0099ff,
    'purple': 0x9932cc
}

# Configurações do bot
intents = discord.Intents.all()  # Ativa todos os intents para evitar PrivilegedIntentsRequired

bot = commands.Bot(command_prefix='!sec_', intents=intents, help_command=None)

# Arquivo para salvar dados de segurança
SECURITY_DATA_FILE = "security_data.json"

class SecurityBot:
    def __init__(self):
        self.guild_configs = {}  # Configurações por servidor
        self.restored_roles = {}  # Para armazenar cargos removidos
        self.security_logs = {}  # Logs por servidor
        self.user_warnings = {}  # Avisos por usuário
        self.spam_tracker = {}  # Rastreamento de spam
        self.backup_data = {}  # Backups de canais/cargos
        self.ban_tracker = {}  # Rastreamento de banimentos por usuário/bot
        self.bot_ban_history = {}  # Histórico de bans realizados pelo BOT (safe mode)
        self.bot_activity_logs = {}  # Logs de atividade de bots
        self.category_messages = {}  # Mensagens salvas por canal (Categoria 1451797806259114080)
        self.ping_cooldowns = {}  # Cooldown para alertas de mass ping/everyone
        self.mass_creation_cooldown = {} # Cooldown para evitar logs repetidos de criação massiva

    async def load_data(self):
        """Carrega dados de segurança salvos"""
        try:
            if os.path.exists(SECURITY_DATA_FILE):
                async with aiofiles.open(SECURITY_DATA_FILE, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                    self.guild_configs = data.get('guild_configs', {})
                    self.restored_roles = data.get('restored_roles', {})
                    self.security_logs = data.get('security_logs', {})
                    self.user_warnings = data.get('user_warnings', {})
                    self.backup_data = data.get('backup_data', {})
                    self.ban_tracker = data.get('ban_tracker', {})
                    self.bot_activity_logs = data.get('bot_activity_logs', {})
                    self.category_messages = data.get('category_messages', {})
        except Exception as e:
            print(f"❌ Erro ao carregar dados de segurança: {e}")

    async def save_data(self):
        """Salva dados de segurança"""
        try:
            data = {
                'guild_configs': self.guild_configs,
                'restored_roles': self.restored_roles,
                'security_logs': self.security_logs,
                'user_warnings': self.user_warnings,
                'backup_data': self.backup_data,
                'ban_tracker': self.ban_tracker,
                'bot_activity_logs': self.bot_activity_logs,
                'category_messages': self.category_messages
            }
            async with aiofiles.open(SECURITY_DATA_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"❌ Erro ao salvar dados de segurança: {e}")

    def get_guild_config(self, guild_id: int):
        """Obtém configuração do servidor"""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.guild_configs:
            self.guild_configs[guild_id_str] = DEFAULT_CONFIG.copy()
        else:
            # Merge any missing keys from DEFAULT_CONFIG
            for key, value in DEFAULT_CONFIG.items():
                if key not in self.guild_configs[guild_id_str]:
                    self.guild_configs[guild_id_str][key] = value
        return self.guild_configs[guild_id_str]

    async def get_logs_channel(self, guild):
        """Encontra o canal de logs configurado"""
        config = self.get_guild_config(guild.id)
        if config['logs_channel_id']:
            return guild.get_channel(config['logs_channel_id'])
        return None

    async def log_security_action(self, guild, title: str, description: str, color: int, fields: List[Dict] = []):
        """Registra ação de segurança no canal de logs"""
        logs_channel = await self.get_logs_channel(guild)
        if not logs_channel:
            return

        embed = discord.Embed(
            title=f"🔒 {title}",
            description=description,
            color=color,
            timestamp=datetime.utcnow()
        )

        if fields:
            for field in fields:
                embed.add_field(
                    name=field['name'],
                    value=field['value'],
                    inline=field.get('inline', False)
                )

        embed.set_footer(text="Sistema de Segurança Automático")

        try:
            await logs_channel.send(embed=embed)

            # Salva no histórico
            guild_id_str = str(guild.id)
            if guild_id_str not in self.security_logs:
                self.security_logs[guild_id_str] = []

            log_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'title': title,
                'description': description
            }
            self.security_logs[guild_id_str].append(log_entry)

            # Mantém apenas os últimos logs
            config = self.get_guild_config(guild.id)
            max_logs = config['max_logs_history']
            self.security_logs[guild_id_str] = self.security_logs[guild_id_str][-max_logs:]

            await self.save_data()

        except Exception as e:
            print(f"❌ Erro ao enviar log de segurança: {e}")

    async def track_ban_activity(self, guild, user_or_bot, target):
        """Rastreia atividade de banimentos para detectar ações suspeitas"""
        guild_id_str = str(guild.id)
        user_id_str = str(user_or_bot.id)
        
        # 👑 OWNER DO BOT É INTOCÁVEL
        if user_or_bot.id == OWNER_ID:
            return

        # Verifica whitelist
        config = self.get_guild_config(guild.id)
        if user_or_bot.id in config.get('whitelist_users', []):
            return

        # BANIMENTO VIA MÉTODO SAFE NA PRIMEIRA TENTATIVA SUSPEITA
        bot_type = "🤖 BOT" if user_or_bot.bot else "👤 USUÁRIO"
        reason = "🔒 Segurança: Banimento não autorizado detectado (Proteção Anti-Raid)"
        banned, ban_count = await self.safe_ban(guild, user_or_bot, reason)

        if banned:
            mockery_messages = [
                "Tentativa de invasão detectada e neutralizada.",
                "O sistema de segurança identificou e removeu o infrator.",
                "Ações não autorizadas resultam em banimento imediato.",
                "Protocolo de proteção ativado. Acesso negado permanentemente.",
                "A segurança deste servidor é prioridade absoluta. Invasor removido."
            ]
            import random
            mockery = random.choice(mockery_messages)

            await self.log_security_action(
                guild,
                f"🚨 {bot_type} BANIDO INSTANTANEAMENTE",
                f"⚠️ {user_or_bot.mention} tentou banir {target.mention} e foi removido.\n\n*{mockery}*",
                COLORS['danger'],
                [
                    {'name': '🎯 Alvo', 'value': f"{target} ({target.id})", 'inline': True},
                    {'name': '⚡ Ação', 'value': f"Banimento Automático (safe {ban_count}/2)", 'inline': True}
                ]
            )

    async def safe_ban(self, guild, member, reason: str = "🔒 Segurança"):
        """Rastreia bans por executor. Avisa na 1ª vez (1/2), bane na 2ª (2/2) em 10 minutos."""
        guild_id_str = str(guild.id)
        executor_id_str = str(member.id)
        now = datetime.utcnow()
        window = timedelta(minutes=10)
        max_bans = 2

        if guild_id_str not in self.bot_ban_history:
            self.bot_ban_history[guild_id_str] = {}

        if executor_id_str not in self.bot_ban_history[guild_id_str]:
            self.bot_ban_history[guild_id_str][executor_id_str] = []

        self.bot_ban_history[guild_id_str][executor_id_str] = [
            t for t in self.bot_ban_history[guild_id_str][executor_id_str]
            if now - datetime.fromisoformat(t) < window
        ]

        count = len(self.bot_ban_history[guild_id_str][executor_id_str])
        self.bot_ban_history[guild_id_str][executor_id_str].append(now.isoformat())
        new_count = count + 1

        if new_count < max_bans:
            # 1ª ocorrência: apenas avisa, não bane
            await self.log_security_action(
                guild,
                "Aviso - Método Safe",
                f"{member.mention} baniu um membro. Método safe de {new_count}/{max_bans} em 10 minutos.\nSe banir novamente em 10 minutos, será banido automaticamente.",
                COLORS['warning']
            )
            return False, new_count

        # 2ª ocorrência ou mais: bane
        try:
            await guild.ban(member, reason=reason)
            await self.log_security_action(
                guild,
                "Ban Automático - Método Safe",
                f"BOT baniu {member.mention}. Método safe de {new_count}/{max_bans} em 10 minutos.",
                COLORS['danger']
            )
            return True, new_count
        except Exception as e:
            print(f"Erro ao banir (safe_ban): {e}")
            return False, new_count

# Instância global do sistema de segurança
security_system = SecurityBot()

@bot.event
async def on_ready():
    """Evento executado quando o bot está pronto"""
    await security_system.load_data()
    
    # Status interessante e dinâmico
    activities = [
        discord.Activity(type=discord.ActivityType.watching, name=f"🔒 {len(bot.guilds)} servidores protegidos"),
        discord.Activity(type=discord.ActivityType.listening, name="🛡️ Detectando ameaças 24/7"),
        discord.Activity(type=discord.ActivityType.playing, name="⚡ Sistema Anti-Raid Ativo"),
        discord.Game(name="🚀 Máxima Segurança Garantida!"),
    ]
    
    # Define um status aleatório
    import random
    try:
        chosen_activity = random.choice(activities)
        await bot.change_presence(
            status=discord.Status.online,
            activity=chosen_activity
        )
    except:
        pass
    
    print("SISTEMA DE SEGURANÇA OPERACIONAL")
    
    # Atualiza status a cada 30 segundos
    async def update_status():
        while True:
            await asyncio.sleep(30)
            new_activity = random.choice(activities)
            await bot.change_presence(
                status=discord.Status.online,
                activity=new_activity
            )
    
    # Inicia task de atualização de status
    bot.loop.create_task(update_status())

@bot.event
async def on_message_monitor(message):
    if message.author.id == bot.user.id:
        return

    # Monitorar mensagens na categoria específica
    if message.channel.category_id == 1451797806259114080:
        channel_id_str = str(message.channel.id)
        if channel_id_str not in security_system.category_messages:
            security_system.category_messages[channel_id_str] = []
        
        msg_data = {
            'author': str(message.author),
            'content': message.content,
            'timestamp': message.created_at.isoformat(),
            'embeds': [e.to_dict() for e in message.embeds]
        }
        security_system.category_messages[channel_id_str].append(msg_data)
        # Manter apenas as últimas 50 mensagens para evitar arquivos gigantes
        security_system.category_messages[channel_id_str] = security_system.category_messages[channel_id_str][-50:]
        await security_system.save_data()

    await bot.process_commands(message)

@bot.event
async def on_guild_channel_create(channel):
    """Detecta criação de canais (Anti-Raid)"""
    try:
        guild = channel.guild
        config = security_system.get_guild_config(guild.id)
        
        await asyncio.sleep(0.3) # Delay mínimo para log de auditoria
        
        async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
            if entry.target.id == channel.id:
                executor = entry.user
                
                # Se o executor for um bot e não for este bot, apagar canal imediatamente
                if executor.bot and executor.id != bot.user.id:
                    try:
                        await channel.delete(reason="Segurança: Canal criado por bot não autorizado")
                        
                        # Sistema de cooldown para logs de criação em massa
                        executor_id_str = str(executor.id)
                        now = datetime.utcnow()
                        last_log = security_system.mass_creation_cooldown.get(executor_id_str)
                        
                        if not last_log or (now - last_log).seconds > 30:
                            security_system.mass_creation_cooldown[executor_id_str] = now
                            await security_system.log_security_action(
                                guild,
                                "CANAIS DE BOT REMOVIDOS",
                                f"O bot {executor.mention} está criando canais de forma não autorizada. Canais removidos automaticamente.",
                                COLORS['danger']
                            )
                    except Exception as e:
                        print(f"Erro ao apagar canal de bot: {e}")
                    return

                # Owner e Whitelist imunes
                if executor.id == OWNER_ID or executor.id in config.get('whitelist_users', []):
                    return
                
                # Se for bot ou usuário malicioso -> BAN IMEDIATO e APAGAR CANAL
                try:
                    await executor.ban(reason=f"Segurança: Criação não autorizada de canal: #{channel.name}")
                    await channel.delete(reason="Segurança: Canal criado por entidade não autorizada")
                    
                    mockery = "Criação de canal não autorizada detectada. Executor removido."

                    await security_system.log_security_action(
                        guild,
                        "CANAL MALICIOSO DELETADO",
                        f"O canal #{channel.name} foi criado e removido. Executor banido.\n\n{mockery}",
                        COLORS['danger'],
                        [
                            {'name': 'Canal', 'value': f"#{channel.name}", 'inline': True}
                        ]
                    )
                except Exception as e:
                    print(f"Erro ao agir contra canal criado: {e}")
                break
    except Exception as e:
        print(f"Erro no detector de criação de canais: {e}")

@bot.event
async def on_guild_role_create(role):
    """Detecta criação de cargos (Anti-Raid)"""
    try:
        guild = role.guild
        config = security_system.get_guild_config(guild.id)
        
        await asyncio.sleep(0.3)
        
        async for entry in guild.audit_logs(action=discord.AuditLogAction.role_create, limit=1):
            if entry.target.id == role.id:
                executor = entry.user
                
                if executor.id == OWNER_ID or executor.id in config.get('whitelist_users', []):
                    return
                
                try:
                    await executor.ban(reason=f"Segurança: Criação não autorizada de cargo: @{role.name}")
                    await role.delete(reason="Segurança: Cargo criado por entidade não autorizada")
                    
                    mockery = "Criação de cargo não autorizada detectada. Executor removido."

                    await security_system.log_security_action(
                        guild,
                        "CARGO MALICIOSO DELETADO",
                        f"O cargo @{role.name} foi criado e removido. Executor banido.\n\n{mockery}",
                        COLORS['danger'],
                        [
                            {'name': 'Cargo', 'value': f"@{role.name}", 'inline': True}
                        ]
                    )
                except Exception as e:
                    print(f"Erro ao agir contra cargo criado: {e}")
                break
    except Exception as e:
        print(f"Erro no detector de criação de cargos: {e}")

@bot.event
async def on_guild_channel_delete(channel):
    """Detecta exclusão de canais"""
    try:
        guild = channel.guild
        config = security_system.get_guild_config(guild.id)

        # Funcionalidade solicitada: Recriar o canal e enviar as mensagens salvas nele mesmo
        if channel.category_id == 1451797806259114080:
            channel_id_str = str(channel.id)
            messages = security_system.category_messages.get(channel_id_str, [])
            
            # Recriar o canal
            try:
                target_channel = None
                # Determina o tipo e recria
                if isinstance(channel, discord.TextChannel):
                    target_channel = await guild.create_text_channel(
                        name=channel.name,
                        category=channel.category,
                        position=channel.position,
                        topic=getattr(channel, 'topic', None),
                        reason=f"Recuperação de canal de sistema com histórico"
                    )
                
                if target_channel and messages:
                    # Log no console
                    print(f"Canal de Sistema Deletado: #{channel.name}")
                    print(f"Canal recriado. Enviando {len(messages)} mensagens...")

                    header_embed = discord.Embed(
                        title="HISTÓRICO RECUPERADO",
                        description=f"Este canal foi deletado e recriado automaticamente.\nRestaurando últimas mensagens salvas:",
                        color=COLORS['success'],
                        timestamp=datetime.utcnow()
                    )
                    await target_channel.send(embed=header_embed)

                    for msg in messages:
                        embed = discord.Embed(
                            description=msg['content'] if msg['content'] else "*Sem conteúdo de texto*",
                            color=COLORS['purple']
                        )
                        embed.set_author(name=msg['author'])
                        embed.set_footer(text=f"Enviada em: {msg['timestamp']}")
                        
                        if msg['embeds']:
                            embed.add_field(name="📦 Contém Embeds", value="Esta mensagem possuía embeds originais.", inline=False)
                        
                        await target_channel.send(embed=embed)
                        await asyncio.sleep(0.3) # Evitar rate limit mas ser rápido

                    # Log no console confirmando a conclusão
                    print(f"✅ [RECUPERAÇÃO] Histórico restaurado com sucesso no novo canal #{target_channel.name}")
            except Exception as e:
                print(f"❌ Erro ao recriar canal ou restaurar mensagens: {e}")

        if not config['protection_enabled']:
            return

        # Salva backup do canal
        if config['backup_channels']:
            guild_id_str = str(guild.id)
            if guild_id_str not in security_system.backup_data:
                security_system.backup_data[guild_id_str] = {'channels': [], 'roles': []}

            channel_backup = {
                'name': channel.name,
                'type': str(channel.type),
                'category': channel.category.name if channel.category else None,
                'position': channel.position,
                'topic': getattr(channel, 'topic', None),
                'deleted_at': datetime.utcnow().isoformat()
            }
            security_system.backup_data[guild_id_str]['channels'].append(channel_backup)

        # Tenta pegar log de auditoria o mais rápido possível
        await asyncio.sleep(0.5) # Reduzi para ser quase instantâneo

        async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
            if entry.target.id == channel.id:
                executor = entry.user

                # 👑 OWNER E WHITELIST TÊM PROTEÇÃO TOTAL
                if executor.id == OWNER_ID:
                    return
                elif executor.id in config['whitelist_users']:
                    return

                # Punição IMEDIATA antes de qualquer outra coisa
                punishment = 'ban' # Alterado para BAN conforme solicitado
                action_applied = "Nenhuma"
                
                try:
                    # Tenta banir o executor IMEDIATAMENTE
                    if executor.id != OWNER_ID and executor.id not in config.get('whitelist_users', []):
                        member = guild.get_member(executor.id)
                        if member:
                            await member.ban(reason=f"🔒 Segurança: Deletou canal #{channel.name}")
                            action_applied = "Banimento Imediato"
                except Exception as e:
                    print(f"Erro ao aplicar punição: {e}")
                    action_applied = f"Erro: {e}"

                # Recria o canal automaticamente se habilitado
                recreated_channel = None
                if config['auto_recreate_channels']:
                    try:
                        # Determina o tipo de canal
                        if isinstance(channel, discord.TextChannel):
                            recreated_channel = await guild.create_text_channel(
                                name=channel.name,
                                category=channel.category,
                                position=channel.position,
                                topic=channel.topic,
                                reason=f"🔄 Recriação automática após deletação por {executor}"
                            )
                        elif isinstance(channel, discord.VoiceChannel):
                            recreated_channel = await guild.create_voice_channel(
                                name=channel.name,
                                category=channel.category,
                                position=channel.position,
                                reason=f"🔄 Recriação automática após deletação por {executor}"
                            )
                    except Exception as e:
                        print(f"❌ Erro ao recriar canal: {e}")

                action_text = config['channel_delete_punishment']
                if recreated_channel:
                    action_text += f" + Canal recriado: {recreated_channel.mention}"

                await security_system.log_security_action(
                    guild,
                    "🚨 CANAL DELETADO",
                    f"⚠️ {executor.mention} deletou o canal #{channel.name}",
                    COLORS['danger'],
                    [
                        {'name': '📺 Canal', 'value': f"#{channel.name}", 'inline': True},
                        {'name': '👤 Responsável', 'value': executor.mention, 'inline': True},
                        {'name': '⚡ Ação', 'value': action_text, 'inline': True}
                    ]
                )
                break
    except Exception as e:
        print(f"❌ Erro no detector de exclusão de canais: {e}")

@bot.event
async def on_guild_role_delete(role):
    """🎭 Detecta exclusão de cargos"""
    try:
        guild = role.guild
        config = security_system.get_guild_config(guild.id)

        if not config['protection_enabled']:
            return

        # Salva backup do cargo
        if config['backup_roles']:
            guild_id_str = str(guild.id)
            if guild_id_str not in security_system.backup_data:
                security_system.backup_data[guild_id_str] = {'channels': [], 'roles': []}

            role_backup = {
                'name': role.name,
                'color': str(role.color),
                'permissions': role.permissions.value,
                'position': role.position,
                'deleted_at': datetime.utcnow().isoformat()
            }
            security_system.backup_data[guild_id_str]['roles'].append(role_backup)

        # Tenta pegar log de auditoria o mais rápido possível
        await asyncio.sleep(0.5)

        async for entry in guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
            if entry.target.id == role.id:
                executor = entry.user

                # 👑 OWNER E WHITELIST TÊM PROTEÇÃO TOTAL
                if executor.id == OWNER_ID:
                    return
                elif executor.id in config['whitelist_users']:
                    return

                # Punição IMEDIATA
                punishment = 'ban' # Alterado para BAN conforme solicitado
                action_applied = "Nenhuma"

                try:
                    # Tenta banir o executor IMEDIATAMENTE
                    if executor.id != OWNER_ID and executor.id not in config.get('whitelist_users', []):
                        member = guild.get_member(executor.id)
                        if member:
                            await member.ban(reason=f"🔒 Segurança: Deletou cargo @{role.name}")
                            action_applied = "Banimento Imediato"
                except Exception as e:
                    print(f"Erro ao aplicar punição: {e}")
                    action_applied = f"Erro: {e}"

                # Recria o cargo automaticamente se habilitado
                recreated_role = None
                if config['auto_recreate_roles']:
                    try:
                        recreated_role = await guild.create_role(
                            name=role.name,
                            color=role.color,
                            permissions=role.permissions,
                            hoist=role.hoist,
                            mentionable=role.mentionable,
                            reason=f"🔄 Recriação automática após deletação por {executor}"
                        )
                        # Tenta reposicionar o cargo
                        try:
                            await recreated_role.edit(position=role.position)
                        except:
                            pass
                    except Exception as e:
                        print(f"❌ Erro ao recriar cargo: {e}")

                action_text = punishment
                if recreated_role:
                    action_text += f" + Cargo recriado: {recreated_role.mention}"

                await security_system.log_security_action(
                    guild,
                    "🚨 CARGO DELETADO",
                    f"⚠️ {executor.mention} deletou o cargo @{role.name}",
                    COLORS['danger'],
                    [
                        {'name': '🎭 Cargo', 'value': f"@{role.name}", 'inline': True},
                        {'name': '👤 Responsável', 'value': executor.mention, 'inline': True},
                        {'name': '⚡ Ação', 'value': action_text, 'inline': True}
                    ]
                )
                break
    except Exception as e:
        print(f"❌ Erro no detector de exclusão de cargos: {e}")

@bot.event
async def on_member_ban(guild, user):
    """🔨 Monitora banimentos para detectar atividade suspeita"""
    try:
        config = security_system.get_guild_config(guild.id)
        
        if not config.get('monitor_bot_activity', True):
            return

        await asyncio.sleep(config['audit_log_delay'])

        # Verifica quem fez o banimento
        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
            if entry.target.id == user.id:
                executor = entry.user

                # 🤖 IGNORAR O PRÓPRIO BOT
                if executor.id == bot.user.id:
                    return

                # Registra o banimento no rastreador
                await security_system.track_ban_activity(guild, executor, user)

                # Se for o owner ou whitelist, apenas ignora
                if executor.id == OWNER_ID:
                    return
                elif executor.id in config.get('whitelist_users', []):
                    return

                # Monta campos do embed de forma organizada
                reason_text = entry.reason or "Sem motivo especificado"

                await security_system.log_security_action(
                    guild,
                    "Banimento Registrado",
                    f"Um membro foi banido no servidor.",
                    COLORS['warning'] if executor.bot else COLORS['info'],
                    [
                        {'name': 'Executor do Ban', 'value': f"```{reason_text}```", 'inline': False},
                        {'name': 'Bot Executor', 'value': f"{executor.mention}\n`{executor.name}`\n`ID: {executor.id}`", 'inline': True},
                        {'name': 'Alvo', 'value': f"{user.mention}\n`{user.name}`\n`ID: {user.id}`", 'inline': True},
                    ]
                )
                break

    except Exception as e:
        print(f"❌ Erro no monitoramento de banimentos: {e}")

@bot.event
async def on_member_join(member):
    """🤖 Eventos quando usuário entra"""
    if member.id == bot.user.id:
        return
    guild = member.guild
    config = security_system.get_guild_config(guild.id)

    if not config['protection_enabled']:
        return

    # Ban automático de bots
    if member.bot and config['auto_ban_bots']:
        try:
            await member.ban(reason="🔒 Segurança: Bot banido automaticamente")
            await security_system.log_security_action(
                guild,
                "🤖 Bot Banido",
                f"Bot {member.mention} foi banido automaticamente",
                COLORS['warning']
            )
        except Exception as e:
            print(f"❌ Erro ao banir bot: {e}")
    elif member.bot and not config['auto_ban_bots']:
        await security_system.log_security_action(
            guild,
            "🤖 Bot Entrou no Servidor",
            f"Bot {member.mention} entrou no servidor, pois o bloqueio de bots está liberado por Yevgenny.",
            COLORS['info']
        )

    # Ban de contas muito novas
    if not member.bot and config['auto_ban_new_accounts']:
        account_age = (datetime.utcnow() - member.created_at).days
        if account_age < config['new_account_days']:
            try:
                await member.ban(reason=f"🔒 Segurança: Conta muito nova ({account_age} dias)")
                await security_system.log_security_action(
                    guild,
                    "🆕 Conta Nova Banida",
                    f"Usuário {member.mention} banido (conta com {account_age} dias)",
                    COLORS['warning']
                )
            except Exception as e:
                print(f"❌ Erro ao banir conta nova: {e}")

@bot.event
async def on_message(message):
    """📨 Monitora mensagens para anti-spam e outras proteções"""
    if message.author.id == bot.user.id:
        return

    guild = message.guild
    if not guild:
        await bot.process_commands(message)
        return

    # APENAS help/h/ajuda, status_categoria, savecanais, limpar_historico, teste são comandos públicos/especiais
    public_commands = ['help', 'h', 'ajuda', 'status_categoria', 'savecanais', 'limpar_historico', 'teste']
    
    # 🔒 INTERCEPTA COMANDOS ANTES DA EXECUÇÃO - APENAS OWNER PODE USAR
    if message.content.startswith('!sec_'):
        command_name = message.content.split()[0][5:]  # Remove '!sec_'
        
        # Se NÃO é comando público E NÃO é o owner
        if command_name not in public_commands and message.author.id != OWNER_ID:
            embed = discord.Embed(
                title="🚫 ACESSO NEGADO",
                description=f"❌ **COMANDO RESTRITO:** `!sec_{command_name}`\n\n👑 **APENAS O OWNER PODE USAR COMANDOS!**",
                color=COLORS['danger']
            )
            embed.add_field(
                name="🆔 Verificação",
                value=f"**Owner ID:** `{OWNER_ID}`\n**Seu ID:** `{message.author.id}`\n**Status:** ❌ Não autorizado",
                inline=False
            )
            embed.add_field(
                name="💡 Comando Público",
                value="• `!sec_help` - Central de ajuda",
                inline=False
            )
            embed.set_footer(text=f"Bloqueio de segurança ativo")
            
            await message.reply(embed=embed)
            return  # BLOQUEIA EXECUÇÃO AQUI
    
    config = security_system.get_guild_config(guild.id)
    
    # 🚨 PROTEÇÃO EVERYONE (VERIFICAÇÃO ANTECIPADA)
    if ("@everyone" in message.content or "@here" in message.content):
        # 👑 OWNER E WHITELIST SÃO IMUNES
        if message.author.id != OWNER_ID and message.author.id not in config.get('whitelist_users', []):
            try:
                # Sistema de cooldown para evitar múltiplas mensagens
                user_id_str = str(message.author.id)
                now = datetime.utcnow()
                last_ping = security_system.ping_cooldowns.get(user_id_str)
                
                if last_ping and (now - last_ping).seconds < 30:
                    # Deleta sem logar se já avisou recentemente
                    try:
                        await message.delete()
                    except:
                        pass
                    return

                security_system.ping_cooldowns[user_id_str] = now
                
                # Tenta deletar a mensagem primeiro
                try:
                    await message.delete()
                except:
                    pass
                
                # Aplica o BAN IMEDIATO conforme solicitado
                await message.author.ban(reason="Segurança: Menção proibida (@everyone/@here)")
                
                mockery = "Menção proibida detectada. Infrator removido permanentemente."
                
                await security_system.log_security_action(
                    guild,
                    "AUTO BAN - EVERYONE DETECTADO",
                    f"{message.author.mention} foi banido por marcar everyone/here.\n\n{mockery}",
                    COLORS['danger'],
                    [{'name': 'Usuário', 'value': f"{message.author} ({message.author.id})", 'inline': True}]
                )
                return 
            except Exception as e:
                print(f"Erro ao processar everyone: {e}")

    # 🚨 DETECÇÃO DE COMANDOS DE RAID (.nuke, .raid)
    raid_commands = ['.nuke', '.raid', '.destroy', '.fuck', '.spam']
    if any(cmd in message.content.lower() for cmd in raid_commands):
        if message.author.id != OWNER_ID and message.author.id not in config.get('whitelist_users', []):
            try:
                await message.author.ban(reason=f"🔒 Raid: Tentativa de uso de comando malicioso: {message.content}")
                
                mockery = "Tentou usar comando de raid? Volta pro lobby, noob. 🤡"
                
                await security_system.log_security_action(
                    guild,
                    "🚨 TENTATIVA DE RAID BLOQUEADA",
                    f"⚠️ {message.author.mention} tentou usar um comando de raid e foi banido.\n\n*{mockery}*",
                    COLORS['danger'],
                    [
                        {'name': '👤 Usuário', 'value': f"{message.author} ({message.author.id})", 'inline': True},
                        {'name': '💬 Conteúdo', 'value': message.content, 'inline': False}
                    ]
                )
                return
            except Exception as e:
                print(f"Erro ao banir raider: {e}")

    if not config['protection_enabled']:
        await bot.process_commands(message)
        return

    # Anti-spam
    if config['anti_spam_enabled']:
        user_id = str(message.author.id)
        guild_id = str(guild.id)

        if guild_id not in security_system.spam_tracker:
            security_system.spam_tracker[guild_id] = {}

        if user_id not in security_system.spam_tracker[guild_id]:
            security_system.spam_tracker[guild_id][user_id] = []

        now = datetime.utcnow()
        user_messages = security_system.spam_tracker[guild_id][user_id]

        # Remove mensagens antigas
        user_messages[:] = [msg_time for msg_time in user_messages 
                           if (now - msg_time).seconds < config['spam_time_window']]

        user_messages.append(now)

        if len(user_messages) >= config['spam_message_count']:
            try:
                await message.author.timeout(
                    timedelta(seconds=config['auto_mute_duration']),
                    reason="🔒 Anti-spam: Muitas mensagens em pouco tempo"
                )
                await security_system.log_security_action(
                    guild,
                    "🚫 Usuário Mutado por Spam",
                    f"{message.author.mention} foi mutado por {config['auto_mute_duration']}s",
                    COLORS['warning']
                )
                user_messages.clear()
            except Exception as e:
                print(f"❌ Erro ao mutar por spam: {e}")

    # Anti mass ping
    if config['auto_kick_mass_ping']:
        mention_count = len(message.mentions)
        if mention_count >= config['max_mentions']:
            try:
                await message.delete()
                await message.author.timeout(
                    timedelta(seconds=config['mass_ping_mute_duration']),
                    reason=f"🔒 Mass ping: {mention_count} menções"
                )
                await security_system.log_security_action(
                    guild,
                    "🚫 Usuário Silenciado por Mass Ping",
                    f"{message.author.mention} silenciado por {config['mass_ping_mute_duration']}s ({mention_count} menções)",
                    COLORS['warning']
                )
            except Exception as e:
                print(f"❌ Erro ao silenciar por mass ping: {e}")

    # Anti convite
    if config['auto_delete_invite_links']:
        invite_pattern = r'discord\.gg/\w+'
        if re.search(invite_pattern, message.content):
            try:
                await message.delete()
                await security_system.log_security_action(
                    guild,
                    "🔗 Link de Convite Deletado",
                    f"Mensagem de {message.author.mention} continha convite",
                    COLORS['info']
                )
            except Exception as e:
                print(f"❌ Erro ao deletar convite: {e}")

    await bot.process_commands(message)

# === COMANDOS DO BOT ===

def is_owner():
    """Verificação rigorosa se é o owner do bot"""
    def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

@bot.command(name='config', aliases=['c'])
@is_owner()
async def config_security(ctx, setting: str = None, *, value: str = None):
    """Configura o sistema de segurança"""
    config = security_system.get_guild_config(ctx.guild.id)

    if not setting:
        def bval(v): return "true" if v else "false"
        logs_val = f"<#{config['logs_channel_id']}>" if config['logs_channel_id'] else "não definido"

        embed = discord.Embed(title="Configurações de Segurança", color=COLORS['info'])

        embed.add_field(
            name="Proteção",
            value=(
                f"```\n"
                f"protection_enabled\n  {bval(config['protection_enabled'])}\n\n"
                f"auto_ban_bots\n  {bval(config['auto_ban_bots'])}\n\n"
                f"auto_ban_new_accounts\n  {bval(config['auto_ban_new_accounts'])}\n\n"
                f"new_account_days\n  {config['new_account_days']}\n"
                f"```"
            ),
            inline=True
        )

        embed.add_field(
            name="Anti-Spam / Ping",
            value=(
                f"```\n"
                f"anti_spam_enabled\n  {bval(config['anti_spam_enabled'])}\n\n"
                f"auto_kick_mass_ping\n  {bval(config['auto_kick_mass_ping'])}\n\n"
                f"auto_delete_invite_links\n  {bval(config['auto_delete_invite_links'])}\n\n"
                f"monitor_bot_activity\n  {bval(config['monitor_bot_activity'])}\n"
                f"```"
            ),
            inline=True
        )

        embed.add_field(
            name="Backup / Restauração",
            value=(
                f"```\n"
                f"backup_channels\n  {bval(config['backup_channels'])}\n\n"
                f"auto_recreate_channels\n  {bval(config['auto_recreate_channels'])}\n\n"
                f"auto_recreate_roles\n  {bval(config['auto_recreate_roles'])}\n\n"
                f"bot_protection_enabled\n  {bval(config['bot_protection_enabled'])}\n"
                f"```"
            ),
            inline=True
        )

        embed.add_field(
            name="Limites / Logs",
            value=(
                f"```\n"
                f"auto_ban_mass_banner\n  {bval(config['auto_ban_mass_banner'])}\n\n"
                f"max_bans_per_timeframe\n  {config['max_bans_per_timeframe']}\n\n"
                f"ban_timeframe_minutes\n  {config['ban_timeframe_minutes']}\n\n"
                f"logs_channel_id\n  {logs_val}\n"
                f"```"
            ),
            inline=True
        )

        embed.add_field(
            name="Uso",
            value="`!sec_c <função> <valor>`\n\nExemplos:\n`!sec_c auto_ban_bots true`\n`!sec_c ban_timeframe_minutes 10`",
            inline=False
        )

        await ctx.reply(embed=embed)
        return

    # Aplica configuração
    if setting == 'auto_ban_bots':
        config['auto_ban_bots'] = value.lower() == 'true'
    elif setting == 'auto_ban_new_accounts':
        config['auto_ban_new_accounts'] = value.lower() == 'true'
    elif setting == 'new_account_days':
        config['new_account_days'] = int(value)
    elif setting == 'protection_enabled':
        config['protection_enabled'] = value.lower() == 'true'
    elif setting == 'anti_spam_enabled':
        config['anti_spam_enabled'] = value.lower() == 'true'
    elif setting == 'auto_kick_mass_ping':
        config['auto_kick_mass_ping'] = value.lower() == 'true'
    elif setting == 'auto_delete_invite_links':
        config['auto_delete_invite_links'] = value.lower() == 'true'
    elif setting == 'backup_channels':
        config['backup_channels'] = value.lower() == 'true'
    elif setting == 'backup_roles':
        config['backup_roles'] = value.lower() == 'true'
    elif setting == 'auto_recreate_channels':
        config['auto_recreate_channels'] = value.lower() == 'true'
    elif setting == 'auto_recreate_roles':
        config['auto_recreate_roles'] = value.lower() == 'true'
    elif setting == 'max_mentions':
        config['max_mentions'] = int(value)
    elif setting == 'spam_message_count':
        config['spam_message_count'] = int(value)
    elif setting == 'auto_mute_duration':
        config['auto_mute_duration'] = int(value)
    elif setting == 'mass_ping_mute_duration':
        config['mass_ping_mute_duration'] = int(value)
    elif setting == 'logs_channel_id':
        if value.startswith('#'):
            channel = discord.utils.get(ctx.guild.channels, name=value[1:])
        else:
            channel = ctx.guild.get_channel(int(value.strip('<#>')))
        config['logs_channel_id'] = channel.id if channel else None
    elif setting == 'monitor_bot_activity':
        config['monitor_bot_activity'] = value.lower() == 'true'
    elif setting == 'auto_ban_mass_banner':
        config['auto_ban_mass_banner'] = value.lower() == 'true'
    elif setting == 'bot_protection_enabled':
        config['bot_protection_enabled'] = value.lower() == 'true'
    elif setting == 'max_bans_per_timeframe':
        config['max_bans_per_timeframe'] = int(value)
    elif setting == 'ban_timeframe_minutes':
        config['ban_timeframe_minutes'] = int(value)
    else:
        await ctx.reply("❌ Configuração inválida!")
        return

    await security_system.save_data()

    embed = discord.Embed(
        title="✅ Configuração Atualizada",
        description=f"**{setting}** = **{value}**",
        color=COLORS['success']
    )
    await ctx.reply(embed=embed)

@bot.command(name='whitelist', aliases=['w'])
@is_owner()
async def manage_whitelist(ctx, action: str = None, user: discord.Member = None):
    """Gerencia whitelist"""
    config = security_system.get_guild_config(ctx.guild.id)

    if not action:
        embed = discord.Embed(title="🔐 Whitelist de Segurança", color=COLORS['info'])

        if config['whitelist_users']:
            users = []
            for user_id in config['whitelist_users']:
                user_obj = bot.get_user(user_id)
                users.append(user_obj.mention if user_obj else f"ID: {user_id}")
            embed.add_field(name="👥 Usuários", value='\n'.join(users), inline=False)
        else:
            embed.add_field(name="👥 Usuários", value="Nenhum usuário na whitelist", inline=False)

        embed.add_field(name="💡 Uso", value="`!sec_w add @user`\n`!sec_w remove @user`", inline=False)
        await ctx.reply(embed=embed)
        return

    if not user:
        await ctx.reply("❌ Mencione um usuário!")
        return

    if action == 'add':
        if user.id not in config['whitelist_users']:
            config['whitelist_users'].append(user.id)
            await security_system.save_data()
            await ctx.reply(f"✅ {user.mention} adicionado à whitelist!")
        else:
            await ctx.reply("❌ Usuário já está na whitelist!")

    elif action == 'remove':
        if user.id in config['whitelist_users']:
            config['whitelist_users'].remove(user.id)
            await security_system.save_data()
            await ctx.reply(f"✅ {user.mention} removido da whitelist!")
        else:
            await ctx.reply("❌ Usuário não está na whitelist!")

@bot.command(name='teste')
@is_owner()
async def test_protection(ctx):
    """Comando de teste: Cria 15 canais e deleta após 60s"""
    await ctx.send("🧪 **Iniciando teste de criação de canais...**\nCriando 15 canais temporários.")
    
    created_channels = []
    for i in range(1, 16):
        try:
            channel = await ctx.guild.create_text_channel(name=f"teste-raid-{i}")
            created_channels.append(channel)
            await asyncio.sleep(0.1) # Pequeno intervalo para não travar
        except Exception as e:
            print(f"Erro ao criar canal de teste {i}: {e}")

    await ctx.send(f"✅ **{len(created_channels)} canais criados.**\nEles serão deletados automaticamente em 60 segundos.")
    
    await asyncio.sleep(60)
    
    for channel in created_channels:
        try:
            await channel.delete(reason="Fim do teste de segurança")
        except:
            pass
    
    await ctx.send("🧹 **Teste concluído.** Canais temporários removidos.")

@bot.command(name='restore', aliases=['r'])
@is_owner()
async def restore_roles(ctx, user: discord.Member):
    """Restaura cargos de um usuário"""
    user_id = str(user.id)

    if user_id not in security_system.restored_roles:
        await ctx.reply("❌ Usuário não tem cargos para restaurar!")
        return

    try:
        user_data = security_system.restored_roles[user_id]
        roles_to_restore = []

        for role_id in user_data['roles']:
            role = ctx.guild.get_role(role_id)
            if role:
                roles_to_restore.append(role)

        if roles_to_restore:
            await user.add_roles(*roles_to_restore, reason=f"Restauração por {ctx.author}")
            del security_system.restored_roles[user_id]
            await security_system.save_data()

            await ctx.reply(f"✅ Cargos de {user.mention} restaurados!")
        else:
            await ctx.reply("❌ Nenhum cargo válido para restaurar!")

    except Exception as e:
        await ctx.reply(f"❌ Erro: {e}")

@bot.command(name='status', aliases=['s'])
@is_owner()
async def security_status(ctx):
    """Status do sistema"""
    config = security_system.get_guild_config(ctx.guild.id)

    embed = discord.Embed(title="🔒 Status do Sistema", color=COLORS['info'])

    # Status geral
    guild_id_str = str(ctx.guild.id)
    logs_count = len(security_system.security_logs.get(guild_id_str, []))
    pending_restores = len([r for r in security_system.restored_roles.values() 
                           if r['guild_id'] == ctx.guild.id])

    embed.add_field(name="🟢 Sistema", value="Operacional", inline=True)
    embed.add_field(name="📊 Logs", value=logs_count, inline=True)
    embed.add_field(name="🔄 Restaurações", value=pending_restores, inline=True)

    # Proteções ativas
    protections = []
    if config['protection_enabled']:
        protections.append("🛡️ Proteção geral ativa")
        if config['auto_ban_bots']:
            protections.append("🤖 Anti-bot")
        if config['anti_spam_enabled']:
            protections.append("📢 Anti-spam")
        if config['auto_kick_mass_ping']:
            protections.append("🚫 Anti mass-ping")
    else:
        protections.append("❌ Proteções desativadas")

    embed.add_field(name="🛡️ Proteções", value='\n'.join(protections), inline=False)

    # Canal de logs
    logs_channel = "Não configurado"
    if config['logs_channel_id']:
        logs_channel = f"<#{config['logs_channel_id']}>"
    embed.add_field(name="📺 Canal de Logs", value=logs_channel, inline=True)

    await ctx.reply(embed=embed)

@bot.command(name='logs', aliases=['l'])
@is_owner()
async def view_logs(ctx, limit: int = 10):
    """Visualiza logs recentes"""
    guild_id_str = str(ctx.guild.id)
    logs = security_system.security_logs.get(guild_id_str, [])

    if not logs:
        await ctx.reply("❌ Nenhum log encontrado!")
        return

    embed = discord.Embed(title="📋 Logs Recentes", color=COLORS['info'])

    recent_logs = logs[-limit:]
    for log in recent_logs:
        timestamp = datetime.fromisoformat(log['timestamp']).strftime("%d/%m %H:%M")
        embed.add_field(
            name=f"🕐 {timestamp}",
            value=f"**{log['title']}**\n{log['description'][:100]}...",
            inline=False
        )

    await ctx.reply(embed=embed)

@bot.command(name='backup', aliases=['b'])
@is_owner()
async def view_backups(ctx):
    """Visualiza backups de canais/cargos deletados"""
    guild_id_str = str(ctx.guild.id)
    backups = security_system.backup_data.get(guild_id_str, {'channels': [], 'roles': [], 'full_backups': []})

    embed = discord.Embed(title="💾 Backups Disponíveis", color=COLORS['info'])

    # Backups completos
    if backups.get('full_backups'):
        full_backups_text = []
        total_backups = len(backups['full_backups'])
        for i, backup in enumerate(backups['full_backups'][-5:], 1):  # Últimos 5
            created_date = datetime.fromisoformat(backup['created_at']).strftime("%d/%m %H:%M")
            backup_id = backup.get('backup_id', 'N/A')
            channels_count = len(backup.get('channels', []))
            roles_count = len(backup.get('roles', []))
            version = backup.get('backup_version', '1.0')
            full_backups_text.append(f"🆔 `{backup_id}` - {created_date}\n   📊 {channels_count} canais, {roles_count} cargos (v{version})")
        
        embed.add_field(
            name=f"🏰 Backups Completos ({total_backups} total)", 
            value='\n'.join(full_backups_text) if full_backups_text else "Nenhum backup completo", 
            inline=False
        )

    # Canais deletados
    if backups['channels']:
        channels_text = []
        for channel in backups['channels'][-5:]:  # Últimos 5
            deleted_date = datetime.fromisoformat(channel['deleted_at']).strftime("%d/%m")
            channels_text.append(f"#{channel['name']} ({deleted_date})")
        embed.add_field(name="📺 Canais Deletados", value='\n'.join(channels_text), inline=True)

    # Cargos deletados
    if backups['roles']:
        roles_text = []
        for role in backups['roles'][-5:]:  # Últimos 5
            deleted_date = datetime.fromisoformat(role['deleted_at']).strftime("%d/%m")
            roles_text.append(f"@{role['name']} ({deleted_date})")
        embed.add_field(name="🎭 Cargos Deletados", value='\n'.join(roles_text), inline=True)

    if not backups['channels'] and not backups['roles'] and not backups.get('full_backups'):
        embed.add_field(name="💾 Status", value="Nenhum backup disponível", inline=False)
    
    # Informações do arquivo
    import os
    if os.path.exists(SECURITY_DATA_FILE):
        file_size = os.path.getsize(SECURITY_DATA_FILE)
        file_size_mb = file_size / (1024 * 1024)
        embed.add_field(
            name="📁 Arquivo de Dados", 
            value=f"📄 `{SECURITY_DATA_FILE}`\n💾 Tamanho: {file_size_mb:.2f} MB\n✅ Status: Acessível", 
            inline=True
        )
    else:
        embed.add_field(
            name="📁 Arquivo de Dados", 
            value=f"📄 `{SECURITY_DATA_FILE}`\n❌ Status: Não encontrado", 
            inline=True
        )
        
    embed.add_field(name="💡 Comandos", value="`!sec_save` - Criar backup completo\n`!sec_restore <ID>` - Restaurar backup\n`!sec_verify_backup <ID>` - Verificar backup", inline=False)

    await ctx.reply(embed=embed)

@bot.command(name='restore_backup', aliases=['restaurar'])
@is_owner()
async def restore_backup(ctx, backup_id: str = None):
    """🔥 Restaura um backup completo usando o ID com 5 confirmações"""
    if not backup_id:
        embed = discord.Embed(
            title="❌ ID Necessário",
            description="Use: `!sec_restore <ID_do_backup>`\n\nPara ver backups disponíveis: `!sec_b`",
            color=COLORS['danger']
        )
        await ctx.reply(embed=embed)
        return
        
    try:
        guild_id_str = str(ctx.guild.id)
        backups = security_system.backup_data.get(guild_id_str, {}).get('full_backups', [])
        
        # Procura backup pelo ID
        target_backup = None
        for backup in backups:
            if backup.get('backup_id', '').upper() == backup_id.upper():
                target_backup = backup
                break
                
        if not target_backup:
            embed = discord.Embed(
                title="❌ Backup Não Encontrado",
                description=f"Backup com ID `{backup_id}` não foi encontrado.\n\nUse `!sec_b` para ver backups disponíveis.",
                color=COLORS['danger']
            )
            await ctx.reply(embed=embed)
            return

        # Sistema de confirmação múltipla (5 vezes)
        confirmations = [
            "⚠️ **CONFIRMAÇÃO 1/5** - Você deseja restaurar este backup?",
            "🔄 **CONFIRMAÇÃO 2/5** - Tem certeza que deseja restaurar? ISSO IRÁ RECRIAR TUDO!",
            "🔍 **CONFIRMAÇÃO 3/5** - Confirme novamente a restauração do backup:",
            "⚡ **CONFIRMAÇÃO 4/5** - Última chance para cancelar a restauração:",
            "🚨 **CONFIRMAÇÃO 5/5** - CONFIRMAÇÃO FINAL - Restaurar backup agora?"
        ]
        
        for i, confirmation_text in enumerate(confirmations, 1):
            # Informações do backup
            backup_info = f"\n\n🆔 **ID:** `{target_backup['backup_id']}`\n🏰 **Servidor:** {target_backup['server_name']}\n📅 **Criado em:** {datetime.fromisoformat(target_backup['created_at']).strftime('%d/%m/%Y %H:%M')}\n📊 **Dados:** {len(target_backup['channels'])} canais, {len(target_backup['roles'])} cargos"
            
            embed = discord.Embed(
                title=f"🔄 RESTAURAÇÃO DE BACKUP - ETAPA {i}/5",
                description=f"{confirmation_text}{backup_info}",
                color=COLORS['warning']
            )
            embed.add_field(name="✅ Confirmar", value="Reaja com ✅", inline=True)
            embed.add_field(name="❌ Cancelar", value="Reaja com ❌", inline=True)
            embed.add_field(name="⏰ Tempo limite", value="45 segundos", inline=True)
            
            if i == 5:
                embed.add_field(name="🚨 ATENÇÃO", value="**ESTA É A CONFIRMAÇÃO FINAL!**\n🔴 Todos os canais e cargos serão recriados!", inline=False)
            
            confirm_msg = await ctx.reply(embed=embed)
            await confirm_msg.add_reaction('✅')
            await confirm_msg.add_reaction('❌')
            
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == confirm_msg.id
            
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=45.0, check=check)
                
                if str(reaction.emoji) == '❌':
                    cancel_embed = discord.Embed(
                        title="❌ RESTAURAÇÃO CANCELADA",
                        description=f"Restauração do backup `{backup_id}` foi cancelada na etapa {i}/5.",
                        color=COLORS['danger']
                    )
                    await confirm_msg.edit(embed=cancel_embed)
                    return
                    
            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(
                    title="⏰ TEMPO ESGOTADO",
                    description=f"Restauração do backup `{backup_id}` cancelada por tempo limite na etapa {i}/5.",
                    color=COLORS['warning']
                )
                await confirm_msg.edit(embed=timeout_embed)
                return
            
            # Confirma cada etapa
            success_step = discord.Embed(
                title=f"✅ ETAPA {i}/5 CONFIRMADA",
                description=f"Confirmação {i} aceita. {'Aguarde próxima etapa...' if i < 5 else 'Todas as confirmações aceitas! Iniciando restauração...'}",
                color=COLORS['success']
            )
            await confirm_msg.edit(embed=success_step)
            
            # Pequena pausa entre confirmações
            if i < 5:
                await asyncio.sleep(3)

        # Inicia restauração
        progress_embed = discord.Embed(
            title="🔄 RESTAURANDO BACKUP",
            description="⚠️ **NÃO INTERROMPA O PROCESSO**\n\n🔄 Iniciando restauração...",
            color=COLORS['warning']
        )
        await confirm_msg.edit(embed=progress_embed)
        
        restored_count = {'categories': 0, 'channels': 0, 'roles': 0}
        
        # Restaura categorias
        progress_embed.description = "🔄 **Criando categorias...**"
        await confirm_msg.edit(embed=progress_embed)
        
        for category_data in target_backup.get('categories', []):
            try:
                await ctx.guild.create_category(
                    name=category_data['name'],
                    reason=f"Restauração do backup {backup_id}"
                )
                restored_count['categories'] += 1
            except Exception as e:
                print(f"Erro ao criar categoria {category_data['name']}: {e}")
        
        # Restaura canais
        progress_embed.description = f"🔄 **Criando canais...** ({len(target_backup['channels'])} para processar)"
        await confirm_msg.edit(embed=progress_embed)
        
        for channel_data in target_backup['channels']:
            try:
                category = None
                if channel_data.get('category'):
                    category = discord.utils.get(ctx.guild.categories, name=channel_data['category'])
                
                if channel_data['type'] == 'text':
                    await ctx.guild.create_text_channel(
                        name=channel_data['name'],
                        category=category,
                        topic=channel_data.get('topic'),
                        slowmode_delay=channel_data.get('slowmode_delay', 0),
                        nsfw=channel_data.get('nsfw', False),
                        reason=f"Restauração do backup {backup_id}"
                    )
                elif channel_data['type'] == 'voice':
                    await ctx.guild.create_voice_channel(
                        name=channel_data['name'],
                        category=category,
                        bitrate=channel_data.get('bitrate', 64000),
                        user_limit=channel_data.get('user_limit', 0),
                        reason=f"Restauração do backup {backup_id}"
                    )
                    
                restored_count['channels'] += 1
                
            except Exception as e:
                print(f"Erro ao criar canal {channel_data['name']}: {e}")
        
        # Restaura cargos
        progress_embed.description = f"🔄 **Criando cargos...** ({len(target_backup['roles'])} para processar)"
        await confirm_msg.edit(embed=progress_embed)
        
        for role_data in target_backup['roles']:
            try:
                permissions = discord.Permissions(role_data['permissions'])
                color = discord.Color(int(role_data['color'].replace('#', ''), 16)) if role_data['color'] != '#000000' else discord.Color.default()
                
                await ctx.guild.create_role(
                    name=role_data['name'],
                    permissions=permissions,
                    color=color,
                    hoist=role_data.get('hoist', False),
                    mentionable=role_data.get('mentionable', True),
                    reason=f"Restauração do backup {backup_id}"
                )
                restored_count['roles'] += 1
                
            except Exception as e:
                print(f"Erro ao criar cargo {role_data['name']}: {e}")

        # Sucesso
        success_embed = discord.Embed(
            title="✅ BACKUP RESTAURADO COM SUCESSO",
            description=f"🎉 **Restauração concluída!**\n\n🆔 **Backup ID:** `{backup_id}`",
            color=COLORS['success'],
            timestamp=datetime.utcnow()
        )
        
        success_embed.add_field(
            name="📊 Itens Restaurados",
            value=f"📁 **Categorias:** {restored_count['categories']}\n📺 **Canais:** {restored_count['channels']}\n🎭 **Cargos:** {restored_count['roles']}",
            inline=True
        )
        
        success_embed.add_field(
            name="ℹ️ Informações",
            value=f"🏰 **Servidor Original:** {target_backup['server_name']}\n📅 **Backup de:** {datetime.fromisoformat(target_backup['created_at']).strftime('%d/%m/%Y')}\n👤 **Restaurado por:** {ctx.author.mention}",
            inline=True
        )
        
        success_embed.set_footer(text="Sistema de Segurança - Restauração Completa")
        
        await confirm_msg.edit(embed=success_embed)
        
        # Log da restauração
        await security_system.log_security_action(
            ctx.guild,
            "🔄 BACKUP RESTAURADO",
            f"Backup `{backup_id}` restaurado por {ctx.author.mention}",
            COLORS['success'],
            [
                {'name': '🆔 ID', 'value': backup_id, 'inline': True},
                {'name': '📊 Restaurados', 'value': f"{restored_count['channels']} canais, {restored_count['roles']} cargos", 'inline': True}
            ]
        )

    except Exception as e:
        error_embed = discord.Embed(
            title="❌ ERRO NA RESTAURAÇÃO",
            description=f"Falha ao restaurar backup: {str(e)}",
            color=COLORS['danger']
        )
        await ctx.reply(embed=error_embed)

@bot.command(name='bans', aliases=['banimentos'])
@is_owner()
async def view_ban_activity(ctx, limite: int = 10):
    """Visualiza atividade de banimentos recentes"""
    guild_id_str = str(ctx.guild.id)
    ban_data = security_system.ban_tracker.get(guild_id_str, {})

    embed = discord.Embed(title="🔨 Atividade de Banimentos", color=COLORS['info'])

    if not ban_data:
        embed.add_field(name="📊 Status", value="Nenhuma atividade de banimento registrada", inline=False)
        await ctx.reply(embed=embed)
        return

    # Mostra usuários/bots com mais banimentos
    activity_summary = []
    for user_id, bans in ban_data.items():
        if bans:  # Se tem banimentos recentes
            user = bot.get_user(int(user_id))
            user_name = user.display_name if user else f"ID: {user_id}"
            is_bot = any(ban.get('is_bot', False) for ban in bans[:1]) if bans else False
            bot_icon = "🤖" if is_bot else "👤"
            
            activity_summary.append({
                'name': f"{bot_icon} {user_name}",
                'count': len(bans),
                'recent': bans[-1]['timestamp'] if bans else None
            })

    # Ordena por quantidade de banimentos
    activity_summary.sort(key=lambda x: x['count'], reverse=True)

    if activity_summary:
        summary_text = []
        for item in activity_summary[:limite]:
            recent_time = datetime.fromisoformat(item['recent']).strftime("%d/%m %H:%M") if item['recent'] else "N/A"
            summary_text.append(f"{item['name']}: {item['count']} banimentos (último: {recent_time})")
        
        embed.add_field(
            name="📊 Atividade Recente",
            value='\n'.join(summary_text),
            inline=False
        )

        # Configurações atuais
        config = security_system.get_guild_config(ctx.guild.id)
        embed.add_field(
            name="⚙️ Configurações",
            value=f"Máximo: {config['max_bans_per_timeframe']} banimentos\nTempo: {config['ban_timeframe_minutes']} minutos\nAuto-ban: {'✅' if config['auto_ban_mass_banner'] else '❌'}",
            inline=True
        )
    else:
        embed.add_field(name="📊 Status", value="Nenhuma atividade recente", inline=False)

    await ctx.reply(embed=embed)

@bot.command(name='warn', aliases=['av'])
@is_owner()
async def warn_user(ctx, user: discord.Member, *, reason: str = "Sem motivo especificado"):
    """Aplica aviso a um usuário"""
    # 🔒 VERIFICAÇÃO DUPLA DE SEGURANÇA
    if ctx.author.id != OWNER_ID:
        await ctx.reply("🚫 Acesso negado! Apenas o owner pode usar este comando.")
        return
        
    # 👑 OWNER DO BOT É INTOCÁVEL - PROTEÇÃO ABSOLUTA
    if user.id == OWNER_ID:
        embed = discord.Embed(
            title="👑 PROTEÇÃO DO OWNER",
            description="❌ **O OWNER DO BOT É COMPLETAMENTE INTOCÁVEL!**\n🛡️ Nenhum comando pode afetar o dono do bot por segurança.",
            color=COLORS['danger']
        )
        await ctx.reply(embed=embed)
        return
    user_id = str(user.id)
    guild_id = str(ctx.guild.id)

    if guild_id not in security_system.user_warnings:
        security_system.user_warnings[guild_id] = {}

    if user_id not in security_system.user_warnings[guild_id]:
        security_system.user_warnings[guild_id][user_id] = []

    warning = {
        'reason': reason,
        'moderator': ctx.author.id,
        'timestamp': datetime.utcnow().isoformat()
    }

    security_system.user_warnings[guild_id][user_id].append(warning)
    await security_system.save_data()

    warnings_count = len(security_system.user_warnings[guild_id][user_id])

    embed = discord.Embed(
        title="⚠️ Aviso Aplicado",
        description=f"{user.mention} recebeu um aviso",
        color=COLORS['warning']
    )
    embed.add_field(name="📝 Motivo", value=reason, inline=False)
    embed.add_field(name="📊 Total de Avisos", value=warnings_count, inline=True)
    embed.add_field(name="👮 Moderador", value=ctx.author.mention, inline=True)

    await ctx.reply(embed=embed)

    await security_system.log_security_action(
        ctx.guild,
        "⚠️ Aviso Aplicado",
        f"{user.mention} recebeu aviso de {ctx.author.mention}",
        COLORS['warning'],
        [
            {'name': '📝 Motivo', 'value': reason, 'inline': False},
            {'name': '📊 Total', 'value': warnings_count, 'inline': True}
        ]
    )

@bot.command(name='warnings', aliases=['avisos'])
@is_owner()
async def view_warnings(ctx, user: discord.Member = None):
    """Visualiza avisos de um usuário"""
    if not user:
        user = ctx.author

    user_id = str(user.id)
    guild_id = str(ctx.guild.id)

    warnings = security_system.user_warnings.get(guild_id, {}).get(user_id, [])

    if not warnings:
        await ctx.reply(f"✅ {user.mention} não possui avisos!")
        return

    embed = discord.Embed(
        title=f"⚠️ Avisos de {user.display_name}",
        color=COLORS['warning']
    )

    for i, warning in enumerate(warnings[-10:], 1):  # Últimos 10
        timestamp = datetime.fromisoformat(warning['timestamp']).strftime("%d/%m %H:%M")
        moderator = bot.get_user(warning['moderator'])
        mod_name = moderator.mention if moderator else "Desconhecido"

        embed.add_field(
            name=f"Aviso #{i}",
            value=f"**Motivo:** {warning['reason']}\n**Moderador:** {mod_name}\n**Data:** {timestamp}",
            inline=False
        )

    embed.add_field(name="📊 Total", value=len(warnings), inline=True)

    await ctx.reply(embed=embed)

@bot.command(name='clear_warnings', aliases=['limpar_avisos'])
@is_owner()
async def clear_warnings(ctx, user: discord.Member):
    """Limpa avisos de um usuário"""
    user_id = str(user.id)
    guild_id = str(ctx.guild.id)

    if guild_id in security_system.user_warnings and user_id in security_system.user_warnings[guild_id]:
        warnings_count = len(security_system.user_warnings[guild_id][user_id])
        del security_system.user_warnings[guild_id][user_id]
        await security_system.save_data()

        await ctx.reply(f"✅ {warnings_count} avisos de {user.mention} foram limpos!")
    else:
        await ctx.reply(f"❌ {user.mention} não possui avisos para limpar!")

@bot.command(name='mute', aliases=['m'])
@is_owner()
async def mute_user(ctx, user: discord.Member, duration: int = 300, *, reason: str = "Sem motivo"):
    """Muta um usuário temporariamente"""
    # 🔒 VERIFICAÇÃO DUPLA DE SEGURANÇA
    if ctx.author.id != OWNER_ID:
        await ctx.reply("🚫 Acesso negado! Apenas o owner pode usar este comando.")
        return
        
    # 👑 OWNER DO BOT É INTOCÁVEL - PROTEÇÃO ABSOLUTA
    if user.id == OWNER_ID:
        embed = discord.Embed(
            title="👑 PROTEÇÃO DO OWNER",
            description="❌ **O OWNER DO BOT É COMPLETAMENTE INTOCÁVEL!**\n🛡️ Nenhum comando pode afetar o dono do bot por segurança.",
            color=COLORS['danger']
        )
        await ctx.reply(embed=embed)
        return
        
    try:
        await user.timeout(
            timedelta(seconds=duration),
            reason=f"🔒 Mutado por {ctx.author}: {reason}"
        )

        embed = discord.Embed(
            title="🔇 Usuário Mutado",
            description=f"{user.mention} foi mutado por {duration} segundos",
            color=COLORS['warning']
        )
        embed.add_field(name="📝 Motivo", value=reason, inline=False)
        embed.add_field(name="⏱️ Duração", value=f"{duration} segundos", inline=True)
        embed.add_field(name="👮 Moderador", value=ctx.author.mention, inline=True)

        await ctx.reply(embed=embed)

        await security_system.log_security_action(
            ctx.guild,
            "🔇 Usuário Mutado",
            f"{user.mention} mutado por {ctx.author.mention}",
            COLORS['warning'],
            [
                {'name': '📝 Motivo', 'value': reason, 'inline': False},
                {'name': '⏱️ Duração', 'value': f"{duration}s", 'inline': True}
            ]
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao mutar usuário: {e}")

@bot.command(name='unmute', aliases=['desmutar'])
@is_owner()
async def unmute_user(ctx, user: discord.Member):
    """Desmuta um usuário"""
    try:
        await user.timeout(None, reason=f"Desmutado por {ctx.author}")
        await ctx.reply(f"✅ {user.mention} foi desmutado!")

        await security_system.log_security_action(
            ctx.guild,
            "🔊 Usuário Desmutado",
            f"{user.mention} desmutado por {ctx.author.mention}",
            COLORS['success']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao desmutar usuário: {e}")

@bot.command(name='banir', aliases=['ban'])
@is_owner()
async def ban_user(ctx, user: discord.Member, *, motivo: str = "Sem motivo especificado"):
    """Bane um usuário do servidor"""
    # 🔒 VERIFICAÇÃO DUPLA DE SEGURANÇA
    if ctx.author.id != OWNER_ID:
        await ctx.reply("🚫 Acesso negado! Apenas o owner pode usar este comando.")
        return
        
    # 👑 OWNER DO BOT É INTOCÁVEL - PROTEÇÃO ABSOLUTA
    if user.id == OWNER_ID:
        embed = discord.Embed(
            title="👑 PROTEÇÃO DO OWNER",
            description="❌ **O OWNER DO BOT É COMPLETAMENTE INTOCÁVEL!**\n🛡️ Nenhum comando pode afetar o dono do bot por segurança.",
            color=COLORS['danger']
        )
        await ctx.reply(embed=embed)
        return
        
    try:
        await user.ban(reason=f"🔒 Banido por {ctx.author}: {motivo}")

        embed = discord.Embed(
            title="🔨 Usuário Banido",
            description=f"{user.mention} foi banido do servidor",
            color=COLORS['danger']
        )
        embed.add_field(name="📝 Motivo", value=motivo, inline=False)
        embed.add_field(name="👮 Moderador", value=ctx.author.mention, inline=True)

        await ctx.reply(embed=embed)

        await security_system.log_security_action(
            ctx.guild,
            "🔨 Usuário Banido",
            f"{user.mention} banido por {ctx.author.mention}",
            COLORS['danger'],
            [{'name': '📝 Motivo', 'value': motivo, 'inline': False}]
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao banir usuário: {e}")

@bot.command(name='expulsar', aliases=['kick'])
@is_owner()
async def kick_user(ctx, user: discord.Member, *, motivo: str = "Sem motivo especificado"):
    """Expulsa um usuário do servidor"""
    # 🔒 VERIFICAÇÃO DUPLA DE SEGURANÇA
    if ctx.author.id != OWNER_ID:
        await ctx.reply("🚫 Acesso negado! Apenas o owner pode usar este comando.")
        return
        
    # 👑 OWNER DO BOT É INTOCÁVEL - PROTEÇÃO ABSOLUTA
    if user.id == OWNER_ID:
        embed = discord.Embed(
            title="👑 PROTEÇÃO DO OWNER",
            description="❌ **O OWNER DO BOT É COMPLETAMENTE INTOCÁVEL!**\n🛡️ Nenhum comando pode afetar o dono do bot por segurança.",
            color=COLORS['danger']
        )
        await ctx.reply(embed=embed)
        return
        
    try:
        await user.kick(reason=f"🔒 Expulso por {ctx.author}: {motivo}")

        embed = discord.Embed(
            title="👢 Usuário Expulso",
            description=f"{user.mention} foi expulso do servidor",
            color=COLORS['warning']
        )
        embed.add_field(name="📝 Motivo", value=motivo, inline=False)
        embed.add_field(name="👮 Moderador", value=ctx.author.mention, inline=True)

        await ctx.reply(embed=embed)

        await security_system.log_security_action(
            ctx.guild,
            "👢 Usuário Expulso",
            f"{user.mention} expulso por {ctx.author.mention}",
            COLORS['warning'],
            [{'name': '📝 Motivo', 'value': motivo, 'inline': False}]
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao expulsar usuário: {e}")

@bot.command(name='limpar', aliases=['clear', 'purge'])
@is_owner()
async def clear_messages(ctx, quantidade: int = 10):
    """Limpa mensagens do canal"""
    if quantidade > 100:
        await ctx.reply("❌ Máximo de 100 mensagens por vez!")
        return

    try:
        deleted = await ctx.channel.purge(limit=quantidade + 1)

        embed = discord.Embed(
            title="🧹 Mensagens Limpas",
            description=f"{len(deleted) - 1} mensagens foram deletadas",
            color=COLORS['success']
        )
        embed.add_field(name="👮 Moderador", value=ctx.author.mention, inline=True)
        embed.add_field(name="📺 Canal", value=ctx.channel.mention, inline=True)

        msg = await ctx.reply(embed=embed)
        await asyncio.sleep(3)
        await msg.delete()

        await security_system.log_security_action(
            ctx.guild,
            "🧹 Mensagens Limpas",
            f"{len(deleted) - 1} mensagens deletadas por {ctx.author.mention}",
            COLORS['info']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao limpar mensagens: {e}")

@bot.command(name='slowmode', aliases=['slow'])
@is_owner()
async def set_slowmode(ctx, segundos: int = 0):
    """Define modo lento no canal"""
    try:
        await ctx.channel.edit(slowmode_delay=segundos)

        if segundos == 0:
            await ctx.reply("✅ Modo lento desativado!")
        else:
            await ctx.reply(f"⏱️ Modo lento ativado: {segundos} segundos")

        await security_system.log_security_action(
            ctx.guild,
            "⏱️ Modo Lento Alterado",
            f"Slowmode definido para {segundos}s por {ctx.author.mention}",
            COLORS['info']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao definir modo lento: {e}")

@bot.command(name='bloquear', aliases=['lock'])
@is_owner()
async def lock_channel(ctx):
    """Bloqueia o canal para @everyone"""
    try:
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

        embed = discord.Embed(
            title="🔒 Canal Bloqueado",
            description="Canal bloqueado para @everyone",
            color=COLORS['warning']
        )
        await ctx.reply(embed=embed)

        await security_system.log_security_action(
            ctx.guild,
            "🔒 Canal Bloqueado",
            f"Canal {ctx.channel.mention} bloqueado por {ctx.author.mention}",
            COLORS['warning']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao bloquear canal: {e}")

@bot.command(name='desbloquear', aliases=['unlock'])
@is_owner()
async def unlock_channel(ctx):
    """Desbloqueia o canal para @everyone"""
    try:
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = True
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

        embed = discord.Embed(
            title="🔓 Canal Desbloqueado",
            description="Canal desbloqueado para @everyone",
            color=COLORS['success']
        )
        await ctx.reply(embed=embed)

        await security_system.log_security_action(
            ctx.guild,
            "🔓 Canal Desbloqueado",
            f"Canal {ctx.channel.mention} desbloqueado por {ctx.author.mention}",
            COLORS['success']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao desbloquear canal: {e}")

@bot.command(name='info', aliases=['userinfo'])
@is_owner()
async def user_info(ctx, user: discord.Member = None):
    """Mostra informações de um usuário"""
    if not user:
        user = ctx.author

    created_at = user.created_at.strftime("%d/%m/%Y %H:%M")
    joined_at = user.joined_at.strftime("%d/%m/%Y %H:%M") if user.joined_at else "Desconhecido"

    embed = discord.Embed(
        title=f"👤 Informações de {user.display_name}",
        color=COLORS['info']
    )
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)

    embed.add_field(name="🆔 ID", value=user.id, inline=True)
    embed.add_field(name="📅 Conta criada", value=created_at, inline=True)
    embed.add_field(name="📥 Entrou em", value=joined_at, inline=True)
    embed.add_field(name="🤖 Bot", value="Sim" if user.bot else "Não", inline=True)
    embed.add_field(name="🎭 Cargos", value=len(user.roles) - 1, inline=True)
    embed.add_field(name="🔝 Maior cargo", value=user.top_role.mention, inline=True)

    await ctx.reply(embed=embed)

@bot.command(name='roleinfo', aliases=['cargoinfo'])
@is_owner()
async def role_info(ctx, *, nome_cargo: str):
    """Mostra informações de um cargo"""
    role = discord.utils.get(ctx.guild.roles, name=nome_cargo)

    if not role:
        await ctx.reply("❌ Cargo não encontrado!")
        return

    created_at = role.created_at.strftime("%d/%m/%Y %H:%M")

    embed = discord.Embed(
        title=f"🎭 Informações do Cargo @{role.name}",
        color=role.color
    )

    embed.add_field(name="🆔 ID", value=role.id, inline=True)
    embed.add_field(name="📅 Criado em", value=created_at, inline=True)
    embed.add_field(name="👥 Membros", value=len(role.members), inline=True)
    embed.add_field(name="📍 Posição", value=role.position, inline=True)
    embed.add_field(name="🎨 Cor", value=str(role.color), inline=True)
    embed.add_field(name="🔗 Mencionável", value="Sim" if role.mentionable else "Não", inline=True)

    await ctx.reply(embed=embed)

@bot.command(name='serverinfo', aliases=['servidor'])
@is_owner()
async def server_info(ctx):
    """Mostra informações do servidor"""
    guild = ctx.guild
    created_at = guild.created_at.strftime("%d/%m/%Y %H:%M")

    embed = discord.Embed(
        title=f"🏰 Informações do Servidor",
        color=COLORS['info']
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(name="📛 Nome", value=guild.name, inline=True)
    embed.add_field(name="🆔 ID", value=guild.id, inline=True)
    embed.add_field(name="👑 Dono", value=guild.owner.mention if guild.owner else "Desconhecido", inline=True)
    embed.add_field(name="👥 Membros", value=guild.member_count, inline=True)
    embed.add_field(name="📺 Canais", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Cargos", value=len(guild.roles), inline=True)
    embed.add_field(name="📅 Criado em", value=created_at, inline=False)

    await ctx.reply(embed=embed)

@bot.command(name='avatar')
@is_owner()
async def show_avatar(ctx, user: discord.Member = None):
    """Mostra o avatar de um usuário"""
    if not user:
        user = ctx.author

    embed = discord.Embed(
        title=f"🖼️ Avatar de {user.display_name}",
        color=COLORS['info']
    )

    if user.avatar:
        embed.set_image(url=user.avatar.url)
        embed.add_field(name="🔗 Link direto", value=f"[Clique aqui]({user.avatar.url})", inline=False)
    else:
        embed.description = "Usuário não possui avatar personalizado"

    await ctx.reply(embed=embed)

@bot.command(name='cargo', aliases=['role'])
@is_owner()
async def manage_role(ctx, acao: str, user: discord.Member, *, nome_cargo: str):
    """Adiciona ou remove cargo de um usuário"""
    role = discord.utils.get(ctx.guild.roles, name=nome_cargo)

    if not role:
        await ctx.reply("❌ Cargo não encontrado!")
        return

    try:
        if acao.lower() in ['add', 'adicionar', 'dar']:
            await user.add_roles(role, reason=f"Cargo adicionado por {ctx.author}")

            embed = discord.Embed(
                title="✅ Cargo Adicionado",
                description=f"Cargo @{role.name} adicionado a {user.mention}",
                color=COLORS['success']
            )

            await security_system.log_security_action(
                ctx.guild,
                "🎭 Cargo Adicionado",
                f"@{role.name} adicionado a {user.mention} por {ctx.author.mention}",
                COLORS['success']
            )

        elif acao.lower() in ['remove', 'remover', 'tirar']:
            await user.remove_roles(role, reason=f"Cargo removido por {ctx.author}")

            embed = discord.Embed(
                title="❌ Cargo Removido",
                description=f"Cargo @{role.name} removido de {user.mention}",
                color=COLORS['warning']
            )

            await security_system.log_security_action(
                ctx.guild,
                "🎭 Cargo Removido",
                f"@{role.name} removido de {user.mention} por {ctx.author.mention}",
                COLORS['warning']
            )
        else:
            await ctx.reply("❌ Ação inválida! Use: `adicionar` ou `remover`")
            return

        await ctx.reply(embed=embed)

    except Exception as e:
        await ctx.reply(f"❌ Erro: {e}")

@bot.command(name='nick', aliases=['nickname'])
@is_owner()
async def change_nickname(ctx, user: discord.Member, *, novo_nick: str = None):
    """Altera o nickname de um usuário"""
    try:
        old_nick = user.display_name
        await user.edit(nick=novo_nick, reason=f"Nickname alterado por {ctx.author}")

        embed = discord.Embed(
            title="✏️ Nickname Alterado",
            color=COLORS['success']
        )
        embed.add_field(name="👤 Usuário", value=user.mention, inline=True)
        embed.add_field(name="📝 Antes", value=old_nick, inline=True)
        embed.add_field(name="📝 Depois", value=novo_nick or user.name, inline=True)

        await ctx.reply(embed=embed)

        await security_system.log_security_action(
            ctx.guild,
            "✏️ Nickname Alterado",
            f"Nickname de {user.mention} alterado por {ctx.author.mention}",
            COLORS['info']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao alterar nickname: {e}")

@bot.command(name='criar_cargo', aliases=['create_role'])
@is_owner()
async def create_role(ctx, *, nome_cargo: str):
    """Cria um novo cargo"""
    try:
        role = await ctx.guild.create_role(
            name=nome_cargo,
            reason=f"Cargo criado por {ctx.author}"
        )

        embed = discord.Embed(
            title="✅ Cargo Criado",
            description=f"Cargo @{role.name} criado com sucesso!",
            color=COLORS['success']
        )
        embed.add_field(name="🆔 ID", value=role.id, inline=True)
        embed.add_field(name="👮 Criado por", value=ctx.author.mention, inline=True)

        await ctx.reply(embed=embed)

        await security_system.log_security_action(
            ctx.guild,
            "🎭 Cargo Criado",
            f"Cargo @{role.name} criado por {ctx.author.mention}",
            COLORS['success']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao criar cargo: {e}")

@bot.command(name='deletar_cargo', aliases=['delete_role'])
@is_owner()
async def delete_role(ctx, *, nome_cargo: str):
    """Deleta um cargo"""
    role = discord.utils.get(ctx.guild.roles, name=nome_cargo)

    if not role:
        await ctx.reply("❌ Cargo não encontrado!")
        return

    try:
        role_name = role.name
        await role.delete(reason=f"Cargo deletado por {ctx.author}")

        embed = discord.Embed(
            title="🗑️ Cargo Deletado",
            description=f"Cargo @{role_name} foi deletado",
            color=COLORS['warning']
        )
        embed.add_field(name="👮 Deletado por", value=ctx.author.mention, inline=True)

        await ctx.reply(embed=embed)

        await security_system.log_security_action(
            ctx.guild,
            "🗑️ Cargo Deletado",
            f"Cargo @{role_name} deletado por {ctx.author.mention}",
            COLORS['warning']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao deletar cargo: {e}")

@bot.command(name='save', aliases=['backup_completo'])
@is_owner()
async def save_server(ctx):
    """🔥 Salva backup completo do servidor com ID único"""
    try:
        guild = ctx.guild
        
        # Gera ID único para o backup
        import uuid
        backup_id = str(uuid.uuid4())[:8].upper()
        
        # Mensagem inicial
        initial_embed = discord.Embed(
            title="💾 INICIANDO BACKUP COMPLETO",
            description="🔄 **Salvando dados do servidor...**\n\n⏳ Aguarde enquanto processamos todos os dados",
            color=COLORS['info']
        )
        message = await ctx.reply(embed=initial_embed)
        
        # Dados do backup
        backup_data = {
            'backup_id': backup_id,
            'server_name': guild.name,
            'server_id': guild.id,
            'created_at': datetime.utcnow().isoformat(),
            'created_by': ctx.author.id,
            'channels': [],
            'roles': [],
            'categories': [],
            'members_count': guild.member_count,
            'server_icon': str(guild.icon.url) if guild.icon else None,
            'server_banner': str(guild.banner.url) if guild.banner else None,
            'backup_version': '2.0'
        }

        # Backup de categorias
        progress_embed = discord.Embed(
            title="💾 BACKUP EM PROGRESSO",
            description="🔄 **Salvando categorias...**",
            color=COLORS['warning']
        )
        await message.edit(embed=progress_embed)
        
        categories_count = 0
        for category in guild.categories:
            try:
                category_data = {
                    'name': category.name,
                    'position': category.position,
                    'id': category.id,
                    'created_at': category.created_at.isoformat() if category.created_at else None
                }
                backup_data['categories'].append(category_data)
                categories_count += 1
            except Exception as e:
                print(f"❌ Erro ao salvar categoria {category.name}: {e}")

        # Backup de canais
        progress_embed.description = f"🔄 **Salvando canais...** ({len(guild.channels)} encontrados)"
        await message.edit(embed=progress_embed)
        
        channels_count = 0
        for channel in guild.channels:
            try:
                channel_data = {
                    'name': channel.name,
                    'type': str(channel.type),
                    'position': channel.position,
                    'category': channel.category.name if channel.category else None,
                    'id': channel.id,
                    'created_at': channel.created_at.isoformat() if channel.created_at else None
                }
                
                # Dados específicos por tipo de canal
                if hasattr(channel, 'topic'):
                    channel_data['topic'] = channel.topic
                if hasattr(channel, 'slowmode_delay'):
                    channel_data['slowmode_delay'] = channel.slowmode_delay
                if hasattr(channel, 'nsfw'):
                    channel_data['nsfw'] = channel.nsfw
                if hasattr(channel, 'bitrate'):
                    channel_data['bitrate'] = channel.bitrate
                if hasattr(channel, 'user_limit'):
                    channel_data['user_limit'] = channel.user_limit
                    
                backup_data['channels'].append(channel_data)
                channels_count += 1
            except Exception as e:
                print(f"❌ Erro ao salvar canal {channel.name}: {e}")

        # Backup de cargos
        progress_embed.description = f"🔄 **Salvando cargos...** ({len(guild.roles)} encontrados)"
        await message.edit(embed=progress_embed)
        
        roles_count = 0
        for role in guild.roles:
            if role != guild.default_role:
                try:
                    role_data = {
                        'name': role.name,
                        'color': str(role.color),
                        'position': role.position,
                        'permissions': role.permissions.value,
                        'hoist': role.hoist,
                        'mentionable': role.mentionable,
                        'managed': role.managed,
                        'members_count': len(role.members),
                        'id': role.id,
                        'created_at': role.created_at.isoformat() if role.created_at else None
                    }
                    backup_data['roles'].append(role_data)
                    roles_count += 1
                except Exception as e:
                    print(f"❌ Erro ao salvar cargo {role.name}: {e}")

        # Finaliza salvamento
        progress_embed.description = "🔄 **Finalizando backup e salvando arquivo...**"
        await message.edit(embed=progress_embed)

        # Verifica se os dados foram coletados corretamente
        if not backup_data['channels'] and not backup_data['roles']:
            raise Exception("Nenhum dado foi coletado para o backup")

        # Salva backup com ID único
        guild_id_str = str(guild.id)
        if guild_id_str not in security_system.backup_data:
            security_system.backup_data[guild_id_str] = {'channels': [], 'roles': [], 'full_backups': []}

        # Adiciona o novo backup mantendo histórico
        if 'full_backups' not in security_system.backup_data[guild_id_str]:
            security_system.backup_data[guild_id_str]['full_backups'] = []
            
        security_system.backup_data[guild_id_str]['full_backups'].append(backup_data)
        
        # Mantém apenas os últimos 10 backups
        security_system.backup_data[guild_id_str]['full_backups'] = security_system.backup_data[guild_id_str]['full_backups'][-10:]
        
        # Salva os dados no arquivo
        await security_system.save_data()

        # Verifica se o backup foi salvo corretamente
        try:
            # Recarrega os dados para verificar
            await security_system.load_data()
            saved_backup = None
            if guild_id_str in security_system.backup_data:
                for backup in security_system.backup_data[guild_id_str].get('full_backups', []):
                    if backup.get('backup_id') == backup_id:
                        saved_backup = backup
                        break
            
            if not saved_backup:
                raise Exception("Backup não foi encontrado após salvamento")
                
        except Exception as e:
            raise Exception(f"Falha na verificação do backup: {str(e)}")

        # Embed final de sucesso
        success_embed = discord.Embed(
            title="✅ BACKUP COMPLETO SALVO COM SUCESSO",
            description=f"🎉 **Backup realizado e verificado!**\n\n🆔 **ID do Backup:** `{backup_id}`\n💾 **Arquivo salvo em:** `security_data.json`",
            color=COLORS['success'],
            timestamp=datetime.utcnow()
        )
        
        success_embed.add_field(
            name="📊 Dados Salvos", 
            value=f"📺 **Canais:** {channels_count}/{len(guild.channels)}\n🎭 **Cargos:** {roles_count}/{len(guild.roles)-1}\n📁 **Categorias:** {categories_count}\n👥 **Membros:** {backup_data['members_count']}", 
            inline=True
        )
        
        success_embed.add_field(
            name="🔧 Informações", 
            value=f"🏰 **Servidor:** {guild.name}\n📅 **Data:** {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}\n👤 **Por:** {ctx.author.mention}\n📁 **Versão:** {backup_data['backup_version']}", 
            inline=True
        )
        
        success_embed.add_field(
            name="⚡ Comandos Úteis", 
            value=f"• `!sec_restore {backup_id}` - Restaurar backup\n• `!sec_backup` - Ver todos os backups\n• `!sec_logs` - Ver logs do sistema", 
            inline=False
        )
        
        success_embed.set_footer(text=f"Backup ID: {backup_id} | Sistema de Segurança v2.0", icon_url=guild.icon.url if guild.icon else None)

        await message.edit(embed=success_embed)

        # Log da ação
        await security_system.log_security_action(
            guild,
            "💾 BACKUP COMPLETO SALVO",
            f"Backup `{backup_id}` criado por {ctx.author.mention} - {channels_count} canais, {roles_count} cargos salvos",
            COLORS['success'],
            [
                {'name': '🆔 ID', 'value': backup_id, 'inline': True},
                {'name': '📊 Dados', 'value': f"{channels_count} canais, {roles_count} cargos", 'inline': True},
                {'name': '✅ Status', 'value': "Verificado e salvo", 'inline': True}
            ]
        )

        print(f"✅ Backup {backup_id} salvo com sucesso para {guild.name}")

    except Exception as e:
        error_embed = discord.Embed(
            title="❌ ERRO NO BACKUP",
            description=f"**Falha ao criar backup:**\n```{str(e)}```\n\n🔧 **Possíveis soluções:**\n• Verifique se o bot tem permissões adequadas\n• Tente novamente em alguns minutos\n• Contate o desenvolvedor se o erro persistir",
            color=COLORS['danger']
        )
        try:
            await message.edit(embed=error_embed)
        except:
            await ctx.reply(embed=error_embed)
        
        print(f"❌ Erro no backup: {e}")
        
        # Log do erro
        try:
            await security_system.log_security_action(
                guild,
                "❌ ERRO NO BACKUP",
                f"Falha ao criar backup: {str(e)}",
                COLORS['danger']
            )
        except:
            pass

@bot.command(name='verify_backup', aliases=['verificar'])
@is_owner()
async def verify_backup(ctx, backup_id: str = None):
    """🔍 Verifica a integridade de um backup específico"""
    if not backup_id:
        embed = discord.Embed(
            title="❌ ID Necessário",
            description="Use: `!sec_verify_backup <ID_do_backup>`\n\nPara ver backups disponíveis: `!sec_b`",
            color=COLORS['danger']
        )
        await ctx.reply(embed=embed)
        return
    
    try:
        guild_id_str = str(ctx.guild.id)
        backups = security_system.backup_data.get(guild_id_str, {}).get('full_backups', [])
        
        # Procura backup pelo ID
        target_backup = None
        for backup in backups:
            if backup.get('backup_id', '').upper() == backup_id.upper():
                target_backup = backup
                break
                
        if not target_backup:
            embed = discord.Embed(
                title="❌ Backup Não Encontrado",
                description=f"Backup com ID `{backup_id}` não foi encontrado.\n\nUse `!sec_b` para ver backups disponíveis.",
                color=COLORS['danger']
            )
            await ctx.reply(embed=embed)
            return

        # Verifica a integridade do backup
        embed = discord.Embed(
            title="🔍 VERIFICAÇÃO DE BACKUP",
            color=COLORS['info'],
            timestamp=datetime.utcnow()
        )
        
        # Informações básicas
        created_date = datetime.fromisoformat(target_backup['created_at']).strftime('%d/%m/%Y %H:%M')
        embed.add_field(
            name="ℹ️ Informações Básicas",
            value=f"🆔 **ID:** `{target_backup['backup_id']}`\n🏰 **Servidor:** {target_backup['server_name']}\n📅 **Criado:** {created_date}\n👤 **Por:** <@{target_backup['created_by']}>\n📊 **Versão:** {target_backup.get('backup_version', '1.0')}",
            inline=True
        )
        
        # Contagem de dados
        channels_count = len(target_backup.get('channels', []))
        roles_count = len(target_backup.get('roles', []))
        categories_count = len(target_backup.get('categories', []))
        
        embed.add_field(
            name="📊 Dados Salvos",
            value=f"📺 **Canais:** {channels_count}\n🎭 **Cargos:** {roles_count}\n📁 **Categorias:** {categories_count}\n👥 **Membros:** {target_backup.get('members_count', 0)}",
            inline=True
        )
        
        # Verificação de integridade
        issues = []
        
        # Verifica campos obrigatórios
        required_fields = ['backup_id', 'server_name', 'server_id', 'created_at', 'created_by']
        for field in required_fields:
            if field not in target_backup:
                issues.append(f"❌ Campo obrigatório ausente: {field}")
        
        # Verifica se há dados
        if channels_count == 0 and roles_count == 0:
            issues.append("⚠️ Backup não contém canais nem cargos")
        
        # Verifica estrutura dos canais
        for i, channel in enumerate(target_backup.get('channels', [])):
            if not channel.get('name'):
                issues.append(f"❌ Canal {i+1} sem nome")
            if not channel.get('type'):
                issues.append(f"❌ Canal {i+1} sem tipo")
        
        # Verifica estrutura dos cargos
        for i, role in enumerate(target_backup.get('roles', [])):
            if not role.get('name'):
                issues.append(f"❌ Cargo {i+1} sem nome")
            if 'permissions' not in role:
                issues.append(f"❌ Cargo {i+1} sem permissões")
        
        # Status da verificação
        if not issues:
            status_text = "✅ **Backup íntegro e válido**\n🔒 Todos os dados estão corretos\n⚡ Pronto para restauração"
            status_color = COLORS['success']
        else:
            status_text = f"⚠️ **{len(issues)} problema(s) encontrado(s)**\n" + '\n'.join(issues[:5])
            if len(issues) > 5:
                status_text += f"\n... e mais {len(issues) - 5} problema(s)"
            status_color = COLORS['warning']
        
        embed.add_field(
            name="🔍 Status da Verificação",
            value=status_text,
            inline=False
        )
        
        embed.color = status_color
        embed.set_footer(text=f"Verificação do backup {backup_id}")
        
        await ctx.reply(embed=embed)

    except Exception as e:
        error_embed = discord.Embed(
            title="❌ ERRO NA VERIFICAÇÃO",
            description=f"Falha ao verificar backup: {str(e)}",
            color=COLORS['danger']
        )
        await ctx.reply(embed=error_embed)

@bot.command(name='backup_server', aliases=['backup_old'])
@is_owner()
async def backup_server_old(ctx):
    """Cria backup completo do servidor (método antigo)"""
    await ctx.reply("⚠️ Use `!sec_save` para criar backups com ID único!")
    await save_server(ctx)

@bot.command(name='audit', aliases=['auditoria'])
@is_owner()
async def audit_logs(ctx, limite: int = 10):
    """Mostra logs de auditoria do servidor"""
    try:
        embed = discord.Embed(
            title="📋 Logs de Auditoria",
            color=COLORS['info']
        )

        logs = []
        async for entry in ctx.guild.audit_logs(limit=limite):
            timestamp = entry.created_at.strftime("%d/%m %H:%M")
            action_name = str(entry.action).replace('AuditLogAction.', '').replace('_', ' ').title()

            log_text = f"**{timestamp}** - {action_name}"
            if entry.user:
                log_text += f" por {entry.user.name}"
            if entry.target:
                target_name = getattr(entry.target, 'name', str(entry.target))
                log_text += f" (Target: {target_name})"

            logs.append(log_text)

        if logs:
            embed.description = '\n'.join(logs)
        else:
            embed.description = "Nenhum log encontrado"

        await ctx.reply(embed=embed)

    except Exception as e:
        await ctx.reply(f"❌ Erro ao buscar logs: {e}")

@bot.command(name='membros', aliases=['members'])
@is_owner()
async def list_members(ctx, status: str = "all"):
    """Lista membros por status"""
    guild = ctx.guild

    if status == "online":
        members = [m for m in guild.members if m.status == discord.Status.online]
        title = "🟢 Membros Online"
    elif status == "offline":
        members = [m for m in guild.members if m.status == discord.Status.offline]
        title = "⚫ Membros Offline"
    elif status == "bots":
        members = [m for m in guild.members if m.bot]
        title = "🤖 Bots no Servidor"
    else:
        members = guild.members
        title = "👥 Todos os Membros"

    embed = discord.Embed(
        title=title,
        description=f"Total: {len(members)} membros",
        color=COLORS['info']
    )

    member_list = []
    for member in members[:20]:  # Máximo 20 para não ultrapassar limite
        member_list.append(f"{member.display_name} ({member.id})")

    if member_list:
        embed.add_field(
            name="📝 Lista",
            value='\n'.join(member_list),
            inline=False
        )

    if len(members) > 20:
        embed.add_field(
            name="ℹ️ Aviso",
            value=f"Mostrando apenas os primeiros 20 de {len(members)} membros",
            inline=False
        )

    await ctx.reply(embed=embed)

@bot.command(name='canais', aliases=['channels'])
@is_owner()
async def list_channels(ctx):
    """Lista todos os canais do servidor"""
    guild = ctx.guild

    text_channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
    voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
    categories = [c for c in guild.channels if isinstance(c, discord.CategoryChannel)]

    embed = discord.Embed(
        title="📺 Canais do Servidor",
        color=COLORS['info']
    )

    if text_channels:
        text_list = [f"#{c.name} ({c.id})" for c in text_channels[:10]]
        embed.add_field(
            name=f"💬 Texto ({len(text_channels)})",
            value='\n'.join(text_list),
            inline=True
        )

    if voice_channels:
        voice_list = [f"🔊 {c.name} ({c.id})" for c in voice_channels[:10]]
        embed.add_field(
            name=f"🔊 Voz ({len(voice_channels)})",
            value='\n'.join(voice_list),
            inline=True
        )

    if categories:
        cat_list = [f"📁 {c.name} ({c.id})" for c in categories[:10]]
        embed.add_field(
            name=f"📁 Categorias ({len(categories)})",
            value='\n'.join(cat_list),
            inline=True
        )

    await ctx.reply(embed=embed)

@bot.command(name='anuncio', aliases=['announce'])
@is_owner()
async def make_announcement(ctx, canal: discord.TextChannel, *, mensagem: str):
    """Faz um anúncio em um canal específico"""
    try:
        embed = discord.Embed(
            title="📢 Anúncio Official",
            description=mensagem,
            color=COLORS['info'],
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"Anúncio feito por {ctx.author.display_name}")

        await canal.send(embed=embed)

        confirmation = discord.Embed(
            title="✅ Anúncio Enviado",
            description=f"Anúncio enviado para {canal.mention}",
            color=COLORS['success']
        )
        await ctx.reply(embed=confirmation)

        await security_system.log_security_action(
            ctx.guild,
            "📢 Anúncio Feito",
            f"Anúncio enviado para {canal.mention} por {ctx.author.mention}",
            COLORS['info']
        )

    except Exception as e:
        await ctx.reply(f"❌ Erro ao enviar anúncio: {e}")

@bot.command(name='status_categoria')
async def status_categoria(ctx):
    """Verifica quantas mensagens estão salvas na categoria monitorada"""
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ Apenas o owner pode usar este comando.")

    count = 0
    channels_count = len(security_system.category_messages)
    for channel_id in security_system.category_messages:
        count += len(security_system.category_messages[channel_id])

    embed = discord.Embed(
        title="📊 Status da Categoria Monitorada",
        description=f"Monitorando categoria: `1451797806259114080`",
        color=COLORS['info'],
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="📺 Canais com histórico", value=str(channels_count), inline=True)
    embed.add_field(name="💬 Total de mensagens salvas", value=str(count), inline=True)
    embed.set_footer(text="Use este comando para verificar se o sistema está capturando mensagens.")
    
    await ctx.send(embed=embed)

@bot.command(name='savecanais')
async def savecanais(ctx):
    """Analisa e salva as últimas 50 mensagens de cada canal na categoria monitorada"""
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ Apenas o owner pode usar este comando.")

    monitored_category_id = 1451797806259114080
    category = discord.utils.get(ctx.guild.categories, id=monitored_category_id)
    
    if not category:
        return await ctx.send(f"❌ Categoria `1451797806259114080` não encontrada neste servidor.")

    status_msg = await ctx.send(f"🔄 Iniciando indexação dos canais da categoria **{category.name}**...")
    
    channels_processed = 0
    total_messages_saved = 0

    for channel in category.text_channels:
        channel_id_str = str(channel.id)
        # Limpar histórico antigo antes de re-indexar para garantir frescor
        security_system.category_messages[channel_id_str] = []
        
        try:
            async for message in channel.history(limit=50, oldest_first=False):
                if message.author.bot:
                    continue
                
                msg_data = {
                    'author': str(message.author),
                    'content': message.content,
                    'timestamp': message.created_at.isoformat(),
                    'embeds': [e.to_dict() for e in message.embeds]
                }
                security_system.category_messages[channel_id_str].append(msg_data)
                total_messages_saved += 1
            
            # Reverter para manter a ordem cronológica correta (histórico veio do novo pro velho)
            security_system.category_messages[channel_id_str].reverse()
            channels_processed += 1
        except Exception as e:
            print(f"❌ Erle ao indexar canal {channel.name}: {e}")

    await security_system.save_data()
    
    # Log da indexação no console
    print(f"📥 [INDEXAÇÃO] Categoria: {category.name}")
    print(f"📊 [INDEXAÇÃO] Canais Processados: {channels_processed}")
    print(f"💬 [INDEXAÇÃO] Mensagens Salvas: {total_messages_saved}")
    print(f"👤 [INDEXAÇÃO] Iniciado por: {ctx.author} ({ctx.author.id})")
    
    # Log da indexação no Discord
    await security_system.log_security_action(
        ctx.guild,
        "📥 INDEXAÇÃO DE CANAIS CONCLUÍDA",
        f"O owner {ctx.author.mention} realizou o backup de mensagens da categoria monitorada.",
        COLORS['info'],
        [
            {'name': '📺 Canais Processados', 'value': str(channels_processed), 'inline': True},
            {'name': '💬 Mensagens Salvas', 'value': str(total_messages_saved), 'inline': True},
            {'name': '📂 Categoria', 'value': category.name, 'inline': True}
        ]
    )

    embed = discord.Embed(
        title="✅ Indexação Concluída",
        description=f"O sistema analisou os canais da categoria monitorada.",
        color=COLORS['success'],
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="📺 Canais Processados", value=str(channels_processed), inline=True)
    embed.add_field(name="💬 Mensagens Indexadas", value=str(total_messages_saved), inline=True)
    embed.set_footer(text="As mensagens agora estão salvas e prontas para recuperação.")
    
    await status_msg.edit(content=None, embed=embed)

@bot.command(name='limpar_historico')
async def limpar_historico(ctx):
    """Limpa o histórico de mensagens salvas da categoria"""
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ Apenas o owner pode usar este comando.")
    
    security_system.category_messages = {}
    await security_system.save_data()
    await ctx.send("✅ Histórico da categoria monitorada foi limpo com sucesso!")

@bot.command(name='help', aliases=['h', 'ajuda'])
async def security_help(ctx):
    """Central de ajuda - COMANDO PÚBLICO"""
    # Verificação se é o owner para mostrar informações especiais
    is_owner_user = ctx.author.id == OWNER_ID
    embed = discord.Embed(
        title="Sistema de Segurança",
        description="Bot de proteção anti-raid, anti-spam e moderação.",
        color=0x00ff41,
        timestamp=datetime.utcnow()
    )

    embed.set_author(name="Central de Comandos", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)

    embed.add_field(
        name="Básicos",
        value=(
            "`!sec_c` — Configurações do sistema\n"
            "`!sec_w` — Gerenciar whitelist\n"
            "`!sec_r` — Restaurar cargos removidos\n"
            "`!sec_s` — Status do sistema\n"
            "`!sec_l` — Logs de segurança\n"
            "`!sec_b` — Backups disponíveis"
        ),
        inline=True
    )

    embed.add_field(
        name="Moderação",
        value=(
            "`!sec_banir @user motivo`\n"
            "`!sec_expulsar @user motivo`\n"
            "`!sec_m @user tempo motivo`\n"
            "`!sec_desmutar @user`\n"
            "`!sec_av @user motivo`\n"
            "`!sec_avisos @user`"
        ),
        inline=True
    )

    embed.add_field(
        name="Canais",
        value=(
            "`!sec_limpar [qtd]`\n"
            "`!sec_slowmode [seg]`\n"
            "`!sec_bloquear`\n"
            "`!sec_desbloquear`\n"
            "`!sec_anuncio #canal msg`"
        ),
        inline=True
    )

    embed.add_field(
        name="Utilidades",
        value=(
            "`!sec_info [@user]`\n"
            "`!sec_avatar [@user]`\n"
            "`!sec_servidor`\n"
            "`!sec_membros [status]`\n"
            "`!sec_canais`\n"
            "`!sec_audit [limite]`\n"
            "`!sec_save` / `!sec_restore <ID>`\n"
            "`!sec_savecanais`\n"
            "`!sec_status_categoria`\n"
            "`!sec_limpar_historico`"
        ),
        inline=True
    )

    embed.add_field(
        name="Cargos",
        value=(
            "`!sec_cargo add/remove @user cargo`\n"
            "`!sec_nick @user novo_nick`\n"
            "`!sec_criar_cargo nome`\n"
            "`!sec_deletar_cargo nome`\n"
            "`!sec_cargoinfo nome`"
        ),
        inline=True
    )

    embed.add_field(
        name="Info",
        value=(
            f"Servidores: {len(bot.guilds)}\n"
            f"Owner verificado: {'sim' if is_owner_user else 'não'}\n"
            "Apenas o owner pode usar comandos."
        ),
        inline=True
    )

    embed.set_footer(
        text="Sistema de Segurança",
        icon_url=bot.user.avatar.url if bot.user.avatar else None
    )

    await ctx.reply(embed=embed)

# Error handler
@bot.event
async def on_command_error(ctx, error):
    """Tratamento de erros dos comandos"""
    if isinstance(error, commands.CheckFailure):
        # BLOQUEIA QUALQUER UM QUE NÃO SEJA O OWNER
        if ctx.author.id != OWNER_ID:
            embed = discord.Embed(
                title="🚫 COMANDO BLOQUEADO",
                description=f"❌ **ACESSO NEGADO!**\n\n👑 **Owner:** `{OWNER_ID}`\n🆔 **Você:** `{ctx.author.id}`\n🚫 **Status:** Não autorizado",
                color=COLORS['danger']
            )
            embed.add_field(
                name="⚠️ AVISO",
                value="Apenas o owner do bot pode executar comandos.\nUse `!sec_help` para ver a central de ajuda.",
                inline=False
            )
            embed.set_footer(text="Sistema de Segurança - Acesso Bloqueado")
            await ctx.reply(embed=embed)
    elif isinstance(error, commands.CommandNotFound):
        return  # Ignora comandos inexistentes
    else:
        print(f"❌ Erro: {error}")
        if ctx.author.id == OWNER_ID:
            await ctx.reply(f"❌ Erro: {error}")

# Inicialização
if __name__ == "__main__":
    load_dotenv()
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')

    if TOKEN:
        print("🚀 Iniciando Sistema de Segurança Avançado...")
        print("⚙️ Configurações padrão:")
        print("  • Proteção de canais/cargos: SEMPRE ATIVO")
        print("  • Anti-spam: OPCIONAL (10s de silenciamento)")
        print("  • Anti mass-ping: OPCIONAL (10s de silenciamento)")
        print("  • Outras proteções: CONFIGURÁVEIS por servidor")
        keep_alive()
        bot.run(TOKEN)
    else:
        print("❌ Token não encontrado! Configure DISCORD_BOT_TOKEN nas Secrets")
